from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.scraper.adzuna import AdzunaFetcher
from app.scraper.base import FetchResult, JobFetcher
from app.scraper.cache import get_cached, store
from app.scraper.exceptions import BlockedError, FetchError, NotConfigured, ScraperError
from app.scraper.jooble import JoobleFetcher
from app.scraper.remotive import ArbeitnowFetcher

logger = logging.getLogger(__name__)

# Priority order. Indeed is prepended once implemented (Phase 4/5).
# Arbeitnow is free + keyless, so it stays last as a guaranteed fallback.
DEFAULT_SOURCES: list[JobFetcher] = [
    AdzunaFetcher(),
    JoobleFetcher(),
    ArbeitnowFetcher(),
]


def all_sources() -> list[JobFetcher]:
    sources = list(DEFAULT_SOURCES)
    try:
        from app.scraper.indeed import IndeedFetcher

        sources.insert(0, IndeedFetcher())
    except Exception:  # pragma: no cover - optional dependency
        logger.debug("IndeedFetcher unavailable, skipping")
    return sources


class NoSourceAvailable(ScraperError):
    pass


def fetch_jobs(
    db: Session,
    keyword: str,
    location: str,
    page: int,
    *,
    use_cache: bool = True,
    sources: list[JobFetcher] | None = None,
) -> FetchResult:
    if use_cache:
        cached = get_cached(db, keyword, location, page)
        if cached:
            logger.info("cache hit for %r/%r p%s", keyword, location, page)
            return cached

    sources = sources if sources is not None else all_sources()
    errors: list[str] = []

    for source in sources:
        if not source.is_configured():
            continue
        try:
            result = source.fetch(keyword, location, page)
        except BlockedError as exc:
            errors.append(f"{source.name}: blocked ({exc})")
            logger.warning("source %s blocked: %s", source.name, exc)
            continue
        except (FetchError, ScraperError) as exc:
            errors.append(f"{source.name}: {exc}")
            logger.warning("source %s failed: %s", source.name, exc)
            continue

        if result.jobs:
            store(db, keyword, location, page, result)
            return result
        errors.append(f"{source.name}: no results")

    raise NoSourceAvailable("All job sources failed: " + " | ".join(errors))
