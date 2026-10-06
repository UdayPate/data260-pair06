"""
Company profile endpoints (own profile only, via /companies/me).

Note for later: when we add a public "view any company" route (/companies/{company_id}),
it must be declared AFTER these /me routes, otherwise FastAPI would try to read the
word "me" as a company id.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.deps import require_company
from ..core.uploads import delete_upload, public_url, save_profile_picture
from ..database import get_db
from ..models import Company
from ..schemas.profile import CompanyProfile, CompanyUpdate, PictureResponse

router = APIRouter(prefix="/companies", tags=["Company profile"])


def to_company_profile(c: Company) -> CompanyProfile:
    return CompanyProfile(
        id=c.id, name=c.name, email=c.email, location=c.city, state=c.state,
        industry=c.industry, description=c.description, contact_email=c.contact_email,
        contact_phone=c.contact_phone, website=c.website,
        profile_pic_url=public_url(c.profile_pic_path),
    )


@router.get("/me", response_model=CompanyProfile, summary="View my company profile")
def get_my_company(company: Company = Depends(require_company)):
    return to_company_profile(company)


@router.patch("/me", response_model=CompanyProfile, summary="Update my company profile (partial)")
def update_my_company(body: CompanyUpdate, company: Company = Depends(require_company),
                      db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:                      # the API says "location"; the column is "city"
        data["city"] = data.pop("location")

    new_email = data.get("email")
    if new_email and new_email != company.email:
        taken = db.scalar(select(Company.id).where(Company.email == new_email, Company.id != company.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")

    for field, value in data.items():
        setattr(company, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")
    db.refresh(company)
    return to_company_profile(company)


@router.post("/me/profile-picture", response_model=PictureResponse, summary="Upload my company logo")
def upload_my_logo(file: UploadFile = File(..., description="PNG, JPEG or WebP, max 2 MB"),
                   company: Company = Depends(require_company), db: Session = Depends(get_db)):
    new_path = save_profile_picture(file, "company", company.id)
    old_path = company.profile_pic_path
    company.profile_pic_path = new_path
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_upload(new_path)
        raise
    delete_upload(old_path)
    return PictureResponse(profile_pic_url=public_url(new_path))