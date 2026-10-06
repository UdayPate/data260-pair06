"""
Authentication endpoints: signup (student / company), login, logout, who-am-I.

Error codes used:
    409 Conflict       = that email is already registered
    401 Unauthorized   = wrong email or password
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.deps import Identity, get_identity
from ..core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from ..database import get_db
from ..models import Company, Student
from ..schemas.auth import (CompanySignup, LoginRequest, MeResponse, MessageResponse,
                            StudentSignup, TokenResponse)

router = APIRouter(prefix="/auth", tags=["Authentication"])

EMAIL_TAKEN = "An account with this email already exists"


def _token_response(role: str, user) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, role),
        role=role, user_id=user.id, name=user.name,
    )


def _save_new_account(db: Session, account) -> None:
    """Insert a new student/company. The email column is UNIQUE, so if two signups
    race each other the database itself rejects the second one."""
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    db.refresh(account)


@router.post("/student/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a student account")
def student_signup(body: StudentSignup, db: Session = Depends(get_db)):
    if db.scalar(select(Student.id).where(Student.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    student = Student(
        name=body.name, email=body.email, college=body.college,
        password_hash=hash_password(body.password),
    )
    _save_new_account(db, student)
    return _token_response("student", student)


@router.post("/company/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a company account")
def company_signup(body: CompanySignup, db: Session = Depends(get_db)):
    if db.scalar(select(Company.id).where(Company.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    company = Company(
        name=body.name, email=body.email, city=body.location,
        password_hash=hash_password(body.password),
    )
    _save_new_account(db, company)
    return _token_response("company", company)


@router.post("/login", response_model=TokenResponse, summary="Sign in as a student or company")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    model = Student if body.role == "student" else Company
    user = db.scalar(select(model).where(model.email == body.email))

    # Always run one bcrypt check, even for unknown emails (see DUMMY_HASH in security.py).
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)

    if user is None or not password_ok:
        # Same message for both cases so attackers can't tell which emails exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(body.role, user)


@router.post("/logout", response_model=MessageResponse, summary="Sign out")
def logout(identity: Identity = Depends(get_identity)):
    # JWTs are "stateless": the server keeps no list of active logins, so signing
    # out means the browser deletes its stored token (the React app does this).
    # This endpoint confirms the token was valid and gives the frontend a clear signal.
    return MessageResponse(message="Signed out. Discard the token on the client.")


@router.get("/me", response_model=MeResponse, summary="Who is the current user?")
def me(identity: Identity = Depends(get_identity)):
    user = identity.user
    return MeResponse(role=identity.role, id=user.id, name=user.name, email=user.email)