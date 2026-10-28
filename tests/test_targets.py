import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
client = TestClient(app)

VALID = {
    "name": "Google",
    "address": "https://google.com",
    "check_type": "http",
    "interval_seconds": 60,
    "warning_ms": 500,
    "critical_ms": 2000,
}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()


def test_create_and_get_target():
    r = client.post("/targets", json=VALID)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert client.get(f"/targets/{tid}").json()["name"] == "Google"


def test_list_targets():
    client.post("/targets", json=VALID)
    r = client.get("/targets")
    assert r.status_code == 200 and len(r.json()) == 1


def test_update_target():
    tid = client.post("/targets", json=VALID).json()["id"]
    changed = {**VALID, "interval_seconds": 120}
    r = client.put(f"/targets/{tid}", json=changed)
    assert r.status_code == 200 and r.json()["interval_seconds"] == 120


def test_delete_target():
    tid = client.post("/targets", json=VALID).json()["id"]
    assert client.delete(f"/targets/{tid}").status_code == 204
    assert client.get(f"/targets/{tid}").status_code == 404


def test_missing_target_returns_404():
    assert client.get("/targets/999").status_code == 404


def test_duplicate_name_returns_409():
    client.post("/targets", json=VALID)
    assert client.post("/targets", json=VALID).status_code == 409


def test_invalid_url_rejected():
    r = client.post("/targets", json={**VALID, "address": "google.com"})
    assert r.status_code == 422


def test_empty_name_rejected():
    r = client.post("/targets", json={**VALID, "name": "   "})
    assert r.status_code == 422


def test_bad_interval_rejected():
    r = client.post("/targets", json={**VALID, "interval_seconds": 2})
    assert r.status_code == 422


def test_warning_must_be_below_critical():
    r = client.post("/targets", json={**VALID, "warning_ms": 3000, "critical_ms": 1000})
    assert r.status_code == 422


def test_ping_target_with_http_prefix_rejected():
    r = client.post(
        "/targets",
        json={**VALID, "name": "Ping1", "check_type": "ping", "address": "http://8.8.8.8"},
    )
    assert r.status_code == 422


def test_valid_ping_target_accepted():
    r = client.post(
        "/targets",
        json={**VALID, "name": "Ping1", "check_type": "ping", "address": "8.8.8.8"},
    )
    assert r.status_code == 201