"""
GET /media/profile_pics/<name>: public profile pictures, read from MongoDB (GridFS).
Resumes are NOT served here; they are private (see routers/applications.py).
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo.database import Database

from ..core.uploads import read_profile_picture
from ..mongo import get_db

router = APIRouter(prefix="/media", tags=["Media"])

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@router.get("/profile_pics/{name}", summary="A public profile picture or company logo")
def profile_picture(name: str, db: Database = Depends(get_db)):
    found = read_profile_picture(db, name) if SAFE_NAME.match(name) else None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Picture not found")
    data, content_type = found
    return Response(content=data, media_type=content_type,
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=3600"})
