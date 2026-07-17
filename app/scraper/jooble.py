from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.scraper.base import FetchResult, JobFetcher, RawJob
from app.scraper.exceptions import FetchError, NotConfigured

BASE_URL = "https://{domain}/api/{key}"


class JoobleFetcher(JobFetcher):
    name = "jooble"

    def is_configured(self) -> bool:
        return bool(settings.jooble_api_key)

    def fetch(self, keyword: str, location: str, page: int) -> FetchResult:
        if not self.is_configured():
            raise NotConfigured("Jooble API key missing")

        url = BASE_URL.format(domain=settings.jooble_country_domain, key=settings.jooble_api_key)
        params = {
            "keywords": keyword,
            "location": location,
            "page": max(page, 0) + 1,
        }
        try:
            resp = httpx.get(url, params=params, timeout=settings.scraper_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"Jooble request failed: {exc}") from exc

        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            jobs.append(
                RawJob(
                    source=self.name,
                    source_key=str(item.get("id")),
                    title=item.get("title", "Untitled"),
                    company=item.get("company"),
                    location=item.get("location"),
                    salary=item.get("salary") or None,
                    summary=_clean(item.get("snippet")),
                    description=item.get("snippet"),
                    url=item.get("link"),
                    posted_at=_parse_updated(item.get("updated")),
                )
            )

        return FetchResult(
            source=self.name, total=data.get("totalCount", len(jobs)), page=page, jobs=jobs
        )


def _clean(text) -> str | None:
    if not text:
        return None
    return " ".join(str(text).split())


def _parse_updated(value) -> datetime | None:
    if not value:
        return None
    # Jooble returns ISO-ish timestamps; be lenient.
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value)[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
