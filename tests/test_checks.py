import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.checker import check_http, check_ping
from app.services import run_due_checks

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
client = TestClient(app)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(1.5)
        code = 500 if self.path == "/error" else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


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


def make_target(name, address, **extra):
    body = {"name": name, "address": address, "check_type": "http",
            "interval_seconds": 60, "warning_ms": 500, "critical_ms": 2000, **extra}
    r = client.post("/targets", json=body)
    assert r.status_code == 201
    return r.json()["id"]


# ---- checker functions ----

def test_http_reachable(base_url):
    result = check_http(f"{base_url}/ok")
    assert result["is_up"] is True
    assert result["status_code"] == 200
    assert result["latency_ms"] is not None


def test_http_server_error(base_url):
    result = check_http(f"{base_url}/error")
    assert result["is_up"] is False
    assert result["status_code"] == 500


def test_http_unreachable():
    result = check_http("http://127.0.0.1:1")
    assert result["is_up"] is False
    assert result["error"]


def test_http_timeout(base_url):
    result = check_http(f"{base_url}/slow", timeout=0.5)
    assert result["is_up"] is False
    assert result["error"] == "Timed out"


def test_http_slow_response(base_url):
    result = check_http(f"{base_url}/slow", timeout=5)
    assert result["is_up"] is True
    assert result["latency_ms"] >= 1000


def test_ping_localhost():
    assert check_ping("127.0.0.1")["is_up"] is True


# ---- API behaviour ----

def test_check_now_and_status_up(base_url):
    tid = make_target("Local OK", f"{base_url}/ok")
    assert client.post(f"/targets/{tid}/check").status_code == 201
    status = client.get(f"/targets/{tid}/status").json()
    assert status["state"] == "up"
    assert status["uptime_percent"] == 100.0
    assert status["total_checks"] == 1


def test_status_down_for_unreachable_target():
    tid = make_target("Dead", "http://127.0.0.1:1")
    client.post(f"/targets/{tid}/check")
    status = client.get(f"/targets/{tid}/status").json()
    assert status["state"] == "down"
    assert status["uptime_percent"] == 0.0


def test_status_slow_when_above_warning(base_url):
    tid = make_target("Slow", f"{base_url}/slow")
    client.post(f"/targets/{tid}/check")
    assert client.get(f"/targets/{tid}/status").json()["state"] == "slow"


def test_results_history(base_url):
    tid = make_target("History", f"{base_url}/ok")
    client.post(f"/targets/{tid}/check")
    client.post(f"/targets/{tid}/check")
    results = client.get(f"/targets/{tid}/results").json()
    assert len(results) == 2


def test_unknown_state_before_any_check(base_url):
    tid = make_target("Fresh", f"{base_url}/ok")
    assert client.get(f"/targets/{tid}/status").json()["state"] == "unknown"


def test_check_missing_target_404():
    assert client.post("/targets/999/check").status_code == 404


def test_scheduler_due_logic(base_url):
    make_target("Due", f"{base_url}/ok")
    db = TestingSession()
    try:
        assert run_due_checks(db) == 1   # never checked, so it is due
        assert run_due_checks(db) == 0   # just checked, so not due again yet
    finally:
        db.close()