from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    source: Literal["tc", "hanabi"]
    title: str
    url: str
    start_date: date | None = None
    end_date: date | None = None
    times: str | None = None        # "HH:MM-HH:MM" ou "HH:MM"
    venue: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price: str | None = None
    attributes: dict = Field(default_factory=dict)
    created_at: datetime
