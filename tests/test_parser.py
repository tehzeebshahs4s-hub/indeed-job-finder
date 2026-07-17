from pathlib import Path

from app.scraper.parser import parse_search_html

FIXTURE = Path(__file__).parent / "fixtures" / "indeed_search.html"


def test_parses_complete_jobs():
    jobs = parse_search_html(FIXTURE.read_text(encoding="utf-8"))
    assert len(jobs) == 2  # third card has no title -> skipped


def test_extracts_core_fields():
    jobs = parse_search_html(FIXTURE.read_text(encoding="utf-8"))
    first = jobs[0]
    assert first.source == "indeed"
    assert first.source_key == "aa111"
    assert first.title == "Senior Python Developer"
    assert first.company == "Acme Corp"
    assert "New York" in first.location
    assert first.salary and "$" in first.salary
    assert first.url and first.url.startswith("https://www.indeed.com")
    assert first.posted_at is not None


def test_dedupes_by_source_key():
    html = FIXTURE.read_text(encoding="utf-8")
    doubled = html + html
    jobs = parse_search_html(doubled)
    keys = {j.source_key for j in jobs}
    assert keys == {"aa111", "bb222"}


def test_empty_html_returns_empty():
    assert parse_search_html("<html></html>") == []


def test_missing_title_card_is_skipped():
    html = """
    <div class="job_seen_beacon" data-jk="x1">
      <h2 class="jobTitle">New</h2>
      <span class="companyName">NoTitle Inc</span>
    </div>"""
    assert parse_search_html(html) == []
