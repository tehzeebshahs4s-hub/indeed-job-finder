def test_search_renders_results(client):
    r = client.get("/search", params={"q": "python", "l": "remote"})
    assert r.status_code == 200
    assert "python Developer" in r.text
    assert "TestCo" in r.text
    assert "badge-indeed" in r.text


def test_htmx_search_returns_partial(client):
    r = client.get("/search", params={"q": "dev"}, headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert 'id="results"' in r.text


def test_empty_query_renders_placeholder(client):
    r = client.get("/search")
    assert r.status_code == 200
    assert "No jobs found" in r.text or "results" in r.text


def test_job_detail(client):
    client.get("/search", params={"q": "golang"})
    r = client.get("/jobs/1")
    assert r.status_code == 200
    assert "golang Developer" in r.text


def test_job_detail_404(client):
    assert client.get("/jobs/999999").status_code == 404


def test_api_jobs_returns_json(client):
    r = client.get("/api/jobs", params={"q": "rust"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data and data[0]["title"] == "rust Developer"


def test_search_error_state(client, monkeypatch):
    from app.scraper.router import NoSourceAvailable

    def fail(db, k, l, p, **kw):
        raise NoSourceAvailable("all sources failed")

    monkeypatch.setattr("app.routers.jobs.source_router.fetch_jobs", fail)
    r = client.get("/search", params={"q": "x"})
    assert r.status_code == 200
    assert "No results right now" in r.text
