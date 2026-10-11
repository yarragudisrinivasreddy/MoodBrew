"""Deterministic vibe scoring. Gemini never decides the vibe; this module does."""

VIBES = ("spark", "zen", "cozy", "chaos")
SCORE_KEYS = ("joy", "surprise", "calm", "play")


def clamp(value: float) -> float:
    """Clamp a number into the 0..1 range."""
    return max(0.0, min(1.0, float(value)))


def classify(scores: dict[str, float]) -> str:
    """Map the four expression scores to one of four vibes (ties favour VIBES order)."""
    joy, surprise, calm, play = (clamp(scores.get(k, 0.0)) for k in SCORE_KEYS)
    weights = {
        "spark": 0.6 * joy + 0.4 * surprise,
        "zen": 0.8 * calm + 0.2 * (1 - max(joy, surprise, play)),
        "cozy": 0.35 * joy + 0.35 * calm + 0.3 * (1 - surprise),
        "chaos": 0.6 * play + 0.4 * surprise,
    }
    return max(VIBES, key=lambda v: (round(weights[v], 6), -VIBES.index(v)))


def points(scores: dict[str, float], previous_visits: int) -> int:
    """Game points: performance plus a small loyalty bonus for return visits."""
    performance = sum(clamp(scores.get(k, 0.0)) for k in SCORE_KEYS) * 75
    return round(performance) + 25 * min(max(previous_visits, 0), 4)


def badge(total: int) -> str:
    """Badge name for a points total."""
    if total >= 220:
        return "Legend"
    if total >= 150:
        return "Regular"
    return "Newcomer"
