"""Generate the static job board (index.html + jobs.json) for GitHub Pages.

Run locally for testing:
    python generate_static.py
Outputs into ./dist/
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.database import SessionLocal, init_db
from app.scraper import router as source_router
from app.scraper.indeed import IndeedFetcher
from app.scraper.router import NoSourceAvailable

# Indeed-only. Run this from a residential IP (your machine) — Indeed blocks
# datacenter IPs (GitHub Actions runners), so scraping must happen locally.
SEED_SEARCHES = [
    ("python developer", "remote"),
    ("frontend developer", "remote"),
    ("data analyst", "remote"),
    ("software engineer", "remote"),
    ("backend developer", "remote"),
    ("full stack developer", "remote"),
    ("devops engineer", "remote"),
    ("react developer", "remote"),
]


def collect_jobs() -> tuple[list[dict], str]:
    init_db()
    db = SessionLocal()
    seen: set[str] = set()
    all_jobs: list[dict] = []
    source_used = "indeed"
    indeed_only = [IndeedFetcher()]
    try:
        for keyword, location in SEED_SEARCHES:
            try:
                result = source_router.fetch_jobs(
                    db, keyword, location, 0, use_cache=False, sources=indeed_only
                )
            except NoSourceAvailable:
                continue
            source_used = result.source
            for j in result.jobs:
                uid = f"{j.source}:{j.source_key}"
                if uid in seen:
                    continue
                seen.add(uid)
                all_jobs.append(_serialize(j))
            if len(all_jobs) >= 120:
                break
    finally:
        db.close()
    return all_jobs, source_used


def _serialize(raw) -> dict:
    return {
        "source": raw.source,
        "title": raw.title,
        "company": raw.company,
        "location": raw.location,
        "salary": raw.salary,
        "summary": raw.summary,
        "url": raw.url,
        "posted_at": raw.posted_at.isoformat() if raw.posted_at else None,
    }


def render_html(jobs: list[dict], source: str, out: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    items_html = "\n".join(_card(j) for j in jobs) or "<p class='muted'>No jobs found.</p>"
    html = PAGE_TEMPLATE.replace("{{JOBS}}", items_html).replace("{{SOURCE}}", source).replace("{{UPDATED}}", now)
    out.write_text(html, encoding="utf-8")


def _card(j: dict) -> str:
    import html as h

    title = h.escape(j["title"] or "Untitled")
    company = h.escape(j.get("company") or "Unknown company")
    loc = h.escape(j.get("location") or "n/a")
    salary = f'<div class="salary">{h.escape(j["salary"])}</div>' if j.get("salary") else ""
    summary = f'<div class="summary">{h.escape(j["summary"][:180])}…</div>' if j.get("summary") else ""
    url = j.get("url") or "#"
    badge = j.get("source", "")
    badge_cls = f"badge-{badge}" if badge else ""
    return f"""<a class="card" href="{h.escape(url)}" target="_blank" rel="noopener">
  <div class="title">{title} <span class="badge {badge_cls}">{h.escape(badge)}</span></div>
  <div class="meta">{company} · {loc}</div>
  {salary}{summary}
</a>"""


PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Remote Job Finder</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f7f9;color:#1a1a1a}
.navbar{display:flex;align-items:center;justify-content:space-between;padding:0 1.5rem;height:60px;background:#fff;border-bottom:1px solid #e2e5ea;position:sticky;top:0;z-index:10}
.brand{font-weight:700;font-size:1.2rem;text-decoration:none;color:#1a1a1a}
.badge,.src{display:inline-block;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;background:#eef1f5;border:1px solid #e2e5ea;padding:.15rem .45rem;border-radius:999px;color:#6b7280;margin-left:.4rem}
.src{padding:.3rem .6rem}
.container{max-width:960px;margin:0 auto;padding:2rem 1.5rem}
.search{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
.search input{flex:1;min-width:160px;padding:.7rem .9rem;font-size:1rem;border:1px solid #e2e5ea;border-radius:10px}
button{border:1px solid #2557d6;background:#2557d6;color:#fff;padding:.7rem 1.2rem;border-radius:10px;font-size:1rem;cursor:pointer;font-family:inherit}
button:hover{background:#1c44a8}
.count{color:#6b7280;font-size:.9rem;margin-bottom:1.25rem}
.updated{color:#999;font-size:.78rem;margin-bottom:1.5rem}
.card{display:block;background:#fff;border:1px solid #e2e5ea;border-radius:10px;padding:1rem 1.25rem;margin-bottom:.75rem;color:inherit;text-decoration:none}
.card:hover{border-color:#2557d6}
.title{font-weight:600;font-size:1.05rem}
.badge-indeed{color:#2557d6}.badge-arbeitnow{color:#1a7f37}.badge-adzuna{color:#9c27b0}.badge-jooble{color:#1a7f37}
.meta{color:#6b7280;font-size:.9rem;margin:.15rem 0}
.salary{color:#1a7f37;font-size:.9rem}
.summary{color:#555;font-size:.88rem;margin-top:.2rem}
.footer{text-align:center;color:#6b7280;padding:2rem}
</style>
</head><body>
<nav class="navbar"><a class="brand" href="/">Remote Job Finder</a><span class="src" id="src">via loading…</span></nav>
<main class="container">
  <div class="search">
    <input id="q" placeholder="Filter by title or company…" oninput="filterJobs()">
    <button onclick="filterJobs()">Filter</button>
  </div>
  <div class="count" id="count"></div>
  <div class="updated">Last updated: {{UPDATED}}</div>
  <div id="results">{{JOBS}}</div>
</main>
<footer class="footer"><small>Jobs from Indeed (scraped daily via GitHub Actions) + legal job APIs. Auto-refreshed on schedule.</small></footer>
<script>
const ALL = document.querySelectorAll('#results .card');
document.getElementById('src').textContent = 'via {{SOURCE}}';
function filterJobs(){
  const q = document.getElementById('q').value.toLowerCase().trim();
  let shown = 0;
  ALL.forEach(c => {
    const text = (c.textContent || '').toLowerCase();
    const match = !q || text.includes(q);
    c.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  document.getElementById('count').textContent = shown + (shown === 1 ? ' job' : ' jobs');
}
filterJobs();
</script>
</body></html>"""


def main() -> None:
    dist = Path("dist")
    dist.mkdir(exist_ok=True)
    jobs, source = collect_jobs()
    print(f"collected {len(jobs)} jobs from {source}")
    (dist / "jobs.json").write_text(json.dumps({"jobs": jobs, "source": source}, indent=2), encoding="utf-8")
    render_html(jobs, source, dist / "index.html")
    (dist / ".nojekyll").write_text("", encoding="utf-8")  # serve raw on GitHub Pages
    print(f"wrote {dist/'index.html'}, {dist/'jobs.json'}, and .nojekyll")


if __name__ == "__main__":
    main()