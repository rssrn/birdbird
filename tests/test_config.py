"""Tests for config.py module.

@author Claude Sonnet 4.5 Anthropic
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from birdbird.config import (
    CONFIG_PATH,
    DEFAULT_LABELS_FILE,
    RemoteConfig,
    SpeciesConfig,
    get_location,
    get_species_config,
    load_config,
)


class TestLoadConfig:
    """Tests for load_config()."""

    def test_load_valid_config(self, tmp_config_dir, sample_config, monkeypatch):
        """Test loading a valid config file."""
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(sample_config))

        # Monkey patch CONFIG_PATH to use temp directory
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        result = load_config()
        assert result == sample_config
        assert result["location"]["lat"] == 51.5074
        assert result["location"]["lon"] == -0.1278

    def test_missing_config_file(self, tmp_config_dir, monkeypatch):
        """Test with missing config file returns empty dict."""
        config_path = tmp_config_dir / "config.json"
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        result = load_config()
        assert result == {}

    def test_partial_config(self, tmp_config_dir, monkeypatch):
        """Test with partial config (missing optional fields)."""
        partial_config = {"location": {"lat": 51.5, "lon": -0.1}}
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(partial_config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        result = load_config()
        assert result == partial_config
        assert "species" not in result

    def test_invalid_json(self, tmp_config_dir, monkeypatch):
        """Test with invalid JSON returns empty dict."""
        config_path = tmp_config_dir / "config.json"
        config_path.write_text("{ invalid json }")
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        result = load_config()
        assert result == {}


class TestGetLocation:
    """Tests for get_location()."""

    def test_location_with_coordinates(self, tmp_config_dir, monkeypatch):
        """Test extracting valid coordinates."""
        config = {"location": {"lat": 51.5074, "lon": -0.1278}}
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        lat, lon = get_location()
        assert lat == 51.5074
        assert lon == -0.1278

    def test_location_missing_coordinates(self, tmp_config_dir, monkeypatch):
        """Test with missing location section."""
        config = {"other": "data"}
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        lat, lon = get_location()
        assert lat is None
        assert lon is None

    def test_location_partial_coordinates(self, tmp_config_dir, monkeypatch):
        """Test with only one coordinate."""
        config = {"location": {"lat": 51.5074}}
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        lat, lon = get_location()
        assert lat is None
        assert lon is None

    def test_location_invalid_types(self, tmp_config_dir, monkeypatch):
        """Test with invalid coordinate types."""
        config = {"location": {"lat": "invalid", "lon": "invalid"}}
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        lat, lon = get_location()
        assert lat is None
        assert lon is None

    def test_location_no_config(self, tmp_config_dir, monkeypatch):
        """Test with no config file."""
        config_path = tmp_config_dir / "config.json"
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        lat, lon = get_location()
        assert lat is None
        assert lon is None


class TestGetSpeciesConfig:
    """Tests for get_species_config()."""

    def test_full_species_config(self, tmp_config_dir, sample_config, monkeypatch):
        """Test parsing full species config with remote."""
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(sample_config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        species_config = get_species_config()
        assert isinstance(species_config, SpeciesConfig)
        assert species_config.enabled is True
        assert species_config.samples_per_minute == 6.0
        assert species_config.min_confidence == 0.5
        assert species_config.processing_mode == "remote"
        assert isinstance(species_config.remote, RemoteConfig)
        assert species_config.remote.host == "devserver@192.168.1.146"
        assert species_config.remote.shell == "bash"
        assert species_config.remote.python_env == "~/bioclip_env"
        assert species_config.remote.timeout == 300

    def test_default_species_config(self, tmp_config_dir, monkeypatch):
        """Test with no species config returns defaults."""
        config_path = tmp_config_dir / "config.json"
        config_path.write_text("{}")
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        species_config = get_species_config()
        assert isinstance(species_config, SpeciesConfig)
        assert species_config.enabled is False
        assert species_config.samples_per_minute == 6.0
        assert species_config.min_confidence == 0.5
        assert species_config.labels_file is None
        assert species_config.processing_mode == "local"
        assert species_config.remote is None

    def test_species_config_local_mode(self, tmp_config_dir, monkeypatch):
        """Test species config with local processing mode."""
        config = {
            "species": {
                "enabled": True,
                "min_confidence": 0.7,
                "processing": {
                    "mode": "local",
                },
            }
        }
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        species_config = get_species_config()
        assert species_config.enabled is True
        assert species_config.processing_mode == "local"
        assert species_config.remote is None

    def test_species_config_labels_file(self, tmp_config_dir, tmp_path, monkeypatch):
        """Test species config with custom labels file."""
        labels_file = tmp_path / "custom_labels.txt"
        labels_file.write_text("Blue Tit\nRobin\n")

        config = {
            "species": {
                "labels_file": str(labels_file),
            }
        }
        config_path = tmp_config_dir / "config.json"
        config_path.write_text(json.dumps(config))
        monkeypatch.setattr("birdbird.config.CONFIG_PATH", config_path)

        species_config = get_species_config()
        assert species_config.labels_file == labels_file


class TestSpeciesConfig:
    """Tests for SpeciesConfig class."""

    def test_get_labels_file_custom(self, tmp_path):
        """Test get_labels_file with custom file."""
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("Blue Tit\n")

        config = SpeciesConfig(labels_file=labels_file)
        assert config.get_labels_file() == labels_file

    def test_get_labels_file_default(self):
        """Test get_labels_file falls back to bundled default."""
        config = SpeciesConfig()
        assert config.get_labels_file() == DEFAULT_LABELS_FILE

    def test_get_labels_file_missing(self, tmp_path):
        """Test get_labels_file with non-existent custom file."""
        missing_file = tmp_path / "missing.txt"

        config = SpeciesConfig(labels_file=missing_file)
        # Should fall back to default when custom file doesn't exist
        assert config.get_labels_file() == DEFAULT_LABELS_FILE
