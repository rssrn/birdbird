"""Shared pytest fixtures for birdbird tests.

@author Claude Sonnet 4.5 Anthropic
"""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create temporary ~/.birdbird/ directory."""
    config_dir = tmp_path / ".birdbird"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_config():
    """Sample valid configuration dict."""
    return {
        "location": {
            "lat": 51.5074,
            "lon": -0.1278,
        },
        "species": {
            "enabled": True,
            "samples_per_minute": 6.0,
            "min_confidence": 0.5,
            "labels_file": "/path/to/labels.txt",
            "processing": {
                "mode": "remote",
                "remote": {
                    "host": "devserver@192.168.1.146",
                    "shell": "bash",
                    "python_env": "~/bioclip_env",
                    "timeout": 300,
                },
            },
        },
    }


@pytest.fixture
def tmp_input_dir(tmp_path):
    """Create temporary input directory with AVI structure."""
    input_dir = tmp_path / "20260114"
    input_dir.mkdir()

    # Create sample AVI files
    (input_dir / "1408301500.avi").touch()
    (input_dir / "1408301600.avi").touch()
    (input_dir / "1508301700.avi").touch()

    return input_dir


@pytest.fixture
def sample_detections():
    """Sample detection data for best_clips tests."""
    return [
        {
            "timestamp_s": 0.0,
            "species": "Blue Tit",
            "confidence": 0.9,
        },
        {
            "timestamp_s": 5.0,
            "species": "Blue Tit",
            "confidence": 0.85,
        },
        {
            "timestamp_s": 10.0,
            "species": "Robin",
            "confidence": 0.75,
        },
        {
            "timestamp_s": 15.0,
            "species": "Blue Tit",
            "confidence": 0.8,
        },
        {
            "timestamp_s": 100.0,
            "species": "Blue Tit",
            "confidence": 0.95,
        },
    ]


@pytest.fixture
def sample_clip_filenames():
    """Sample clip filenames for publish tests."""
    return [
        "1408301500.avi",
        "1408301600.avi",
        "1508301700.avi",
        "1608301800.avi",
    ]


@pytest.fixture
def sample_birdnet_csv(tmp_path):
    """Create sample BirdNET CSV file."""
    csv_path = tmp_path / "results.csv"
    csv_content = """Start (s),End (s),Scientific name,Common name,Confidence,File
0.0,3.0,Cyanistes caeruleus,Eurasian Blue Tit,0.9134,1408301500.wav
5.0,8.0,Erithacus rubecula,European Robin,0.8521,1408301500.wav
12.0,15.0,Parus major,Great Tit,0.7845,1408301500.wav
"""
    csv_path.write_text(csv_content)
    return csv_path
