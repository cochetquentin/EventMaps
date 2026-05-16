from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class EventBase(BaseModel):
    id: str
    source: str
    title: str
    url: str
    start_date: str          # YYYY/MM/DD
    start_time: str | None = None
    end_time: str | None = None
    lat: float | None = None
    lng: float | None = None
    scraped_at: datetime


class TokyoCheapoEvent(EventBase):
    source: Literal["tc"] = "tc"
    end_date: str | None = None
    price: str | None = None
    categories: list[str] = []
    tags: list[str] = []
    official_link: str | None = None
    location_name: str | None = None


class HanabiEvent(EventBase):
    source: Literal["hanabi"] = "hanabi"
    fireworks_count: str | None = None
    fireworks_duration: str | None = None
    expected_crowd: str | None = None
    rain_policy: str | None = None
    paid_seating: str | None = None
    paid_seating_details: str | None = None
    food_stalls: str | None = None
    notes: str | None = None
    venue: str | None = None
    access: str | None = None
    parking: str | None = None
    official_site: str | None = None
    official_x: str | None = None
    contact: str | None = None
    contact2: str | None = None


Event = Annotated[TokyoCheapoEvent | HanabiEvent, Field(discriminator="source")]
