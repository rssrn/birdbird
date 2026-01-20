"""Configuration loading from ~/.birdbird/config.json.

@author Claude Opus 4.5 Anthropic
"""

import json
from pathlib import Path
from typing import Any


CONFIG_PATH = Path.home() / ".birdbird" / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from ~/.birdbird/config.json.

    Returns empty dict if file doesn't exist or is invalid.

    @author Claude Opus 4.5 Anthropic
    """
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_location() -> tuple[float | None, float | None]:
    """Get default location (lat, lon) from config.

    Returns (None, None) if not configured.

    @author Claude Opus 4.5 Anthropic
    """
    config = load_config()
    location = config.get("location", {})

    lat = location.get("lat")
    lon = location.get("lon")

    # Both must be present and valid numbers
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return (float(lat), float(lon))

    return (None, None)
