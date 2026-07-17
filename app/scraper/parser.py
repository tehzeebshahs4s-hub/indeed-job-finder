from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.scraper.base import RawJob

BASE_URL = "https://www.indeed.com"

# Selector candidates, tried in order. Indeed changes markup frequently.
CARD_SELECTORS = [
    "div.job_seen_beacon",
    "div.slider_item",
    "div.result",
    "[data-jk]",
]
TITLE_SELECTORS = ["a.jcs-JobTitle", "h2.jobTitle a", "h2.jobTitle", "a[data-jk]"]
COMPANY_SELECTORS = [
    '[data-testid="company-name"]',
    "span.companyName",
    "div.company",
    "a.companyName",
]
LOCATION_SELECTORS = [
    '[data-testid="text-location"]',
    "div.companyLocation",
    "span.companyLocation",
    '[data-testid="job-location"]',
]
SALARY_SELECTORS = [
    ".salary-snippet",
    '[data-testid="salary-snippet"]',
    ".metadata.salary-snippet-container",
    "div.attribute_snippet_wrapper",
]
SUMMARY_SELECTORS = [
    "div.job-snippet",
    '[data-testid="result-snippet"]',
    ".result-content",
    "div.summary",
]
DATE_SELECTORS = [
    '[data-testid="myTime-date"]',
    "span.date",
    ".result-link-bar-container span.date",
    "span.date.new",
]

_JK_RE = re.compile(r"[?&]jk=([a-f0-9]+)")
_SALARY_RE = re.compile(r"(\$[\d,]+\s*(?:-|\s+to\s+)\$?[\d,]+|\$[\d,]+)", re.I)


def parse_search_html(html: str, source: str = "indeed") -> list[RawJob]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(", ".join(CARD_SELECTORS))

    seen: set[str] = set()
    jobs: list[RawJob] = []

    for card in cards:
        job = _parse_card(card, source)
        if not job or job.source_key in seen:
            continue
        seen.add(job.source_key)
        jobs.append(job)

    return jobs


def _parse_card(card, source: str) -> RawJob | None:
    title, link, jk = _extract_title_and_key(card)
    if not title or not jk:
        return None

    company = _first_text(card, COMPANY_SELECTORS)
    location = _first_text(card, LOCATION_SELECTORS)
    salary = _first_text(card, SALARY_SELECTORS) or _guess_salary(card)
    summary = _first_text(card, SUMMARY_SELECTORS)
    posted_label = _first_text(card, DATE_SELECTORS)
    posted_at = _parse_relative_date(posted_label)

    url = BASE_URL + link if link and link.startswith("/") else (link or None)

    return RawJob(
        source=source,
        source_key=jk,
        title=title.strip(),
        company=_clean(company),
        location=_clean(location),
        salary=_clean(salary),
        summary=_clean(summary),
        url=url,
        posted_at=posted_at,
    )


def _extract_title_and_key(card) -> tuple[str | None, str | None, str | None]:
    for sel in TITLE_SELECTORS:
        node = card.select_one(sel)
        if node and node.get_text(strip=True) and node.get_text(strip=True).lower() != "new":
            href = node.get("href") if node.name == "a" else None
            jk = _extract_jk(card, node, href)
            return node.get_text(strip=True), href, jk
    return None, None, None


def _extract_jk(card, node, href) -> str | None:
    jk = card.get("data-jk") or node.get("data-jk")
    if jk:
        return jk
    for target in (href, card.get("data-empn")):
        if target and (m := _JK_RE.search(str(target))):
            return m.group(1)
        if target:
            parsed = urlparse(str(target))
            qs = parse_qs(parsed.query)
            if qs.get("jk"):
                return qs["jk"][0]
    return None


def _first_text(card, selectors: list[str]) -> str | None:
    for sel in selectors:
        node = card.select_one(sel)
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return None


def _guess_salary(card) -> str | None:
    text = card.get_text(" ", strip=True)
    m = _SALARY_RE.search(text)
    return m.group(1) if m else None


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.split()) or None


def _parse_relative_date(label: str | None) -> datetime | None:
    if not label:
        return None
    label = label.lower().replace("posted", "").replace("active", "").strip()
    now = datetime.now(timezone.utc)
    m = re.search(r"(\d+)\s*day", label)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*hour", label)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"just\s*now|today", label)
    if m:
        return now
    return None
