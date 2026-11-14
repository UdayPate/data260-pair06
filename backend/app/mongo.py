"""
MongoDB access for every Handshake service (Lab 2). It replaces the MySQL/SQLAlchemy layer of Lab 1.

What is in this file
  get_database()   the one connection to the p06_handshake database (shared by the whole process)
  get_db()         the FastAPI dependency the routers use:  db: Database = Depends(get_db)
  Doc              a document you can read as doc.title instead of doc["title"]
  load() / dump()  convert between MongoDB documents and the Python values the rest of the code uses
  get/find/page/count/insert/update/attach   small helpers so the routers stay short
  next_id()        gives every new document the next whole-number id
  ensure_indexes() the unique rules and search indexes (the replacement for SQL UNIQUE constraints)

Whole-number ids: the URLs (/jobs/12), the website and the assistant tools all use integer ids, so we keep them.
MongoDB's normal ids (ObjectId) are not used for the main collections. The `counters` collection holds one
counter per collection and is increased atomically, so two requests never get the same id.

Dates: a Python date is stored as text "2026-10-05" (easy to read in a MongoDB viewer and it sorts correctly);
date-times (event_datetime, applied_at...) are stored as real MongoDB dates. load() turns the text back into dates.
"""
import logging
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import gridfs
import pymongo
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import PyMongoError

from . import config

logger = logging.getLogger("handshake")

_database: Optional[Database] = None
_indexes_ready = False        # have the indexes been created through this connection yet?


def get_database() -> Database:
    """The p06_handshake database. The connection is created once and re-used."""
    global _database
    if _database is None:
        client = pymongo.MongoClient(config.MONGO_URL, serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS)
        _database = client[config.MONGO_DB_NAME]
    return _database


def use_database(db: Optional[Database]) -> None:
    """The tests call this to plug in an in-memory database (None = go back to the real one)."""
    global _database, _indexes_ready
    _database, _indexes_ready = db, False


def get_db() -> Database:
    """FastAPI dependency: every request gets the shared database object.

    The first request that finds MongoDB reachable also creates the indexes (safe to repeat). That matters when a
    service starts before MongoDB does (Kubernetes does not order start-up): the unique rules are then created as
    soon as the database is there, instead of never."""
    global _indexes_ready
    db = get_database()
    if not _indexes_ready:
        ensure_indexes(db)             # raises PyMongoError while MongoDB is unreachable: the request answers 500
        _indexes_ready = True
    return db


# ---------------- documents ----------------
class Doc(dict):
    """A MongoDB document that can also be read with a dot: doc.title. doc.id is the integer _id."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def id(self) -> int:
        return self["_id"]


# Which fields hold a date (not a date-time). They are stored as "YYYY-MM-DD" text.
DATE_FIELDS = {"students": ("date_of_birth",), "jobs": ("posting_date", "deadline")}
NESTED_DATE_FIELDS = {"students": {"experiences": ("start_date", "end_date")}}


def _as_date(value: Any) -> Any:
    return date.fromisoformat(value) if isinstance(value, str) else value


def load(collection: str, raw: Optional[dict]) -> Optional[Doc]:
    """A document as read from MongoDB -> a Doc whose date fields are real Python dates."""
    if raw is None:
        return None
    doc = Doc(raw)
    for field in DATE_FIELDS.get(collection, ()):
        doc[field] = _as_date(doc.get(field))
    for key, fields in NESTED_DATE_FIELDS.get(collection, {}).items():
        doc[key] = [Doc({**item, **{f: _as_date(item.get(f)) for f in fields}}) for item in doc.get(key) or []]
    return doc


def dump(value: Any) -> Any:
    """Python values -> what MongoDB can store: enums become their text, dates become "YYYY-MM-DD" text.
    Works on filters and updates too, so callers can write {"deadline": {"$gte": date.today()}}."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):          # a datetime is also a date: check it first and leave it alone
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [dump(item) for item in value]
    return value


# ---------------- search filters ----------------
def contains(word: str) -> dict:
    """Case-insensitive "contains" test. re.escape makes a typed "%" or "." an ordinary character."""
    return {"$regex": re.escape(word), "$options": "i"}


def equals_ignoring_case(value: str) -> dict:
    return {"$regex": f"^{re.escape(value)}$", "$options": "i"}


# ---------------- reading ----------------
def get(db: Database, collection: str, _id: Any) -> Optional[Doc]:
    return load(collection, db[collection].find_one({"_id": _id}))


def find_one(db: Database, collection: str, flt: dict) -> Optional[Doc]:
    return load(collection, db[collection].find_one(dump(flt)))


def find(db: Database, collection: str, flt: Optional[dict] = None, *, sort: Optional[list] = None,
         skip: int = 0, limit: int = 0) -> List[Doc]:
    cursor = db[collection].find(dump(flt or {}))
    if sort:
        cursor = cursor.sort(sort)
    if skip:
        cursor = cursor.skip(skip)
    if limit:
        cursor = cursor.limit(limit)
    return [load(collection, raw) for raw in cursor]


def count(db: Database, collection: str, flt: Optional[dict] = None) -> int:
    return db[collection].count_documents(dump(flt or {}))


