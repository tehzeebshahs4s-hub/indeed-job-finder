from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_debug: bool = True

    database_url: str = "sqlite:///./indeed.db"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080

    scraper_headless: bool = True
    scraper_min_delay: int = 3
    scraper_max_delay: int = 8
    scraper_cache_ttl_seconds: int = 3600
    scraper_timeout_seconds: int = 30
    # Set to false on low-memory (free) tiers where Chromium cannot run;
    # the app then serves results from the legal API fallbacks only.
    indeed_enabled: bool = True

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "us"
    jooble_api_key: str = ""
    jooble_country_domain: str = "jooble.org"

    two_captcha_key: str = ""
    captcha_daily_limit: int = 50

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
