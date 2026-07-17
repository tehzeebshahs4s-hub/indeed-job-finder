class ScraperError(Exception):
    """Base error for any job source failure."""


class BlockedError(ScraperError):
    """Source is blocking us (anti-bot / rate limit). Try fallback."""


class CaptchaEncountered(BlockedError):
    """Source served a CAPTCHA."""


class NotConfigured(ScraperError):
    """Source has no API key / credentials configured."""


class FetchError(ScraperError):
    """Transient network or parsing error from a source."""
