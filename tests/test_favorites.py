def _login(client, email="f@b.com", password="password1"):
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", data={"username": email, "password": password})


def test_favorite_toggle(client):
    _login(client)
    client.get("/search", params={"q": "python"})
    r = client.post("/favorites/1", follow_redirects=False)
    assert r.status_code == 303

    from app.database import SessionLocal
    from app.models import Favorite

    db = SessionLocal()
    assert db.query(Favorite).count() == 1
    db.close()

    # toggle off
    client.post("/favorites/1", follow_redirects=False)
    db = SessionLocal()
    assert db.query(Favorite).count() == 0
    db.close()


def test_favorites_list(client):
    _login(client, email="f2@b.com")
    client.get("/search", params={"q": "python"})
    client.post("/favorites/1", follow_redirects=False)
    r = client.get("/favorites")
    assert r.status_code == 200
    assert "python Developer" in r.text


def test_favorites_require_auth(client):
    assert client.post("/favorites/1", follow_redirects=False).status_code == 401
    assert client.get("/favorites", follow_redirects=False).status_code == 401


def test_save_search(client):
    _login(client, email="f3@b.com")
    r = client.post("/saved-searches", data={"q": "python", "l": "remote"}, follow_redirects=False)
    assert r.status_code == 303
    from app.database import SessionLocal
    from app.models import SavedSearch

    db = SessionLocal()
    assert db.query(SavedSearch).count() == 1
    db.close()


def test_save_search_dedupes(client):
    _login(client, email="f4@b.com")
    for _ in range(2):
        client.post("/saved-searches", data={"q": "python", "l": ""}, follow_redirects=False)
    from app.database import SessionLocal
    from app.models import SavedSearch

    db = SessionLocal()
    assert db.query(SavedSearch).count() == 1
    db.close()


def test_saved_searches_list(client):
    _login(client, email="f5@b.com")
    client.post("/saved-searches", data={"q": "java", "l": ""}, follow_redirects=False)
    r = client.get("/saved-searches")
    assert r.status_code == 200
    assert "java" in r.text
