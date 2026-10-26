"""Request bodies for notification preferences and messaging."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.common import CamelModel
from app.services.notifications import Category

EmailFrequency = Literal["INSTANT", "DAILY", "OFF"]

_CATEGORY_NAMES = {c.value for c in Category}


class NotificationPreferencesUpdate(CamelModel):
    """Partial update: omitted fields keep their current value."""

    categories: dict[str, bool] | None = None
    email_frequency: EmailFrequency | None = None
    new_applicant_digest: bool | None = None

    @field_validator("categories")
    @classmethod
    def _known_categories(cls, value: dict[str, bool] | None) -> dict[str, bool] | None:
        if value is None:
            return value
        unknown = sorted(k for k in value if k not in _CATEGORY_NAMES)
        if unknown:
            raise ValueError(f"Unknown notification categories: {', '.join(unknown)}")
        return value


class MessageCreate(CamelModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=5000)


class ThreadCreate(MessageCreate):
    """Recruiters supply ``candidateId``; candidates supply ``recruiterId`` (reply only)."""

    candidate_id: uuid.UUID | None = None
    recruiter_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one_counterpart(self) -> "ThreadCreate":
        if (self.candidate_id is None) == (self.recruiter_id is None):
            raise ValueError("Provide exactly one of candidateId or recruiterId")
        return self
