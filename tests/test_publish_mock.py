"""Tests for publish.py module (mocked boto3 + subprocess).

@author Claude Opus 4.6 Anthropic
"""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from birdbird.publish import (
    calculate_md5,
    cleanup_old_batches,
    generate_batch_id,
    get_highlights_duration,
    list_batches,
    should_upload_file,
)


class TestCalculateMd5:
    """Tests for calculate_md5()."""

    def test_known_file_content(self, tmp_path):
        """Returns expected MD5 hash for known content."""
        test_file = tmp_path / "test.bin"
        content = b"hello world"
        test_file.write_bytes(content)

        expected = hashlib.md5(content, usedforsecurity=False).hexdigest()
        result = calculate_md5(test_file)

        assert result == expected


class TestShouldUploadFile:
    """Tests for should_upload_file()."""

    def test_file_doesnt_exist_404(self, mock_s3_client, tmp_path):
        """Returns True when remote file doesn't exist (404)."""
        error_response = {"Error": {"Code": "404"}}
        mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        test_file = tmp_path / "new.mp4"
        test_file.write_bytes(b"data")

        assert should_upload_file(mock_s3_client, "bucket", "key", test_file) is True

    def test_same_md5(self, mock_s3_client, tmp_path):
        """Returns False when MD5 matches (no upload needed)."""
        content = b"same content"
        test_file = tmp_path / "same.mp4"
        test_file.write_bytes(content)

        local_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        mock_s3_client.head_object.return_value = {
            "ETag": f'"{local_md5}"',
            "ContentLength": len(content),
        }

        assert should_upload_file(mock_s3_client, "bucket", "key", test_file) is False

    def test_different_md5(self, mock_s3_client, tmp_path):
        """Returns True when MD5 differs."""
        test_file = tmp_path / "changed.mp4"
        test_file.write_bytes(b"new content")

        mock_s3_client.head_object.return_value = {
            "ETag": '"oldmd5hash1234567890abcdef12345678"',
            "ContentLength": 100,
        }

        assert should_upload_file(mock_s3_client, "bucket", "key", test_file) is True

    def test_multipart_etag_compares_size(self, mock_s3_client, tmp_path):
        """Multipart ETag (contains '-') compares file size instead."""
        content = b"multipart content"
        test_file = tmp_path / "large.mp4"
        test_file.write_bytes(content)

        mock_s3_client.head_object.return_value = {
            "ETag": '"abc123-2"',  # Multipart ETag
            "ContentLength": len(content),  # Same size
        }

        assert should_upload_file(mock_s3_client, "bucket", "key", test_file) is False

    def test_multipart_etag_different_size(self, mock_s3_client, tmp_path):
        """Multipart ETag with different size triggers upload."""
        test_file = tmp_path / "large.mp4"
        test_file.write_bytes(b"content")

        mock_s3_client.head_object.return_value = {
            "ETag": '"abc123-2"',
            "ContentLength": 999,  # Different size
        }

        assert should_upload_file(mock_s3_client, "bucket", "key", test_file) is True


class TestListBatches:
    """Tests for list_batches()."""

    def test_multiple_batches(self, mock_s3_client):
        """Returns sorted list of batch IDs (newest first)."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": "batches/20260112_01/"},
                {"Prefix": "batches/20260114_01/"},
                {"Prefix": "batches/20260113_01/"},
            ]
        }

        result = list_batches(mock_s3_client, "bucket")

        assert result == ["20260114_01", "20260113_01", "20260112_01"]

    def test_empty_bucket(self, mock_s3_client):
        """Returns empty list for empty bucket."""
        mock_s3_client.list_objects_v2.return_value = {}

        result = list_batches(mock_s3_client, "bucket")

        assert result == []


class TestGenerateBatchId:
    """Tests for generate_batch_id()."""

    def test_no_existing_batches(self, mock_s3_client):
        """Returns date_01 when no batches exist."""
        mock_s3_client.list_objects_v2.return_value = {}

        batch_id, exists = generate_batch_id(mock_s3_client, "bucket", "2026-01-14")

        assert batch_id == "20260114_01"
        assert exists is False

    def test_existing_batch_create_new_false(self, mock_s3_client):
        """Reuses existing batch ID when create_new=False."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": "batches/20260114_01/"}]
        }

        batch_id, exists = generate_batch_id(
            mock_s3_client, "bucket", "2026-01-14", create_new=False
        )

        assert batch_id == "20260114_01"
        assert exists is True

    def test_existing_batch_create_new_true(self, mock_s3_client):
        """Increments sequence when create_new=True."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": "batches/20260114_01/"}]
        }

        batch_id, exists = generate_batch_id(
            mock_s3_client, "bucket", "2026-01-14", create_new=True
        )

        assert batch_id == "20260114_02"
        assert exists is False


class TestGetHighlightsDuration:
    """Tests for get_highlights_duration()."""

    def test_valid_ffprobe_output(self):
        """Returns float duration from ffprobe."""
        with patch("birdbird.publish.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="123.456\n", stderr=""
            )

            result = get_highlights_duration(Path("highlights.mp4"))

        assert result == pytest.approx(123.456)

    def test_ffprobe_fails(self):
        """Raises RuntimeError when ffprobe fails."""
        with patch("birdbird.publish.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error"
            )

            with pytest.raises(RuntimeError, match="ffprobe failed"):
                get_highlights_duration(Path("highlights.mp4"))


class TestCleanupOldBatches:
    """Tests for cleanup_old_batches()."""

    def test_five_or_fewer_batches_no_deletion(self, mock_s3_client):
        """No deletion when <= 5 batches exist."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": f"batches/2026011{i}_01/"} for i in range(5)
            ]
        }

        result = cleanup_old_batches(mock_s3_client, "bucket")

        assert result == []

    def test_more_than_five_user_confirms(self, mock_s3_client):
        """> 5 batches, user confirms deletion of oldest."""
        mock_s3_client.list_objects_v2.side_effect = [
            # First call: list_batches
            {
                "CommonPrefixes": [
                    {"Prefix": f"batches/2026011{i}_01/"} for i in range(7)
                ]
            },
            # Second call: also list_batches (called again inside cleanup)
            {
                "CommonPrefixes": [
                    {"Prefix": f"batches/2026011{i}_01/"} for i in range(7)
                ]
            },
            # Third+: list_objects for each batch to delete
            {"Contents": [{"Key": "batches/20260111_01/highlights.mp4"}]},
            {"Contents": [{"Key": "batches/20260110_01/highlights.mp4"}]},
        ]

        with patch("birdbird.publish.typer.confirm", return_value=True):
            with patch("birdbird.publish.typer.echo"):
                # Mock get_object for latest.json update
                mock_s3_client.get_object.return_value = {
                    "Body": MagicMock(
                        read=MagicMock(return_value=b'{"latest":"20260116_01","batches":[]}')
                    )
                }

                result = cleanup_old_batches(mock_s3_client, "bucket")

        assert len(result) == 2

    def test_more_than_five_user_declines(self, mock_s3_client):
        """> 5 batches, user declines deletion."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": f"batches/2026011{i}_01/"} for i in range(7)
            ]
        }

        with patch("birdbird.publish.typer.confirm", return_value=False):
            with patch("birdbird.publish.typer.echo"):
                result = cleanup_old_batches(mock_s3_client, "bucket")

        assert result == []
        mock_s3_client.delete_object.assert_not_called()