def page(db: Database, collection: str, flt: Optional[dict], sort: list, page_number: int,
         page_size: int) -> Tuple[List[Doc], int]:
    """(the documents of one page, the total number that match), the way every list endpoint needs it."""
    total = count(db, collection, flt)
    docs = find(db, collection, flt, sort=sort, skip=(page_number - 1) * page_size, limit=page_size)
    return docs, total


def attach(db: Database, docs: Sequence[Doc], key: str, collection: str, attr: str) -> Sequence[Doc]:
    """For each doc, look up the document that doc[key] points to and store it as doc[attr].
    One query for the whole list (a job's company_id -> job.company)."""
    ids = list({doc[key] for doc in docs})
    found = {d.id: d for d in find(db, collection, {"_id": {"$in": ids}})} if ids else {}
    for doc in docs:
        doc[attr] = found.get(doc[key])
    return docs


# ---------------- writing ----------------
def next_id(db: Database, name: str, how_many: int = 1) -> int:
    """Reserve `how_many` ids for collection `name`; returns the first one (an atomic counter)."""
    seq = db.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": how_many}}, upsert=True,
        return_document=ReturnDocument.AFTER)["seq"]
    return seq - how_many + 1


def insert(db: Database, collection: str, data: dict) -> Doc:
    """Insert a new document with the next integer id and return it. A unique index that is violated
    raises pymongo.errors.DuplicateKeyError (the id used up in that case is simply skipped)."""
    doc = dump(data)
    doc["_id"] = next_id(db, collection)
    db[collection].insert_one(doc)
    return load(collection, doc)


def update(db: Database, collection: str, _id: Any, changes: dict) -> None:
    """Change only the listed fields of one document."""
    db[collection].update_one({"_id": _id}, {"$set": dump(changes)})


# ---------------- files (GridFS) ----------------
def bucket(db: Database, name: str) -> gridfs.GridFS:
    """A GridFS bucket: MongoDB's way of storing files. Used for resumes and profile pictures so that no
    service needs a shared disk and every container stays stateless."""
    return gridfs.GridFS(db, collection=name)


# ---------------- indexes ----------------
# (collection, keys, options). Unique indexes replace the SQL UNIQUE constraints of Lab 1.
INDEXES = [
    ("students", [("email", 1)], {"unique": True}),
    ("students", [("name_lower", 1)], {}),
    ("students", [("major", 1)], {}),
    ("students", [("skills_lower", 1)], {}),
    ("companies", [("email", 1)], {"unique": True}),
    ("jobs", [("company_id", 1)], {}),
    ("jobs", [("deadline", 1)], {}),
    ("jobs", [("posting_date", -1), ("_id", -1)], {}),
    ("jobs", [("category", 1)], {}),
    ("jobs", [("skills_lower", 1)], {}),
    ("jobs", [("salary_yearly_max", -1)], {}),
    ("applications", [("student_id", 1), ("job_id", 1)], {"unique": True}),     # one application per student and job
    ("applications", [("job_id", 1)], {}),
    ("applications", [("student_id", 1), ("applied_at", -1)], {}),
    ("events", [("company_id", 1)], {}),
    ("events", [("event_datetime", 1)], {}),
    ("events", [("eligible_majors_lower", 1)], {}),
    ("event_registrations", [("student_id", 1), ("event_id", 1)], {"unique": True}),
    ("event_registrations", [("event_id", 1)], {}),
    ("saved_items", [("student_id", 1), ("item_type", 1), ("item_id", 1)], {"unique": True}),
    ("student_preferences", [("student_id", 1)], {"unique": True}),
    ("sessions", [("expires_at", 1)], {"expireAfterSeconds": 0}),               # MongoDB deletes expired sessions itself
    ("sessions", [("user_id", 1), ("role", 1)], {}),
    ("activity_logs", [("actor_role", 1), ("actor_id", 1), ("at", -1)], {}),
    ("activity_logs", [("action", 1)], {}),
    ("notifications", [("user_role", 1), ("user_id", 1), ("created_at", -1)], {}),
    # The assistant's memory layers (Lab 2, Part 3)
    ("assistant_rules", [("rule_key", 1)], {"unique": True}),
    ("student_memory", [("student_id", 1), ("date", 1)], {}),
    ("conversations", [("student_id", 1), ("updated_at", -1)], {}),
    ("conversations", [("updated_at", 1)], {"expireAfterSeconds": 86400}),     # a chat silent for a day is discarded
]


def ensure_indexes(db: Database) -> None:
    """Create every index (safe to run again). Called when a service starts and by the seed script."""
    for collection, keys, options in INDEXES:
        db[collection].create_index(keys, **options)


def ensure_indexes_quietly() -> None:
    """For service start-up: a database that is not reachable yet must not stop the service from starting
    (/health still works; get_db() creates the indexes on the first request once MongoDB answers)."""
    global _indexes_ready
    try:
        ensure_indexes(get_database())
        _indexes_ready = True
    except PyMongoError as exc:
        logger.warning("Could not create the MongoDB indexes at start-up (they are created on the first request "
                       "that finds the database): %s", exc)
