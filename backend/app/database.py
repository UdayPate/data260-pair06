"""
Database connection setup.

engine       -> the connection pool to MySQL
SessionLocal -> creates a "session" (one unit of work / conversation with the DB)
Base         -> parent class for every table model in models.py
get_db       -> FastAPI dependency: gives each request its own session, then closes it
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()