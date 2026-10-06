"""
Student profile endpoints. Every route is under /students/me, so a student can only
ever read or change THEIR OWN profile (the id comes from the login token, never from
the URL). That is how we "restrict users to authorized actions".
"""
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.deps import require_student
from ..core.uploads import delete_upload, public_url, save_profile_picture
from ..database import get_db
from ..models import Student, StudentExperience, StudentSkill
from ..schemas.profile import ExperienceOut, PictureResponse, StudentProfile, StudentUpdate

router = APIRouter(prefix="/students", tags=["Student profile"])


def to_student_profile(s: Student) -> StudentProfile:
    experiences = sorted(s.experiences, key=lambda e: e.start_date or date.min, reverse=True)
    return StudentProfile(
        id=s.id, name=s.name, email=s.email, college=s.college,
        date_of_birth=s.date_of_birth, city=s.city, state=s.state, country=s.country,
        career_objective=s.career_objective, degree=s.degree, major=s.major,
        graduation_year=s.graduation_year, cgpa=s.cgpa, phone=s.phone,
        profile_pic_url=public_url(s.profile_pic_path),
        skills=sorted((k.skill for k in s.skills), key=str.lower),
        experience=[ExperienceOut.model_validate(e) for e in experiences],
    )


def _sync_skills(student: Student, new_skills: list) -> None:
    """Make the student's skill rows match `new_skills`, changing as little as possible.
    (We diff instead of delete-all + insert-all because the table has a UNIQUE
    (student_id, skill) rule, and re-inserting a skill in the same save would clash.)"""
    existing = {row.skill.lower(): row for row in student.skills}
    wanted = {skill.lower(): skill for skill in new_skills}
    for key, row in list(existing.items()):
        if key not in wanted:
            student.skills.remove(row)          # delete-orphan removes it from MySQL
        elif row.skill != wanted[key]:
            row.skill = wanted[key]             # same skill, spelling/casing fixed
    for key, text in wanted.items():
        if key not in existing:
            student.skills.append(StudentSkill(skill=text))


@router.get("/me", response_model=StudentProfile, summary="View my profile")
def get_my_profile(student: Student = Depends(require_student)):
    return to_student_profile(student)


@router.patch("/me", response_model=StudentProfile, summary="Update my profile (partial)")
def update_my_profile(body: StudentUpdate, student: Student = Depends(require_student),
                      db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)   # only the fields the client actually sent
    skills = data.pop("skills", None)
    experience = data.pop("experience", None)

    new_email = data.get("email")
    if new_email and new_email != student.email:
        taken = db.scalar(select(Student.id).where(Student.email == new_email, Student.id != student.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")

    for field, value in data.items():
        setattr(student, field, value)
    if skills is not None:
        _sync_skills(student, skills)
    if experience is not None:
        student.experiences = [StudentExperience(**item) for item in experience]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")
    db.refresh(student)
    return to_student_profile(student)


@router.post("/me/profile-picture", response_model=PictureResponse, summary="Upload my profile picture")
def upload_my_picture(file: UploadFile = File(..., description="PNG, JPEG or WebP, max 2 MB"),
                      student: Student = Depends(require_student), db: Session = Depends(get_db)):
    new_path = save_profile_picture(file, "student", student.id)
    old_path = student.profile_pic_path
    student.profile_pic_path = new_path
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_upload(new_path)   # don't leave an orphan file behind
        raise
    delete_upload(old_path)       # remove the previous picture only after the save worked
    return PictureResponse(profile_pic_url=public_url(new_path))