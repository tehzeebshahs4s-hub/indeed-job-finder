from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SearchCache(Base):
    """Raw scraper/API payload cache keyed by (keyword, location, page)."""

    __tablename__ = "search_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    page: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="")  # which source filled this
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
