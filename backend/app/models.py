"""
Database tables for the Handshake clone, defined as SQLAlchemy ORM classes.
Each class = one MySQL table. Base.metadata.create_all() builds them all.
"""
import enum
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------- Enums (fixed sets of allowed values) ----------
class JobCategory(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    on_campus = "on_campus"
    internship = "internship"


class PayPeriod(str, enum.Enum):
    hourly = "hourly"
    yearly = "yearly"


class ApplicationStatus(str, enum.Enum):
    pending = "Pending"
    reviewed = "Reviewed"
    declined = "Declined"


class SavedItemType(str, enum.Enum):
    job = "job"
    event = "event"


def enum_column(enum_cls, name):
    """Store the enum's VALUE (e.g. 'Pending') instead of its Python name."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


# ---------- Students ----------
class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    college: Mapped[str] = mapped_column(String(150), index=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    career_objective: Mapped[Optional[str]] = mapped_column(Text)
    degree: Mapped[Optional[str]] = mapped_column(String(100))
    major: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer)
    cgpa: Mapped[Optional[float]] = mapped_column(Float)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    profile_pic_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    skills: Mapped[List["StudentSkill"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    experiences: Mapped[List["StudentExperience"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    applications: Mapped[List["Application"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    preferences: Mapped[Optional["StudentPreference"]] = relationship(back_populates="student", uselist=False, cascade="all, delete-orphan")
    saved_items: Mapped[List["SavedItem"]] = relationship(back_populates="student", cascade="all, delete-orphan")


class StudentSkill(Base):
    __tablename__ = "student_skills"
    __table_args__ = (UniqueConstraint("student_id", "skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(50), index=True)

    student: Mapped["Student"] = relationship(back_populates="skills")


class StudentExperience(Base):
    __tablename__ = "student_experience"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    company: Mapped[str] = mapped_column(String(150))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)  # NULL = current role
    description: Mapped[Optional[str]] = mapped_column(Text)

    student: Mapped["Student"] = relationship(back_populates="experiences")


class StudentPreference(Base):
    """Saved job/event preferences. Read by the assistant's get_student_preferences tool."""
    __tablename__ = "student_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), unique=True)
    preferred_categories: Mapped[Optional[list]] = mapped_column(JSON)  # e.g. ["internship"]
    preferred_cities: Mapped[Optional[list]] = mapped_column(JSON)      # e.g. ["San Jose"]
    preferred_roles: Mapped[Optional[list]] = mapped_column(JSON)       # e.g. ["Data Analyst"]
    min_hourly_rate: Mapped[Optional[int]] = mapped_column(Integer)     # USD/hour (yearly / 2080)
    open_to_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    event_interests: Mapped[Optional[list]] = mapped_column(JSON)       # e.g. ["Career Fair"]
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    student: Mapped["Student"] = relationship(back_populates="preferences")


# ---------- Companies ----------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    profile_pic_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    jobs: Mapped[List["Job"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    events: Mapped[List["Event"]] = relationship(back_populates="company", cascade="all, delete-orphan")


# ---------- Jobs and applications ----------
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[JobCategory] = mapped_column(enum_column(JobCategory, "job_category"), index=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[Optional[str]] = mapped_column(String(100))
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer)
    pay_period: Mapped[PayPeriod] = mapped_column(enum_column(PayPeriod, "pay_period"))
    posting_date: Mapped[date] = mapped_column(Date)
    deadline: Mapped[date] = mapped_column(Date, index=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="jobs")
    skills: Mapped[List["JobSkill"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[List["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(50), index=True)

    job: Mapped["Job"] = relationship(back_populates="skills")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("student_id", "job_id"),)  # can't apply twice

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_status"), default=ApplicationStatus.pending, index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    student: Mapped["Student"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")


# ---------- Events ----------
class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    event_datetime: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="events")
    eligible_majors: Mapped[List["EventEligibleMajor"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventEligibleMajor(Base):
    """One row per allowed major. A single row with major='All' means open to everyone."""
    __tablename__ = "event_eligible_majors"
    __table_args__ = (UniqueConstraint("event_id", "major"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    major: Mapped[str] = mapped_column(String(100), index=True)

    event: Mapped["Event"] = relationship(back_populates="eligible_majors")


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = (UniqueConstraint("student_id", "event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="registrations")
    event: Mapped["Event"] = relationship(back_populates="registrations")


# ---------- Saved items (written by the assistant's save_job_or_event tool) ----------
class SavedItem(Base):
    """item_id points to jobs.id or events.id depending on item_type, so it has no FK."""
    __tablename__ = "saved_items"
    __table_args__ = (UniqueConstraint("student_id", "item_type", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[SavedItemType] = mapped_column(enum_column(SavedItemType, "saved_item_type"))
    item_id: Mapped[int] = mapped_column(Integer)
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="saved_items")