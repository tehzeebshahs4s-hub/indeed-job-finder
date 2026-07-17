from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    keyword: str = Field(default="", max_length=255)
    location: str = Field(default="", max_length=255)
    page: int = Field(default=0, ge=0)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
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
    is_favorite: bool = False


class SearchResults(BaseModel):
    keyword: str
    location: str
    page: int
    source: str  # which source actually produced results
    total: int
    jobs: list[JobOut]
