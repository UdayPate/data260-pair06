"""
Schemas for a student's saved job and event preferences.

These are what the AI assistant reads first ("find me an internship in MY city"), and what the
student edits on their profile page. A student either has saved preferences or does not:
the API says which with  saved: true / false.
"""
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import CITY_SET
from ..models import JobCategory

_CANON_CITIES = {c.lower(): c for c in CITY_SET}
_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &()/.+#\-]*$")

def _clean_list(values: List[str], label: str, canon: Optional[dict] = None,
                limit: int = 10, max_len: int = 100) -> List[str]:
    """Trim, drop blanks and repeats (ignoring case), and reject odd characters."""
    result, seen = [], set()
    for raw in values:
        text = " ".join(raw.split())
        if not text:
            continue
        if len(text) > max_len or not _TEXT_RE.match(text):
            raise ValueError(f"Invalid {label}: {raw!r}")
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append((canon or {}).get(key, text))
    if len(result) > limit:
        raise ValueError(f"At most {limit} {label} entries are allowed")
    return result

class PreferencesIn(BaseModel):
    """Saving REPLACES the whole set, so send every field you want to keep."""
    model_config = ConfigDict(extra="forbid")

    preferred_categories: List[JobCategory] = Field(default_factory=list,
                                                    description="full_time, part_time, on_campus, internship")
    preferred_cities: List[str] = Field(default_factory=list, description="e.g. San Jose")
    preferred_roles: List[str] = Field(default_factory=list, description="e.g. Data Analyst")
    min_hourly_rate: Optional[int] = Field(None, ge=0, le=500, description="Lowest acceptable pay, dollars per hour")
    open_to_remote: bool = True
    event_interests: List[str] = Field(default_factory=list, description="e.g. Career Fair, Tech Talk")

    @field_validator("preferred_categories")
    @classmethod
    def _unique_categories(cls, v):
        return list(dict.fromkeys(v))

    @field_validator("preferred_cities")
    @classmethod
    def _cities(cls, v):
        return _clean_list(v, "city", canon=_CANON_CITIES)

    @field_validator("preferred_roles")
    @classmethod
    def _roles(cls, v):
        return _clean_list(v, "role")

    @field_validator("event_interests")
    @classmethod
    def _interests(cls, v):
        return _clean_list(v, "event interest")

class PreferencesOut(BaseModel):
    saved: bool = Field(description="False when this student has not saved any preferences yet")
    preferred_categories: List[JobCategory]
    preferred_cities: List[str]
    preferred_roles: List[str]
    min_hourly_rate: Optional[int]
    open_to_remote: bool
    event_interests: List[str]
    updated_at: Optional[datetime]