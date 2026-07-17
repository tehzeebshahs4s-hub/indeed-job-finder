from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field


class RawJob(BaseModel):
    """Source-agnostic job record produced by every fetcher."""

    source: str
    source_key: str
    title: str
    company: str | None = None
    location: str | None = None
    salary: str | None = None
    summary: str | None = None
    description: str | None = None
    url: str | None = None
    posted_at: datetime | None = None


class FetchResult(BaseModel):
    source: str
    total: int = 0
    page: int = 0
    jobs: list[RawJob] = Field(default_factory=list)


class JobFetcher(ABC):
    name: ClassVar[str]

    @abstractmethod
    def fetch(self, keyword: str, location: str, page: int) -> FetchResult:
        """Return normalized jobs for one page. Raise exceptions.* on failure."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return False if credentials are missing (skip this source)."""
        return True
