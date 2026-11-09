"""
Company profile endpoints (own profile only, via /companies/me).

Order matters: the public "view any company" route (/companies/{company_id}) is declared
AFTER the /me routes, otherwise FastAPI would try to read the word "me" as a company id.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import mongo
from ..core.deps import Identity, get_identity, require_company
from ..core.uploads import delete_upload, public_url, save_profile_picture
from ..mongo import Doc, get_db
from ..schemas.profile import CompanyProfile, CompanyPublic, CompanyUpdate, PictureResponse

router = APIRouter(prefix="/companies", tags=["Company profile"])


def to_company_profile(c: Doc) -> CompanyProfile:
    return CompanyProfile(
        id=c.id, name=c.name, email=c.email, location=c.city, state=c.state,
        industry=c.industry, description=c.description, contact_email=c.contact_email,
        contact_phone=c.contact_phone, website=c.website,
        profile_pic_url=public_url(c.profile_pic_path),
    )


@router.get("/me", response_model=CompanyProfile, summary="View my company profile")
def get_my_company(company: Doc = Depends(require_company)):
    return to_company_profile(company)


@router.patch("/me", response_model=CompanyProfile, summary="Update my company profile (partial)")
def update_my_company(body: CompanyUpdate, company: Doc = Depends(require_company),
                      db: Database = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:                      # the API says "location"; the column is "city"
        data["city"] = data.pop("location")

    new_email = data.get("email")
    if new_email and new_email != company.email:
        if mongo.find_one(db, "companies", {"email": new_email, "_id": {"$ne": company.id}}):
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")

    try:
        mongo.update(db, "companies", company.id, data)
    except DuplicateKeyError:        # two accounts changing to the same email at once
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account")
    return to_company_profile(mongo.get(db, "companies", company.id))


@router.post("/me/profile-picture", response_model=PictureResponse, summary="Upload my company logo")
def upload_my_logo(file: UploadFile = File(..., description="PNG, JPEG or WebP, max 2 MB"),
                   company: Doc = Depends(require_company), db: Database = Depends(get_db)):
    new_path = save_profile_picture(db, file, "company", company.id)
    old_path = company.profile_pic_path
    try:
        mongo.update(db, "companies", company.id, {"profile_pic_path": new_path})
    except Exception:
        delete_upload(db, new_path)
        raise
    delete_upload(db, old_path)
    return PictureResponse(profile_pic_url=public_url(new_path))


# Declared AFTER the /me routes on purpose (see the note at the top of this file).
@router.get("/{company_id}", response_model=CompanyPublic, summary="View any company's public profile")
def get_company(company_id: int, identity: Identity = Depends(get_identity), db: Database = Depends(get_db)):
    company = mongo.get(db, "companies", company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return CompanyPublic.from_company(company)