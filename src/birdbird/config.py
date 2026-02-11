"""Configuration loading from ~/.birdbird/config.json.

@author Claude Opus 4.5 Anthropic
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CONFIG_PATH = Path.home() / ".birdbird" / "config.json"

# Default labels file bundled with package
DEFAULT_LABELS_FILE = Path(__file__).parent / "data" / "uk_garden_birds.txt"


@dataclass
class RemoteConfig:
    """Remote GPU processing configuration.

    @author Claude Opus 4.5 Anthropic
    """

    host: str
    shell: str = "bash"
    python_env: str = "~/bioclip_env"
    timeout: int = 300


@dataclass
class SpeciesConfig:
    """Species identification configuration.

    @author Claude Opus 4.5 Anthropic
    """

    enabled: bool = False
    samples_per_minute: float = 6.0
    min_confidence: float = 0.5
    labels_file: Path | None = None
    processing_mode: str = "local"  # "local", "remote", or "cloud"
    remote: RemoteConfig | None = None

    def get_labels_file(self) -> Path:
        """Get labels file path, falling back to bundled default.

        @author Claude Opus 4.5 Anthropic
        """
        if self.labels_file and Path(self.labels_file).exists():
            return Path(self.labels_file)
        return DEFAULT_LABELS_FILE


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


def get_species_config() -> SpeciesConfig:
    """Get species identification configuration.

    Reads from ~/.birdbird/config.json species section.
    Returns defaults if not configured.

    @author Claude Opus 4.5 Anthropic
    """
    config = load_config()
    species = config.get("species", {})

    # Parse remote config if present
    remote_config = None
    processing = species.get("processing", {})
    if processing.get("mode") == "remote":
        remote = processing.get("remote", {})
        if "host" in remote:
            remote_config = RemoteConfig(
                host=remote["host"],
                shell=remote.get("shell", "bash"),  # nosec B604
                python_env=remote.get("python_env", "~/bioclip_env"),
                timeout=remote.get("timeout", 300),
            )

    # Parse labels file
    labels_file = None
    if species.get("labels_file"):
        labels_file = Path(species["labels_file"]).expanduser()

    return SpeciesConfig(
        enabled=species.get("enabled", False),
        samples_per_minute=species.get("samples_per_minute", 6.0),
        min_confidence=species.get("min_confidence", 0.5),
        labels_file=labels_file,
        processing_mode=processing.get("mode", "local"),
        remote=remote_config,
    )
