# Job Finder (Indeed + fallback APIs)

A small job-board web app that searches jobs across multiple sources:

1. **Indeed** — scraped headlessly with **Playwright** (real browser, bypasses Cloudflare JS challenges).
2. **Adzuna** & **Jooble** — free official REST APIs used as automatic **fallbacks** when Indeed blocks us.

If Indeed returns a CAPTCHA, an optional **2Captcha** integration can auto-solve it (within a daily budget), and if it can't, the request transparently falls through to Adzuna, then Jooble — so the site always returns results.

> **Legal note:** Scraping Indeed violates their Terms of Service. This project is for **personal/educational** use. The legal API fallbacks (Adzuna/Jooble) are the recommended path for any real deployment.

---

## Features

- Keyword + location search with pagination (HTMX-powered, no full page reloads)
- Job detail pages with a link to the original posting
- User accounts (register / login / logout) with JWT cookies
- Save favorite jobs and save searches (per-user)
- Source-agnostic design — every provider normalizes to one `RawJob` schema
- Result caching (TTL-based) to minimize hits to Indeed
- Rate limiting on search endpoints

## Architecture

```
Browser ──▶ FastAPI (Jinja2 + HTMX)
              │
              ├─ app/scraper/router.py   # orchestrates sources + fallback + cache
              │     ├─ IndeedFetcher     # Playwright + BeautifulSoup parser
              │     ├─ AdzunaFetcher     # httpx REST
              │     └─ JoobleFetcher     # httpx REST
              ├─ app/services/jobs.py    # DB upsert / favorites
              └─ SQLAlchemy (SQLite dev / Postgres prod)
```

`app/scraper/router.py` tries each configured source in priority order and falls through on `BlockedError` / `CaptchaEncountered` / `FetchError`, caching the first successful result keyed by `(keyword, location, page)`.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate            # Windows
# source .venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
python -m playwright install chromium   # needed only for the Indeed scraper

cp .env.example .env
```

Register free API keys and fill in `.env`:

| Variable | Where to get it |
|---|---|
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | https://developer.adzuna.com |
| `JOOBLE_API_KEY` | https://jooble.org/api/about |
| `TWO_CAPTCHA_KEY` | https://2captcha.com (optional, paid) |
| `JWT_SECRET` | any long random string |
| `DATABASE_URL` | `sqlite:///./indeed.db` (dev) or Postgres URL (prod) |

## Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

## API

- `GET /api/jobs?q=&l=&page=` → JSON list of jobs
- `POST /auth/register`, `POST /auth/login` → JSON / form auth

## Test

```bash
pytest
```

Tests use a fake job source (no network), covering the parser, auth, search UI, and favorites/saved-searches.

## Docker

```bash
docker compose up --build
# app on :8000, Postgres on :5432
```

## Cloud deploy (recommended home for the full app + Indeed scraping)

The app is configured for **Render** (`render.yaml`), **Fly.io** (`fly.toml`), and **Railway**. Headless Chromium needs ~1 GB RAM, so use a paid/starter instance for Indeed scraping, or set `INDEED_ENABLED=false` on a free tier to run the legal API fallbacks (Adzuna/Jooble) only.

### Render (one-click)
1. Push this repo to GitHub.
2. Go to <https://dashboard.render.com> → **New +** → **Blueprint** → select your repo. Render auto-reads `render.yaml` and provisions a web service + Postgres.
3. In the web service's **Environment**, fill in `JWT_SECRET`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `JOOBLE_API_KEY` (and optionally `TWO_CAPTCHA_KEY`).
4. Deploy. Set your custom domain in Render and point `indeed.s4s.tehzeeb.to...` at it (CNAME), or just use the `*.onrender.com` URL.

### Fly.io
```bash
fly launch            # detects Dockerfile + fly.toml
fly secrets set JWT_SECRET=... ADZUNA_APP_ID=... ADZUNA_APP_KEY=... JOOBLE_API_KEY=...
fly deploy
```

### Pointing your domain
Add a CNAME record for `indeed` → your cloud app's hostname (e.g. `xxx.onrender.com` or `xxx.fly.dev`). Your current Plesk box serves PHP and can't run this Python+Chromium app.

## Configuration

All settings live in `.env` (see `.env.example`). Key scraper knobs:

- `SCRAPER_HEADLESS` — `false` shows the browser (helps debug Cloudflare)
- `SCRAPER_MIN_DELAY` / `SCRAPER_MAX_DELAY` — jitter between requests
- `SCRAPER_CACHE_TTL_SECONDS` — how long cached search results are reused
- `CAPTCHA_DAILY_LIMIT` — hard cap on paid 2Captcha solves per day

## Maintenance

Indeed's HTML markup changes frequently. If scraping returns 0 results, the parser selectors in `app/scraper/parser.py` likely need updating — each selector list has fallbacks, and unit tests in `tests/test_parser.py` + the fixture in `tests/fixtures/` make this easy to verify offline.
