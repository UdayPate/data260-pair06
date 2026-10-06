"""
"Who is logged in?" helpers, used as FastAPI dependencies.

A dependency is a function FastAPI runs BEFORE your endpoint. Write
    def my_endpoint(student: Student = Depends(require_student)): ...
and FastAPI will first read the Authorization header, verify the token, load the
student from MySQL, and hand it to you. If anything is wrong the request stops
with an error and your endpoint code never runs.

HTTP status codes used here:
    401 Unauthorized = "we don't know who you are" (no token / bad token / expired)
    403 Forbidden    = "we know who you are, but you may not do this" (wrong role)
"""
from dataclasses import dataclass
from typing import Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Company, Student
from .security import decode_access_token

# Makes Swagger UI show an "Authorize" button where you paste a token.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Identity:
    role: str                       # "student" or "company"
    user: Union[Student, Company]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_identity(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Identity:
    """Any logged-in user (student OR company)."""
    if creds is None:
        raise _unauthorized("Missing bearer token")

    payload = decode_access_token(creds.credentials)
    if payload is None:
        raise _unauthorized("Invalid or expired token")

    role = payload.get("role")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise _unauthorized("Invalid token")

    model = {"student": Student, "company": Company}.get(role)
    if model is None:
        raise _unauthorized("Invalid token")

    user = db.get(model, user_id)
    if user is None:  # account was deleted after the token was issued
        raise _unauthorized("Account no longer exists")
    return Identity(role=role, user=user)


def require_student(identity: Identity = Depends(get_identity)) -> Student:
    """Only students may call this endpoint."""
    if identity.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Students only")
    return identity.user


def require_company(identity: Identity = Depends(get_identity)) -> Company:
    """Only companies may call this endpoint."""
    if identity.role != "company":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Companies only")
    return identity.user