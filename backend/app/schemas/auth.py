"""
Pydantic schemas = the SHAPE and RULES of data going in and out of the API.
If a request breaks a rule, FastAPI automatically replies 422 (Unprocessable
Entity) with a message saying which field is wrong, before any of our code runs.
This is how we "validate every input".
"""
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

# A string with leading/trailing spaces removed, 1-100 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _validate_email(value: str) -> str:
    value = value.strip().lower()  # emails are case-insensitive: store one form
    if len(value) > 255:
        raise ValueError("Email is too long")
    return value


def _validate_new_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(value.encode("utf-8")) > 72:
        # bcrypt only reads the first 72 bytes, so longer passwords are rejected
        raise ValueError("Password must be at most 72 bytes long")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


class StudentSignup(BaseModel):
    name: Name
    email: EmailStr
    password: str
    college: Name = Field(description="College name, e.g. San Jose State University")

    _email = field_validator("email")(_validate_email)
    _password = field_validator("password")(_validate_new_password)


class CompanySignup(BaseModel):
    name: Name = Field(description="Company name")
    email: EmailStr
    password: str
    location: Name = Field(description="City where the company is based, e.g. San Jose")

    _email = field_validator("email")(_validate_email)
    _password = field_validator("password")(_validate_new_password)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    role: Literal["student", "company"]

    _email = field_validator("email")(_validate_email)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["student", "company"]
    user_id: int
    name: str


class MeResponse(BaseModel):
    role: Literal["student", "company"]
    id: int
    name: str
    email: str


class MessageResponse(BaseModel):
    message: str