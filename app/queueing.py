"""Deterministic wait-time model: time-decayed open load divided across baristas."""
import math
from datetime import datetime

from .config import BARISTAS, QUEUE_WINDOW_MIN


def decayed_load(orders: list[tuple[float, datetime]], now: datetime) -> float:
    """Sum of remaining prep minutes, each order fading linearly to zero over the window."""
    total = 0.0
    for load_min, created in orders:
        age = (now - created).total_seconds() / 60
        total += load_min * max(0.0, 1 - age / QUEUE_WINDOW_MIN)
    return total


def eta_minutes(open_load: float, own_prep: float, baristas: int = BARISTAS) -> int:
    """Estimated minutes until a new order is ready (never below 2)."""
    return max(2, math.ceil(open_load / max(1, baristas) + own_prep))


def busy_label(wait_min: int) -> str:
    """Human label for the current wait."""
    if wait_min <= 5:
        return "quiet"
    return "steady" if wait_min <= 10 else "busy"


STAFF_TIPS = {
    "spark": "High energy in the room. Push cold brews and keep the playlist upbeat.",
    "zen": "A calm room. Keep music low and offer slow-sip drinks and pastries.",
    "cozy": "Cozy mood. Suggest warm drinks and desserts; stay near tables for refills.",
    "chaos": "Playful chaos. Highlight shareable snacks and run a table challenge.",
}
