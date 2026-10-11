"""API tests with an in-memory database and no Gemini."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

CID = "client-abc-12345"


@pytest.fixture()
def client():
    return TestClient(create_app("sqlite://", picker=None))


def play(client, **kw):
    body = {"client_id": CID, "joy": 1, "surprise": 0.5, "calm": 0, "play": 0, "table": "T7"}
    body.update(kw)
    return client.post("/api/vibe", json=body)


def test_health_and_pages(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    assert client.get("/staff").status_code == 200


def test_menu_seeded(client):
    menu = client.get("/api/menu").json()
    assert len(menu) == 13 and {m["kind"] for m in menu} == {"drink", "snack"}


def test_vibe_flow_and_returning_bonus(client):
    first = play(client).json()
    assert first["vibe"] == "spark" and first["source"] == "rules"
    assert first["drink"]["kind"] == "drink" and first["returning_bonus"] == 0
    second = play(client).json()
    assert second["returning_bonus"] == 25 and second["points"] == first["points"] + 25


@pytest.mark.parametrize("bad", [
    {"joy": 2}, {"joy": -1}, {"client_id": "x"}, {"client_id": "bad id!!!!!"}, {"table": "<script>"},
])
def test_vibe_validation(client, bad):
    assert play(client, **bad).status_code == 422


def test_order_and_wait_grow(client):
    before = client.get("/api/wait").json()["wait_minutes"]
    res = client.post("/api/order", json={"table": "T7", "item_ids": ["d1", "s2"]})
    assert res.status_code == 200 and res.json()["total"] == 420 and res.json()["eta_minutes"] >= 2
    for _ in range(6):
        client.post("/api/order", json={"item_ids": ["d5", "s3"]})
    after = client.get("/api/wait").json()
    assert after["wait_minutes"] > before and after["status"] in {"steady", "busy"}


def test_order_rejects_unknown_and_empty(client):
    assert client.post("/api/order", json={"item_ids": ["zzz"]}).status_code == 422
    assert client.post("/api/order", json={"item_ids": []}).status_code == 422
    assert client.post("/api/order", json={"item_ids": ["d1"] * 7}).status_code == 422


def test_room_pulse(client):
    empty = client.get("/api/room").json()
    assert empty["guests_last_hour"] == 0 and empty["dominant"] is None
    play(client)
    play(client, client_id="client-two-12345", joy=0, surprise=0, calm=1)
    room = client.get("/api/room").json()
    assert room["guests_last_hour"] == 2 and sum(room["mix"].values()) == 100
    assert room["dominant"] in {"spark", "zen"} and room["tip"]


def test_leaderboard_orders_tables(client):
    play(client, table="A1", joy=0.2)
    play(client, client_id="client-two-12345", table="B2", joy=1, surprise=1)
    board = client.get("/api/leaderboard").json()
    assert [r["table"] for r in board] == ["B2", "A1"]


def test_security_headers(client):
    headers = client.get("/").headers
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert "camera=(self)" in headers["permissions-policy"]


def test_rate_limit(monkeypatch):
    monkeypatch.setattr("app.main.RATE_LIMIT_PER_MIN", 3)
    limited = TestClient(create_app("sqlite://", picker=None))
    codes = [limited.get("/api/health").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes
