"""Unit tests for the deterministic core: vibes, recommendations, wait model."""
from datetime import datetime, timedelta

from app import queueing, vibes
from app.menu_seed import MENU
from app.recommend import recommend, shortlist

ITEMS = [
    {"id": i, "name": n, "kind": k, "price": p, "prep_min": m, "vibes": v, "blurb": b}
    for i, n, k, p, m, v, b in MENU
]


def test_classify_each_vibe():
    assert vibes.classify({"joy": 1, "surprise": 0.6, "calm": 0, "play": 0}) == "spark"
    assert vibes.classify({"joy": 0, "surprise": 0, "calm": 1, "play": 0}) == "zen"
    assert vibes.classify({"joy": 0.5, "surprise": 0, "calm": 0.6, "play": 0}) == "cozy"
    assert vibes.classify({"joy": 0, "surprise": 0.4, "calm": 0, "play": 1}) == "chaos"


def test_classify_clamps_and_handles_empty():
    assert vibes.classify({}) in vibes.VIBES
    assert vibes.classify({"joy": 9, "surprise": 9}) == "spark"


def test_points_and_badges():
    full = {"joy": 1, "surprise": 1, "calm": 1, "play": 1}
    assert vibes.points(full, 0) == 300
    assert vibes.points(full, 10) == 400  # loyalty bonus capped at 4 visits
    assert vibes.badge(300) == "Legend"
    assert vibes.badge(160) == "Regular"
    assert vibes.badge(10) == "Newcomer"


def test_shortlist_prefers_primary_match():
    top = shortlist(ITEMS, "zen", "drink")
    assert top[0]["id"] == "d5"  # matcha lists zen first
    assert all(i["kind"] == "drink" for i in top)


def test_recommend_falls_back_without_picker():
    out = recommend(ITEMS, "cozy", {"joy": 0.5}, None)
    assert out["source"] == "rules" and out["drink"]["kind"] == "drink"


class FakePicker:
    def __init__(self, reply):
        self.reply = reply

    def pick(self, vibe, scores, drinks, snacks):
        return self.reply


def test_recommend_accepts_valid_gemini_choice():
    drinks = shortlist(ITEMS, "spark", "drink")
    snacks = shortlist(ITEMS, "spark", "snack")
    reply = {"drink_id": drinks[1]["id"], "snack_id": snacks[0]["id"], "line": "Bold choice."}
    out = recommend(ITEMS, "spark", {"joy": 1}, FakePicker(reply))
    assert out["source"] == "gemini" and out["drink"]["id"] == drinks[1]["id"]


def test_recommend_rejects_hallucinated_ids():
    reply = {"drink_id": "nope", "snack_id": "s1", "line": "Hi"}
    assert recommend(ITEMS, "spark", {"joy": 1}, FakePicker(reply))["source"] == "rules"


def test_recommend_rejects_wrong_kind_and_long_line():
    drinks = shortlist(ITEMS, "spark", "drink")
    snacks = shortlist(ITEMS, "spark", "snack")
    swapped = {"drink_id": snacks[0]["id"], "snack_id": drinks[0]["id"], "line": "x"}
    assert recommend(ITEMS, "spark", {}, FakePicker(swapped))["source"] == "rules"
    too_long = {"drink_id": drinks[0]["id"], "snack_id": snacks[0]["id"], "line": "x" * 200}
    assert recommend(ITEMS, "spark", {}, FakePicker(too_long))["source"] == "rules"


def test_eta_and_decay():
    now = datetime(2026, 1, 1, 12, 0)
    fresh = queueing.decayed_load([(10, now)], now)
    old = queueing.decayed_load([(10, now - timedelta(minutes=10))], now)
    gone = queueing.decayed_load([(10, now - timedelta(minutes=30))], now)
    assert fresh == 10 and old == 5 and gone == 0
    assert queueing.eta_minutes(0, 0) == 2
    assert queueing.eta_minutes(10, 4, baristas=2) == 9
    assert queueing.busy_label(4) == "quiet"
    assert queueing.busy_label(8) == "steady"
    assert queueing.busy_label(15) == "busy"
