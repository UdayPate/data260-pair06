"""
Authentication endpoints: signup (student / company), login, logout, who-am-I.

Error codes used:
    409 Conflict       = that email is already registered
    401 Unauthorized   = wrong email or password
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import documents, mongo
from ..core.deps import Identity, get_identity
from ..core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from ..core.sessions import create_session, end_session
from ..mongo import Doc, get_db
from ..schemas.auth import (CompanySignup, LoginRequest, MeResponse, MessageResponse,
                            StudentSignup, TokenResponse)
from ..services.activity_log import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])

EMAIL_TAKEN = "An account with this email already exists"


def _token_response(db: Database, role: str, user: Doc) -> TokenResponse:
    """Start a session (a document in MongoDB) and sign a token that points at it."""
    session_id = create_session(db, role, user.id)
    return TokenResponse(
        access_token=create_access_token(user.id, role, session_id),
        role=role, user_id=user.id, name=user.name,
    )


def _save_new_account(db: Database, collection: str, document: dict) -> Doc:
    """Insert a new student/company. The email has a UNIQUE index, so if two signups
    race each other the database itself rejects the second one."""
    try:
        return mongo.insert(db, collection, document)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)


@router.post("/student/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a student account")
def student_signup(body: StudentSignup, db: Database = Depends(get_db)):
    if mongo.find_one(db, "students", {"email": body.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    student = _save_new_account(db, "students", documents.student(
        name=body.name, email=body.email, college=body.college,
        password_hash=hash_password(body.password),
    ))
    log_activity(db, "student", student.id, "signup")
    return _token_response(db, "student", student)


@router.post("/company/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a company account")
def company_signup(body: CompanySignup, db: Database = Depends(get_db)):
    if mongo.find_one(db, "companies", {"email": body.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    company = _save_new_account(db, "companies", documents.company(
        name=body.name, email=body.email, city=body.location,
        password_hash=hash_password(body.password),
    ))
    log_activity(db, "company", company.id, "signup")
    return _token_response(db, "company", company)


@router.post("/login", response_model=TokenResponse, summary="Sign in as a student or company")
def login(body: LoginRequest, db: Database = Depends(get_db)):
    collection = "students" if body.role == "student" else "companies"
    user = mongo.find_one(db, collection, {"email": body.email})

    # Always run one bcrypt check, even for unknown emails (see DUMMY_HASH in security.py).
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)

    if user is None or not password_ok:
        # Same message for both cases so attackers can't tell which emails exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    log_activity(db, body.role, user.id, "login")
    return _token_response(db, body.role, user)


@router.post("/logout", response_model=MessageResponse, summary="Sign out")
def logout(identity: Identity = Depends(get_identity), db: Database = Depends(get_db)):
    # Lab 2: the login is a session document in MongoDB. Deleting it makes this token useless at once,
    # even if someone copied it. The browser should also discard its stored token (the React app does).
    end_session(db, identity.session_id)
    log_activity(db, identity.role, identity.user.id, "logout")
    return MessageResponse(message="Signed out. Discard the token on the client.")


@router.get("/me", response_model=MeResponse, summary="Who is the current user?")
def me(identity: Identity = Depends(get_identity)):
    user = identity.user
    return MeResponse(role=identity.role, id=user.id, name=user.name, email=user.email)