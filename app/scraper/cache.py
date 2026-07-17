from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import SearchCache
from app.scraper.base import FetchResult


def query_hash(keyword: str, location: str, page: int) -> str:
    raw = f"{keyword.strip().lower()}|{location.strip().lower()}|{page}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(db: Session, keyword: str, location: str, page: int) -> FetchResult | None:
    qh = query_hash(keyword, location, page)
    row = db.query(SearchCache).filter(SearchCache.query_hash == qh).first()
    if not row:
        return None
    created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
    if datetime.now(timezone.utc) - created > timedelta(seconds=settings.scraper_cache_ttl_seconds):
        return None
    return FetchResult.model_validate_json(row.payload)


def store(
    db: Session, keyword: str, location: str, page: int, result: FetchResult
) -> None:
    qh = query_hash(keyword, location, page)
    payload = result.model_dump_json()
    row = db.query(SearchCache).filter(SearchCache.query_hash == qh).first()
    if row:
        row.payload = payload
        row.source = result.source
        row.created_at = datetime.now(timezone.utc)
    else:
        db.add(
            SearchCache(
                query_hash=qh,
                keyword=keyword,
                location=location,
                page=page,
                source=result.source,
                payload=payload,
            )
        )
    db.commit()
