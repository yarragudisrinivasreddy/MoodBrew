"""Recommendation: the menu graph shortlists, Gemini only chooses among the shortlist."""
from typing import Protocol

FALLBACK_LINES = {
    "spark": "That energy deserves something bright and cold. Cheers to a great day.",
    "zen": "A calm table is a rare thing. Here is something to match it.",
    "cozy": "Settle in. This one tastes like a warm corner and no rush.",
    "chaos": "Absolutely unhinged, in the best way. Your order is equally bold.",
}


class Picker(Protocol):
    """Anything that can choose from candidates."""

    def pick(self, vibe: str, scores: dict, drinks: list[dict], snacks: list[dict]) -> dict | None:
        """Return a choice dict or None."""


def affinity(item: dict, vibe: str) -> int:
    """2 for a primary match, 1 for a secondary match, 0 otherwise."""
    vibes = item["vibes"]
    if vibes and vibes[0] == vibe:
        return 2
    return 1 if vibe in vibes else 0


def shortlist(items: list[dict], vibe: str, kind: str, size: int = 4) -> list[dict]:
    """Top candidates of one kind for a vibe, stable-sorted by affinity then name."""
    pool = [i for i in items if i["kind"] == kind]
    pool.sort(key=lambda i: (-affinity(i, vibe), i["name"]))
    return pool[:size]


def recommend(items: list[dict], vibe: str, scores: dict, picker: Picker | None) -> dict:
    """Return {'drink','snack','line','source'} using Gemini when valid, else deterministic."""
    drinks = shortlist(items, vibe, "drink")
    snacks = shortlist(items, vibe, "snack")
    variety = int(sum(scores.values()) * 100)
    choice = {
        "drink": drinks[variety % min(2, len(drinks))],
        "snack": snacks[variety % min(2, len(snacks))],
        "line": FALLBACK_LINES[vibe],
        "source": "rules",
    }
    brief = lambda xs: [{"id": x["id"], "name": x["name"], "blurb": x["blurb"]} for x in xs]
    result = picker.pick(vibe, scores, brief(drinks), brief(snacks)) if picker else None
    if not result:
        return choice
    by_id = {i["id"]: i for i in drinks + snacks}
    drink, snack = by_id.get(result.get("drink_id")), by_id.get(result.get("snack_id"))
    line = str(result.get("line", "")).strip()
    if drink and snack and drink["kind"] == "drink" and snack["kind"] == "snack" and 0 < len(line) <= 160:
        return {"drink": drink, "snack": snack, "line": line, "source": "gemini"}
    return choice
