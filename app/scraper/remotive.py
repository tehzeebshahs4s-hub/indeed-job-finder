from __future__ import annotations

from datetime import datetime

import httpx

from app.config import settings
from app.scraper.base import FetchResult, JobFetcher, RawJob
from app.scraper.exceptions import FetchError

BASE_URL = "https://www.arbeitnow.com/api/job-board-api"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class ArbeitnowFetcher(JobFetcher):
    """Free public job board API — no key required. Guarantees results out of the box."""

    name = "arbeitnow"

    def is_configured(self) -> bool:
        return True

    def fetch(self, keyword: str, location: str, page: int) -> FetchResult:
        params = {}
        if page > 0:
            params["page"] = page + 1
        try:
            resp = httpx.get(
                BASE_URL,
                params=params,
                timeout=settings.scraper_timeout_seconds,
                headers={"User-Agent": UA, "Accept": "application/json"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"Arbeitnow request failed: {exc}") from exc

        kw = keyword.strip().lower()
        loc = location.strip().lower()
        jobs: list[RawJob] = []
        for item in data.get("data", []):
            title = item.get("title", "Untitled")
            job_loc = item.get("location") or ("Remote" if item.get("remote") else None)
            tags = [t.lower() for t in item.get("tags", [])]
            # client-side keyword/location filtering (API has no query params)
            if kw and kw not in title.lower() and not any(kw in t for t in tags):
                continue
            if loc and loc not in ("remote",) and job_loc and loc not in job_loc.lower():
                continue
            salary = ", ".join(item.get("job_types", [])[:3]) or None
            desc = item.get("description") or None
            jobs.append(
                RawJob(
                    source=self.name,
                    source_key=item.get("slug") or str(item.get("id", "")),
                    title=title,
                    company=item.get("company_name"),
                    location=job_loc,
                    salary=salary if salary else None,
                    summary=", ".join(item.get("tags", [])[:6]) or None,
                    description=desc,
                    url=item.get("url"),
                    posted_at=_parse(item.get("created_at")),
                )
            )

        meta = data.get("meta", {})
        total = meta.get("total", len(jobs)) if isinstance(meta, dict) else len(jobs)
        return FetchResult(source=self.name, total=total, page=page, jobs=jobs)


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None