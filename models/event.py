from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from models.attributes import HanabiWalkerAttributes, TimeoutTokyoAttributes, TokyoCheapoAttributes


class Event(BaseModel):
    id: str
    source: Literal["tc", "hanabi", "tot"]
    title: str
    url: str
    start_date: date | None = None
    end_date: date | None = None
    times: str | None = None  # "HH:MM-HH:MM" ou "HH:MM"
    venue: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price: str | None = None
    attributes: TokyoCheapoAttributes | HanabiWalkerAttributes | TimeoutTokyoAttributes
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def coerce_attributes(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        source = data.get("source")
        attrs = data.get("attributes", {})
        if isinstance(attrs, dict):
            if source == "tc":
                data["attributes"] = TokyoCheapoAttributes.model_validate(attrs)
            elif source == "hanabi":
                data["attributes"] = HanabiWalkerAttributes.model_validate(attrs)
            elif source == "tot":
                data["attributes"] = TimeoutTokyoAttributes.model_validate(attrs)
        return data
