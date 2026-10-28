"""Scalar normalization shared by headless application services and UI adapters."""


def coerce_bool(value: object) -> bool:
    """Read checkbox values safely from live state, JSON, or legacy CSV text."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "on", "checked"}
