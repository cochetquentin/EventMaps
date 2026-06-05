from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from models.event import Event


@dataclass
class ScrapeReport:
    source: str
    links_seen: int = 0
    events_ok: int = 0
    events_skipped: int = 0
    errors: list[dict] = field(default_factory=list)  # [{"url": ..., "reason": ...}]
    duration_s: float | None = None  # wall-clock seconds for the scrape() call

    @property
    def error_rate(self) -> float:
        if self.links_seen == 0:
            return 0.0
        return (self.events_skipped + len(self.errors)) / self.links_seen


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self) -> tuple[list[Event], ScrapeReport]:
        """Scrape all events and return a list of canonical Event objects with a report."""
        ...
