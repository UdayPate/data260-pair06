"""
File upload helpers: profile pictures (public) and resume PDFs (private).

Safety rules we follow (pictures AND resumes):
  * We NEVER use the filename the user sent. We make our own name, so nobody can
    upload "../../something" to write outside the uploads folder.
  * We check the file's first bytes ("magic bytes"), not just the extension or the
    Content-Type header, because both of those are easy to fake.
  * We only accept PNG, JPEG and WebP. SVG is refused on purpose: an SVG file can
    contain JavaScript.
  * There is a size limit.

Database rows store only the RELATIVE path (e.g. "profile_pics/student_1_ab12.png").
"""
import os
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status

from .. import config  # read config.UPLOAD_DIR at call time (lets tests point it at a temp folder)

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB


def detect_image_type(data: bytes) -> Optional[str]:
    """Return 'png', 'jpg' or 'webp' based on the file's first bytes, else None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_profile_picture(file: UploadFile, owner_type: str, owner_id: int) -> str:
    """Validate and store an uploaded picture. Returns its relative path."""
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be 2 MB or smaller")
    ext = detect_image_type(data)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PNG, JPEG or WebP images are allowed")

    rel_path = f"profile_pics/{owner_type}_{owner_id}_{uuid.uuid4().hex[:12]}.{ext}"
    abs_path = os.path.join(config.UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return rel_path


def _inside(base: str, target: str) -> bool:
    """True if `target` is inside folder `base` (guards against '../' tricks)."""
    try:
        return os.path.commonpath([base, target]) == base
    except ValueError:      # e.g. paths on different drives on Windows
        return False


def delete_upload(rel_path: Optional[str]) -> None:
    """Delete a stored file. Silently ignores missing files and paths outside UPLOAD_DIR."""
    if not rel_path:
        return
    base = os.path.abspath(config.UPLOAD_DIR)
    target = os.path.abspath(os.path.join(base, rel_path))
    if not _inside(base, target):
        return
    try:
        os.remove(target)
    except FileNotFoundError:
        pass


def save_resume(file: UploadFile, student_id: int, job_id: int) -> str:
    """Validate and store an uploaded resume. Only real PDFs are accepted: the file must
    START with the PDF signature "%PDF-" (we do not trust the filename or Content-Type)."""
    data = file.file.read(MAX_RESUME_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume must be 5 MB or smaller")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Resume must be a PDF file")

    rel_path = f"resumes/app_{student_id}_{job_id}_{uuid.uuid4().hex[:12]}.pdf"
    abs_path = os.path.join(config.UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return rel_path


def resume_file_path(rel_path: Optional[str]) -> Optional[str]:
    """Absolute path of a stored resume, or None if it is missing or is NOT inside the
    resumes folder (so a bad value in the database can never expose other files)."""
    if not rel_path:
        return None
    base = os.path.abspath(os.path.join(config.UPLOAD_DIR, "resumes"))
    target = os.path.abspath(os.path.join(config.UPLOAD_DIR, rel_path))
    if not _inside(base, target) or not os.path.isfile(target):
        return None
    return target


def public_url(rel_path: Optional[str]) -> Optional[str]:
    """URL the browser can use to show a profile picture (served by main.py)."""
    return f"/media/{rel_path}" if rel_path else None