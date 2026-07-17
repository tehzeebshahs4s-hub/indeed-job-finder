from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus

from app.config import settings
from app.scraper.base import FetchResult, JobFetcher, RawJob
from app.scraper.exceptions import BlockedError, CaptchaEncountered, FetchError, NotConfigured
from app.scraper.parser import parse_search_html

logger = logging.getLogger(__name__)

BASE_URL = "https://www.indeed.com"

# Markers that indicate a CAPTCHA / block page rather than real results.
CAPTCHA_MARKERS = ["g-recaptcha", "h-captcha", "cf-challenge", "are you a human", "verify you are human"]
BLOCK_MARKERS = ["access denied", "you do not have permission", "error 403"]
RESULT_SELECTOR = "div.job_seen_beacon, ul.jobsearch-ResultsList, [data-jk]"


class IndeedFetcher(JobFetcher):
    name = "indeed"

    def is_configured(self) -> bool:
        # Indeed needs a real Chromium browser (heavy). Disable on low-memory tiers.
        return settings.indeed_enabled

    def fetch(self, keyword: str, location: str, page: int) -> FetchResult:
        url = _build_url(keyword, location, page)
        html = _render(url)
        jobs = parse_search_html(html, source=self.name)
        logger.info("Indeed scraped %d jobs for %r/%r page %d", len(jobs), keyword, location, page)
        return FetchResult(source=self.name, total=len(jobs), page=page, jobs=jobs)


def _build_url(keyword: str, location: str, page: int) -> str:
    q = quote_plus(keyword)
    loc = quote_plus(location)
    start = max(page, 0) * 10
    return f"{BASE_URL}/jobs?q={q}&l={loc}&start={start}&from=search"


def _render(url: str) -> str:
    try:
        from playwright.sync_api import Error as PWError, TimeoutError as PWTimeout, sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise NotConfigured(f"Playwright not installed: {exc}") from exc

    # Stealth is optional; degrade silently if unavailable.
    stealth_sync = None
    stealth_config = None
    try:
        from playwright_stealth import StealthConfig, stealth_sync as _stealth_sync

        stealth_sync = _stealth_sync
        stealth_config = StealthConfig()
    except Exception:  # pragma: no cover
        logger.debug("playwright-stealth unavailable, continuing without it")

    # Light random delay to look human.
    time.sleep(random.uniform(settings.scraper_min_delay, settings.scraper_max_delay) * 0.25)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.scraper_headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            try:
                if stealth_sync is not None:
                    stealth_sync(context, config=stealth_config)
            except Exception:  # pragma: no cover - stealth optional
                pass

            page = context.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=settings.scraper_timeout_seconds * 1000)
            if resp is not None and resp.status in (403, 429):
                raise BlockedError(f"Indeed returned HTTP {resp.status}")
            try:
                page.wait_for_selector(RESULT_SELECTOR, timeout=settings.scraper_timeout_seconds * 1000)
            except PWTimeout:
                pass

            html = page.content()
            try:
                _detect_block(html, url)
            except CaptchaEncountered:
                # Try to solve within the live session, then re-check once.
                html = _attempt_captcha_solve(page, context, url, html)
            return html
    except (BlockedError, CaptchaEncountered):
        raise
    except PWError as exc:  # pragma: no cover - environment dependent
        raise FetchError(f"Playwright error: {exc}") from exc
    except Exception as exc:
        raise FetchError(f"Indeed render failed: {exc}") from exc


def _attempt_captcha_solve(page, context, url: str, html: str) -> str:
    """Best-effort solve of an encountered captcha inside the live session."""
    from app.scraper.captcha import CaptchaSolver, detect_challenge

    solver = CaptchaSolver()
    challenge = detect_challenge(html)
    if not challenge or not solver.is_configured():
        raise CaptchaEncountered(f"Unsolvable/uncleared captcha at {url}")

    kind, sitekey = challenge
    logger.info("Attempting to solve %s captcha at %s", kind, url)
    try:
        if kind == "recaptcha":
            token = solver.solve_recaptcha(sitekey, url)
            page.evaluate(
                "(t) => { document.getElementById('g-recaptcha-response').value = t; }", token
            )
        elif kind == "hcaptcha":
            token = solver.solve_hcaptcha(sitekey, url)
            page.evaluate(
                "(t) => { const el = document.querySelector('[name=h-captcha-response]');"
                " if (el) el.value = t; }", token
            )
        else:  # turnstile
            token = solver.solve_turnstile(sitekey, url)
            page.evaluate(
                "(t) => { document.querySelectorAll('input[name=\"cf-turnstile-response\"]').forEach(e => e.value = t); }",
                token,
            )
        # Submit any form, then reload and re-check.
        try:
            page.evaluate("() => { const f = document.querySelector('form'); if (f) f.submit(); }")
        except Exception:
            pass
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except CaptchaEncountered:
        raise
    except Exception as exc:
        raise CaptchaEncountered(f"Captcha solve/inject failed: {exc}") from exc

    new_html = page.content()
    try:
        _detect_block(new_html, url)
    except CaptchaEncountered as exc:
        raise CaptchaEncountered(f"Captcha not cleared after solve: {exc}") from exc
    return new_html


def _detect_block(html: str, url: str) -> None:
    lowered = html.lower()
    if any(marker in lowered for marker in CAPTCHA_MARKERS) and RESULT_SELECTOR.split(",")[0] not in html:
        raise CaptchaEncountered(f"CAPTCHA page detected at {url}")
    if any(marker in lowered for marker in BLOCK_MARKERS) and "job_seen_beacon" not in html:
        raise BlockedError(f"Block page detected at {url}")
