from __future__ import annotations

import httpx

from app.config import settings
from app.scraper.base import FetchResult, JobFetcher, RawJob
from app.scraper.exceptions import FetchError, NotConfigured

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
RESULTS_PER_PAGE = 10


class AdzunaFetcher(JobFetcher):
    name = "adzuna"

    def is_configured(self) -> bool:
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    def fetch(self, keyword: str, location: str, page: int) -> FetchResult:
        if not self.is_configured():
            raise NotConfigured("Adzuna credentials missing")

        # Adzuna pages are 1-indexed.
        adzuna_page = max(page, 0) + 1
        params = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": keyword,
            "where": location,
            "content-type": "application/json",
        }

        url = f"{BASE_URL}/{settings.adzuna_country}/search/{adzuna_page}"
        try:
            resp = httpx.get(url, params=params, timeout=settings.scraper_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"Adzuna request failed: {exc}") from exc

        jobs: list[RawJob] = []
        for item in data.get("results", []):
            salary = _format_salary(item.get("salary_min"), item.get("salary_max"))
            company = item.get("company")
            company_name = company.get("display_name") if isinstance(company, dict) else company
            location_obj = item.get("location")
            location_name = (
                location_obj.get("display_name") if isinstance(location_obj, dict) else location_obj
            )
            jobs.append(
                RawJob(
                    source=self.name,
                    source_key=str(item.get("id")),
                    title=item.get("title", "Untitled"),
                    company=company_name,
                    location=location_name,
                    salary=salary,
                    summary=_truncate(item.get("description", "")),
                    description=item.get("description"),
                    url=item.get("redirect_url"),
                    posted_at=item.get("created"),
                )
            )

        return FetchResult(source=self.name, total=data.get("count", len(jobs)), page=page, jobs=jobs)


def _format_salary(lo, hi) -> str | None:
    if not lo and not hi:
        return None
    if lo and hi and lo != hi:
        return f"${int(lo):,} - ${int(hi):,}"
    val = hi or lo
    return f"${int(val):,}" if val else None


def _truncate(text: str, limit: int = 280) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "\u2026"
