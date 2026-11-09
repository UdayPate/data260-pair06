"""
File upload helpers: profile pictures (public) and resume PDFs (private).

Lab 2: the files are stored in MongoDB (GridFS), not on a disk. That way every service container
stays stateless and any of them can serve a file that another one stored.

Safety rules we follow (pictures AND resumes), unchanged from Lab 1:
  * We NEVER use the filename the user sent. We make our own name.
  * We check the file's first bytes ("magic bytes"), not just the extension or the
    Content-Type header, because both of those are easy to fake.
  * We only accept PNG, JPEG and WebP. SVG is refused on purpose: an SVG file can
    contain JavaScript.
  * There is a size limit.

GridFS keeps two buckets: "profile_pics" (public, found by file name) and "resumes" (private, found by id;
only the Application service's /applications/{id}/resume endpoint hands them out after checking who asks).
A document stores only a reference: profile_pic_path = "profile_pics/<name>", resume_file_id = <GridFS id>.
"""
import uuid
from typing import Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException, UploadFile, status
from pymongo.database import Database

from ..mongo import bucket

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB
PICTURES = "profile_pics"
RESUMES = "resumes"
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def detect_image_type(data: bytes) -> Optional[str]:
    """Return 'png', 'jpg' or 'webp' based on the file's first bytes, else None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_profile_picture(db: Database, file: UploadFile, owner_type: str, owner_id: int) -> str:
    """Validate and store an uploaded picture. Returns its path ("profile_pics/<name>")."""
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be 2 MB or smaller")
    ext = detect_image_type(data)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PNG, JPEG or WebP images are allowed")

    name = f"{owner_type}_{owner_id}_{uuid.uuid4().hex[:12]}.{ext}"
    bucket(db, PICTURES).put(data, filename=name, content_type=IMAGE_TYPES[ext],
                             owner_type=owner_type, owner_id=owner_id)
    return f"{PICTURES}/{name}"


def read_profile_picture(db: Database, name: str) -> Optional[Tuple[bytes, str]]:
    """(the picture bytes, its content type) for a stored name, or None."""
    stored = bucket(db, PICTURES).find_one({"filename": name})
    if stored is None:
        return None
    return stored.read(), getattr(stored, "content_type", None) or "application/octet-stream"


def delete_upload(db: Database, path: Optional[str]) -> None:
    """Delete a stored profile picture by its path. Silently ignores a missing file or any other kind of path."""
    if not path or not path.startswith(f"{PICTURES}/"):
        return
    files = bucket(db, PICTURES)
    for stored in list(files.find({"filename": path[len(PICTURES) + 1:]})):
        files.delete(stored._id)


def save_resume(db: Database, file: UploadFile, student_id: int, job_id: int) -> ObjectId:
    """Validate and store an uploaded resume. Only real PDFs are accepted: the file must
    START with the PDF signature "%PDF-" (we do not trust the filename or Content-Type).
    Returns the GridFS id to keep in the application document."""
    data = file.file.read(MAX_RESUME_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume must be 5 MB or smaller")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Resume must be a PDF file")

    name = f"app_{student_id}_{job_id}_{uuid.uuid4().hex[:12]}.pdf"
    return bucket(db, RESUMES).put(data, filename=name, content_type="application/pdf",
                                   student_id=student_id, job_id=job_id)


def read_resume(db: Database, file_id: Optional[ObjectId]) -> Optional[bytes]:
    """The resume PDF bytes, or None if the file is missing."""
    if file_id is None:
        return None
    files = bucket(db, RESUMES)
    if not files.exists(file_id):
        return None
    return files.get(file_id).read()


def delete_resume(db: Database, file_id: Optional[ObjectId]) -> None:
    if file_id is not None:
        bucket(db, RESUMES).delete(file_id)


def public_url(path: Optional[str]) -> Optional[str]:
    """URL the browser can use to show a profile picture (served by routers/media.py)."""
    return f"/media/{path}" if path else None
