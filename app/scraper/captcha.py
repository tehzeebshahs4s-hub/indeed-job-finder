from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import httpx

from app.config import settings
from app.scraper.exceptions import ScraperError

logger = logging.getLogger(__name__)

IN_URL = "https://2captcha.com/in.php"
RES_URL = "https://2captcha.com/res.php"
USAGE_FILE = Path("captcha_usage.json")

POLL_INTERVAL = 5
POLL_TIMEOUT = 180  # seconds

# Regexes to find sitekeys in a challenge page.
SITEKEY_RE = re.compile(r"data-sitekey=['\"]([0-9a-zA-Z_-]+)['\"]", re.I)


def detect_challenge(html: str) -> tuple[str, str] | None:
    """Return (challenge_type, sitekey) if a solvable challenge is found, else None."""
    m = SITEKEY_RE.search(html)
    if not m:
        return None
    sitekey = m.group(1)
    lowered = html.lower()
    if "turnstile" in lowered:
        return "turnstile", sitekey
    if "hcaptcha" in lowered or "h-captcha" in lowered:
        return "hcaptcha", sitekey
    return "recaptcha", sitekey


class CaptchaSolver:
    """2Captcha client with a per-day solve budget to cap spending."""

    def __init__(self, api_key: str | None = None, daily_limit: int | None = None) -> None:
        self.api_key = api_key or settings.two_captcha_key
        self.daily_limit = daily_limit if daily_limit is not None else settings.captcha_daily_limit

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def solve_recaptcha(self, sitekey: str, pageurl: str) -> str:
        return self._solve(method="userrecaptcha", sitekey=sitekey, pageurl=pageurl)

    def solve_hcaptcha(self, sitekey: str, pageurl: str) -> str:
        return self._solve(method="hcaptcha", sitekey=sitekey, pageurl=pageurl)

    def solve_turnstile(self, sitekey: str, pageurl: str) -> str:
        return self._solve(method="turnstile", sitekey=sitekey, pageurl=pageurl)

    def _solve(self, method: str, sitekey: str, pageurl: str) -> str:
        if not self.is_configured():
            raise ScraperError("2Captcha key not configured")
        if _today_count() >= self.daily_limit:
            raise ScraperError(f"Captcha daily limit reached ({self.daily_limit})")

        logger.info("Submitting %s captcha to 2Captcha", method)
        resp = httpx.get(
            IN_URL,
            params={"key": self.api_key, "method": method, "sitekey": sitekey, "pageurl": pageurl, "json": 1},
            timeout=30,
        )
        data = resp.json()
        if data.get("status") != 1:
            raise ScraperError(f"2Captcha submit failed: {data.get('request')}")

        captcha_id = data["request"]
        _increment_count()
        token = self._poll(captcha_id)
        logger.info("Captcha solved (id=%s)", captcha_id)
        return token

    def _poll(self, captcha_id: str) -> str:
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            resp = httpx.get(
                RES_URL,
                params={"key": self.api_key, "action": "get", "id": captcha_id, "json": 1},
                timeout=30,
            )
            data = resp.json()
            if data.get("status") == 1:
                return data["request"]
            if data.get("request") != "CAPCHA_NOT_READY":
                raise ScraperError(f"2Captcha error: {data.get('request')}")
        raise ScraperError("2Captcha timed out waiting for solution")


def _today_count() -> int:
    data = _read_usage()
    return data.get(str(date.today()), 0)


def _increment_count() -> None:
    data = _read_usage()
    key = str(date.today())
    data[key] = data.get(key, 0) + 1
    try:
        USAGE_FILE.write_text(json.dumps(data))
    except OSError:
        logger.warning("could not persist captcha usage")


def _read_usage() -> dict:
    try:
        return json.loads(USAGE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
