from __future__ import annotations

from abc import ABC, abstractmethod

from models.event import Event


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self) -> list[Event]:
        """Scrape all events and return a list of canonical Event objects."""
        ...
