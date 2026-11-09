"""
Student profile endpoints. Every route is under /students/me, so a student can only
ever read or change THEIR OWN profile (the id comes from the login token, never from
the URL). That is how we "restrict users to authorized actions".
"""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import documents, mongo
from ..core.deps import require_student
from ..core.uploads import delete_upload, public_url, save_profile_picture
from ..mongo import Doc, get_db
from ..schemas.activity import ActivityDay
from ..schemas.profile import PictureResponse, StudentProfile, StudentUpdate
from ..services.activity import application_activity
from ..services.activity_log import log_activity
from ..services.students import experience_out

router = APIRouter(prefix="/students", tags=["Student profile"])


def to_student_profile(s: Doc) -> StudentProfile:
    return StudentProfile(
        id=s.id, name=s.name, email=s.email, college=s.college,
        date_of_birth=s.date_of_birth, city=s.city, state=s.state, country=s.country,
        career_objective=s.career_objective, degree=s.degree, major=s.major,
        graduation_year=s.graduation_year, cgpa=s.cgpa, phone=s.phone,
        profile_pic_url=public_url(s.profile_pic_path),
        skills=sorted(s.skills, key=str.lower),
        experience=experience_out(s),
    )


@router.get("/me", response_model=StudentProfile, summary="View my profile")
def get_my_profile(student: Doc = Depends(require_student)):
    return to_student_profile(student)


@router.patch("/me", response_model=StudentProfile, summary="Update my profile (partial)")
def update_my_profile(body: StudentUpdate, student: Doc = Depends(require_student),
                      db: Database = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)   # only the fields the client actually sent
    skills = data.pop("skills", None)
    experience = data.pop("experience", None)

    new_email = data.get("email")
    if new_email and new_email != student.email:
        if mongo.find_one(db, "students", {"email": new_email, "_id": {"$ne": student.id}}):
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")

    changes = dict(data)
    if skills is not None:
        changes["skills"] = skills
    if experience is not None:       # the whole list is replaced; every entry gets its own id
        first_id = mongo.next_id(db, "student_experience", max(len(experience), 1))
        changes["experiences"] = [documents.experience(first_id + n, **item) for n, item in enumerate(experience)]
    changes.update(documents.derived("students", changes))      # name_lower, skills_lower

    try:
        mongo.update(db, "students", student.id, changes)
    except DuplicateKeyError:        # two accounts changing to the same email at once
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")
    log_activity(db, "student", student.id, "profile_updated")
    return to_student_profile(mongo.get(db, "students", student.id))


@router.post("/me/profile-picture", response_model=PictureResponse, summary="Upload my profile picture")
def upload_my_picture(file: UploadFile = File(..., description="PNG, JPEG or WebP, max 2 MB"),
                      student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    new_path = save_profile_picture(db, file, "student", student.id)
    old_path = student.profile_pic_path
    try:
        mongo.update(db, "students", student.id, {"profile_pic_path": new_path})
    except Exception:
        delete_upload(db, new_path)   # don't leave an orphan file behind
        raise
    delete_upload(db, old_path)       # remove the previous picture only after the save worked
    return PictureResponse(profile_pic_url=public_url(new_path))


@router.get("/me/activity", response_model=List[ActivityDay],
            summary="My application activity per day, for the heatmap (student only)")
def my_activity(days: int = Query(365, ge=1, le=730, description="How many days back, ending today (1 to 730)"),
                student: Doc = Depends(require_student), db: Database = Depends(get_db)):
    return application_activity(db, student.id, days)
