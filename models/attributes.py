from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TokyoCheapoAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")

    categories: list[str] = []
    tags: list[str] = []
    official_link: str | None = None
    location_name: str | None = None
    description: str | None = None


class HanabiWalkerAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")

    fireworks_count: str | None = None
    fireworks_duration: str | None = None
    expected_crowd: str | None = None
    rain_policy: str | None = None
    paid_seating: str | None = None
    paid_seating_details: str | None = None
    food_stalls: str | None = None
    notes: str | None = None
    access: str | None = None
    parking: str | None = None
    official_site: str | None = None
    official_x: str | None = None
    contact: str | None = None
    contact2: str | None = None


class TimeoutTokyoAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")

    categories: list[str] = Field(default_factory=list)
    venue_name: str | None = None
    venue_address: str | None = None
    image_url: str | None = None
    description: str | None = None
