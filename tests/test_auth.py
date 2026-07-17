def test_register_and_me(client):
    r = client.post("/auth/register", json={"email": "a@b.com", "password": "password1"})
    assert r.status_code == 201
    assert r.json()["email"] == "a@b.com"


def test_register_duplicate_rejected(client):
    payload = {"email": "dup@b.com", "password": "password1"}
    client.post("/auth/register", json=payload)
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409


def test_login_sets_cookie(client):
    client.post("/auth/register", json={"email": "log@b.com", "password": "password1"})
    r = client.post("/auth/login", data={"username": "log@b.com", "password": "password1"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "wp@b.com", "password": "password1"})
    r = client.post("/auth/login", data={"username": "wp@b.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401


def test_logout_clears_session(client):
    client.post("/auth/register", json={"email": "out@b.com", "password": "password1"})
    client.post("/auth/login", data={"username": "out@b.com", "password": "password1"})
    assert client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
