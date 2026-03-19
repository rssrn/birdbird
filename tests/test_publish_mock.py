"""Tests for publish.py module (mocked boto3 + subprocess).

@author Claude Opus 4.6 Anthropic
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from birdbird.publish import (
    calculate_md5,
    cleanup_old_batches,
    generate_batch_id,
    get_highlights_duration,
    list_batches,
    publish_to_r2,
    should_upload_file,
    update_latest_json,
    upload_batch,
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
        mock_s3_client.list_objects_v2.return_value = {"CommonPrefixes": [{"Prefix": "batches/20260114_01/"}]}

        batch_id, exists = generate_batch_id(mock_s3_client, "bucket", "2026-01-14", create_new=False)

        assert batch_id == "20260114_01"
        assert exists is True

    def test_existing_batch_create_new_true(self, mock_s3_client):
        """Increments sequence when create_new=True."""
        mock_s3_client.list_objects_v2.return_value = {"CommonPrefixes": [{"Prefix": "batches/20260114_01/"}]}

        batch_id, exists = generate_batch_id(mock_s3_client, "bucket", "2026-01-14", create_new=True)

        assert batch_id == "20260114_02"
        assert exists is False


class TestGetHighlightsDuration:
    """Tests for get_highlights_duration()."""

    def test_valid_ffprobe_output(self, mocker):
        """Returns float duration from ffprobe."""
        mock_run = mocker.patch("birdbird.publish.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stdout="123.456\n", stderr="")

        result = get_highlights_duration(Path("highlights.mp4"))

        assert result == pytest.approx(123.456)

    def test_ffprobe_fails(self, mocker):
        """Raises RuntimeError when ffprobe fails."""
        mock_run = mocker.patch("birdbird.publish.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        with pytest.raises(RuntimeError, match="ffprobe failed"):
            get_highlights_duration(Path("highlights.mp4"))


class TestCleanupOldBatches:
    """Tests for cleanup_old_batches()."""

    def test_five_or_fewer_batches_no_deletion(self, mock_s3_client):
        """No deletion when <= 5 batches exist."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": f"batches/2026011{i}_01/"} for i in range(5)]
        }

        result = cleanup_old_batches(mock_s3_client, "bucket")

        assert result == []

    def test_more_than_five_user_confirms(self, mock_s3_client, mocker):
        """> 5 batches, user confirms deletion of oldest."""
        mock_s3_client.list_objects_v2.side_effect = [
            # First call: list_batches
            {"CommonPrefixes": [{"Prefix": f"batches/2026011{i}_01/"} for i in range(7)]},
            # Second call: also list_batches (called again inside cleanup)
            {"CommonPrefixes": [{"Prefix": f"batches/2026011{i}_01/"} for i in range(7)]},
            # Third+: list_objects for each batch to delete
            {"Contents": [{"Key": "batches/20260111_01/highlights.mp4"}]},
            {"Contents": [{"Key": "batches/20260110_01/highlights.mp4"}]},
        ]

        mocker.patch("birdbird.publish.typer.confirm", return_value=True)
        mocker.patch("birdbird.publish.typer.echo")
        # Mock get_object for latest.json update
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b'{"latest":"20260116_01","batches":[]}'))
        }

        result = cleanup_old_batches(mock_s3_client, "bucket")

        assert len(result) == 2

    def test_more_than_five_user_declines(self, mock_s3_client, mocker):
        """> 5 batches, user declines deletion."""
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [{"Prefix": f"batches/2026011{i}_01/"} for i in range(7)]
        }

        mocker.patch("birdbird.publish.typer.confirm", return_value=False)
        mocker.patch("birdbird.publish.typer.echo")

        result = cleanup_old_batches(mock_s3_client, "bucket")

        assert result == []
        mock_s3_client.delete_object.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers shared by upload_batch tests
# ---------------------------------------------------------------------------


def _make_paths(tmp_path: Path) -> MagicMock:
    """Create a MagicMock BirdbirdPaths with a real highlights.mp4 file."""
    assets_dir = tmp_path / "birdbird" / "assets"
    assets_dir.mkdir(parents=True)
    highlights_mp4 = assets_dir / "highlights.mp4"
    highlights_mp4.write_bytes(b"fake video content")

    paths = MagicMock()
    paths.highlights_mp4 = highlights_mp4
    paths.input_dir = tmp_path / "20260114"
    return paths


def _call_upload_batch(mock_s3_client, paths, mocker, **kwargs):
    """Call upload_batch() with common patches applied."""
    defaults = dict(
        s3_client=mock_s3_client,
        bucket_name="test-bucket",
        batch_id="20260114_01",
        paths=paths,
        clip_count=10,
        original_date="2026-01-14",
        batch_exists=False,
    )
    defaults.update(kwargs)

    tqdm_cm = MagicMock()
    tqdm_cm.__enter__ = MagicMock(return_value=MagicMock())
    tqdm_cm.__exit__ = MagicMock(return_value=False)

    mocker.patch("birdbird.publish.extract_date_range", return_value=("2026-01-14", "2026-01-14"))
    mocker.patch("birdbird.publish.get_highlights_duration", return_value=120.0)
    mocker.patch("birdbird.publish.tqdm", return_value=tqdm_cm)
    mocker.patch("birdbird.publish.typer.echo")

    return upload_batch(**defaults)


# ---------------------------------------------------------------------------
# TestUploadBatch
# ---------------------------------------------------------------------------


class TestUploadBatch:
    """Tests for upload_batch().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_highlights_uploaded_with_correct_r2_key(self, mock_s3_client, tmp_path, mocker):
        """Uploads highlights.mp4 to correct R2 key."""
        paths = _make_paths(tmp_path)
        _call_upload_batch(mock_s3_client, paths, mocker)

        mock_s3_client.upload_fileobj.assert_called_once()
        _, positional, keyword = mock_s3_client.upload_fileobj.mock_calls[0]
        assert positional[1] == "test-bucket"
        assert positional[2] == "batches/20260114_01/highlights.mp4"
        assert keyword["ExtraArgs"]["ContentType"] == "video/mp4"

    def test_metadata_structure(self, mock_s3_client, tmp_path, mocker):
        """Returns metadata dict with required fields and correct types."""
        paths = _make_paths(tmp_path)
        result = _call_upload_batch(mock_s3_client, paths, mocker, clip_count=42)

        assert result["batch_id"] == "20260114_01"
        assert result["original_date"] == "2026-01-14"
        assert result["start_date"] == "2026-01-14"
        assert result["end_date"] == "2026-01-14"
        assert result["clip_count"] == 42
        assert result["highlights_duration"] == 120.0

    def test_upload_stats_tracking(self, mock_s3_client, tmp_path, mocker):
        """Records uploaded and skipped files in _upload_stats."""
        paths = _make_paths(tmp_path)
        result = _call_upload_batch(mock_s3_client, paths, mocker)

        stats = result["_upload_stats"]
        assert "highlights.mp4" in stats["uploaded"]
        assert "metadata.json" in stats["uploaded"]

    def test_skips_highlights_when_unchanged_and_batch_exists(self, mock_s3_client, tmp_path, mocker):
        """Skips highlights.mp4 upload when batch_exists=True and file unchanged."""
        paths = _make_paths(tmp_path)
        mocker.patch("birdbird.publish.should_upload_file", return_value=False)
        result = _call_upload_batch(mock_s3_client, paths, mocker, batch_exists=True)

        mock_s3_client.upload_fileobj.assert_not_called()
        assert "highlights.mp4" in result["_upload_stats"]["skipped"]

    def test_uploads_when_file_changed_and_batch_exists(self, mock_s3_client, tmp_path, mocker):
        """Re-uploads highlights.mp4 when batch_exists=True but file has changed."""
        paths = _make_paths(tmp_path)
        mocker.patch("birdbird.publish.should_upload_file", return_value=True)
        result = _call_upload_batch(mock_s3_client, paths, mocker, batch_exists=True)

        mock_s3_client.upload_fileobj.assert_called_once()
        assert "highlights.mp4" in result["_upload_stats"]["uploaded"]

    def test_songs_json_included_when_present(self, mock_s3_client, tmp_path, mocker):
        """Uploads songs.json and adds summary to metadata when file exists."""
        paths = _make_paths(tmp_path)
        songs_path = tmp_path / "songs.json"
        songs_data = {
            "summary": {"total_detections": 5, "unique_species": 3},
            "timestamps_reliable": True,
        }
        songs_path.write_text(json.dumps(songs_data))

        result = _call_upload_batch(mock_s3_client, paths, mocker, songs_path=songs_path)

        # songs.json uploaded to correct key
        put_keys = [c[1]["Key"] for c in mock_s3_client.put_object.call_args_list]
        assert "batches/20260114_01/songs.json" in put_keys

        # summary in metadata
        assert result["songs"]["total_detections"] == 5
        assert result["songs"]["unique_species"] == 3
        assert result["songs"]["timestamps_reliable"] is True

    def test_songs_json_not_included_when_absent(self, mock_s3_client, tmp_path, mocker):
        """Does not include songs key in metadata when songs_path is None."""
        paths = _make_paths(tmp_path)
        result = _call_upload_batch(mock_s3_client, paths, mocker, songs_path=None)

        assert "songs" not in result

    def test_song_clips_metadata_aggregation(self, mock_s3_client, tmp_path, mocker):
        """Aggregates song clip metadata from songs.json clips list."""
        paths = _make_paths(tmp_path)

        # Create song clips dir with two WAV files
        clips_dir = tmp_path / "song_clips"
        clips_dir.mkdir()
        (clips_dir / "BlueTit_01.wav").write_bytes(b"audio")
        (clips_dir / "Robin_01.wav").write_bytes(b"audio")

        songs_path = tmp_path / "songs.json"
        songs_data = {
            "summary": {"total_detections": 2, "unique_species": 2},
            "clips": [
                {
                    "filename": "BlueTit_01.wav",
                    "common_name": "Blue Tit",
                    "scientific_name": "Cyanistes caeruleus",
                    "confidence": 0.91,
                },
                {
                    "filename": "Robin_01.wav",
                    "common_name": "Robin",
                    "scientific_name": "Erithacus rubecula",
                    "confidence": 0.85,
                },
            ],
        }
        songs_path.write_text(json.dumps(songs_data))

        result = _call_upload_batch(mock_s3_client, paths, mocker, songs_path=songs_path, song_clips_dir=clips_dir)

        assert "song_clips" in result
        clip_names = [c["filename"] for c in result["song_clips"]]
        assert "BlueTit_01.wav" in clip_names
        assert "Robin_01.wav" in clip_names

        blue_tit = next(c for c in result["song_clips"] if c["filename"] == "BlueTit_01.wav")
        assert blue_tit["common_name"] == "Blue Tit"
        assert blue_tit["confidence"] == 0.91

    def test_species_json_included_when_present(self, mock_s3_client, tmp_path, mocker):
        """Uploads species.json and adds species summary to metadata."""
        paths = _make_paths(tmp_path)
        species_path = tmp_path / "species.json"
        species_data = {
            "total_frames": 100,
            "species_summary": {
                "Blue Tit": {"count": 60},
                "Robin": {"count": 40},
            },
        }
        species_path.write_text(json.dumps(species_data))

        result = _call_upload_batch(mock_s3_client, paths, mocker, species_path=species_path)

        put_keys = [c[1]["Key"] for c in mock_s3_client.put_object.call_args_list]
        assert "batches/20260114_01/species.json" in put_keys

        assert result["species"]["total_frames"] == 100
        assert result["species"]["unique_species"] == 2
        assert set(result["species"]["species_list"]) == {"Blue Tit", "Robin"}

    def test_best_clips_json_included_when_present(self, mock_s3_client, tmp_path, mocker):
        """Uploads best_clips.json and adds summary to metadata."""
        paths = _make_paths(tmp_path)
        best_clips_path = tmp_path / "best_clips.json"
        best_clips_data = {
            "window_duration_s": 5.0,
            "species_count": 2,
            "clips": {"Blue Tit": {}, "Robin": {}},
        }
        best_clips_path.write_text(json.dumps(best_clips_data))

        result = _call_upload_batch(mock_s3_client, paths, mocker, best_clips_path=best_clips_path)

        put_keys = [c[1]["Key"] for c in mock_s3_client.put_object.call_args_list]
        assert "batches/20260114_01/best_clips.json" in put_keys

        assert result["best_clips"]["window_duration_s"] == 5.0
        assert result["best_clips"]["species_count"] == 2
        assert set(result["best_clips"]["species_list"]) == {"Blue Tit", "Robin"}

    def test_metadata_json_always_uploaded(self, mock_s3_client, tmp_path, mocker):
        """metadata.json is always uploaded regardless of batch_exists."""
        paths = _make_paths(tmp_path)
        mocker.patch("birdbird.publish.should_upload_file", return_value=False)
        result = _call_upload_batch(mock_s3_client, paths, mocker, batch_exists=True)

        put_keys = [c[1]["Key"] for c in mock_s3_client.put_object.call_args_list]
        assert "batches/20260114_01/metadata.json" in put_keys
        assert "metadata.json" in result["_upload_stats"]["uploaded"]


# ---------------------------------------------------------------------------
# TestUpdateLatestJson
# ---------------------------------------------------------------------------


class TestUpdateLatestJson:
    """Tests for update_latest_json().

    @author Claude Sonnet 4.6 Anthropic
    """

    _batch_meta = {
        "batch_id": "20260114_01",
        "uploaded": "2026-01-14T12:00:00+00:00",
        "original_date": "2026-01-14",
        "start_date": "2026-01-14",
        "end_date": "2026-01-14",
        "clip_count": 10,
        "highlights_duration": 120.0,
    }

    def test_creates_fresh_when_no_such_key(self, mock_s3_client, mocker):
        """Creates latest.json from scratch when it does not exist (NoSuchKey)."""
        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        mock_s3_client.get_object.side_effect = error

        mocker.patch("birdbird.publish.typer.echo")
        update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)

        mock_s3_client.put_object.assert_called_once()
        body = json.loads(mock_s3_client.put_object.call_args[1]["Body"])
        assert body["latest"] == "20260114_01"
        assert len(body["batches"]) == 1
        assert body["batches"][0]["id"] == "20260114_01"

    def test_prepends_to_existing_batches(self, mock_s3_client, mocker):
        """Prepends new batch to existing list so newest is first."""
        existing = {
            "latest": "20260113_01",
            "batches": [{"id": "20260113_01", "clip_count": 5}],
        }
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(existing).encode()))
        }

        mocker.patch("birdbird.publish.typer.echo")
        update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)

        body = json.loads(mock_s3_client.put_object.call_args[1]["Body"])
        assert body["batches"][0]["id"] == "20260114_01"
        assert body["batches"][1]["id"] == "20260113_01"

    def test_deduplicates_batch_id(self, mock_s3_client, mocker):
        """Removes old entry with same batch_id before prepending (deduplication)."""
        existing = {
            "latest": "20260114_01",
            "batches": [
                {"id": "20260114_01", "clip_count": 5},  # stale duplicate
                {"id": "20260113_01", "clip_count": 3},
            ],
        }
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(existing).encode()))
        }

        mocker.patch("birdbird.publish.typer.echo")
        update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)

        body = json.loads(mock_s3_client.put_object.call_args[1]["Body"])
        ids = [b["id"] for b in body["batches"]]
        assert ids.count("20260114_01") == 1
        assert len(body["batches"]) == 2  # updated + old one

    def test_sets_latest_pointer(self, mock_s3_client, mocker):
        """Sets the latest field to the new batch_id."""
        mock_s3_client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        mocker.patch("birdbird.publish.typer.echo")
        update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)

        body = json.loads(mock_s3_client.put_object.call_args[1]["Body"])
        assert body["latest"] == "20260114_01"

    def test_batch_summary_has_required_fields(self, mock_s3_client, mocker):
        """Batch summary in latest.json contains all required fields."""
        mock_s3_client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        mocker.patch("birdbird.publish.typer.echo")
        update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)

        body = json.loads(mock_s3_client.put_object.call_args[1]["Body"])
        summary = body["batches"][0]
        required_keys = {
            "id",
            "uploaded",
            "original_date",
            "start_date",
            "end_date",
            "clip_count",
            "highlights_duration",
        }
        assert required_keys.issubset(summary.keys())

    def test_propagates_non_nosuchkey_errors(self, mock_s3_client):
        """Re-raises ClientError that is not NoSuchKey."""
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        mock_s3_client.get_object.side_effect = error

        with pytest.raises(ClientError):
            update_latest_json(mock_s3_client, "test-bucket", self._batch_meta)


# ---------------------------------------------------------------------------
# TestPublishToR2
# ---------------------------------------------------------------------------


class TestPublishToR2:
    """Tests for publish_to_r2() orchestration.

    @author Claude Sonnet 4.6 Anthropic
    """

    def _setup_dirs(self, tmp_path: Path):
        """Create the minimal directory structure publish_to_r2 expects."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        assets_dir = input_dir / "birdbird" / "assets"
        assets_dir.mkdir(parents=True)
        highlights_mp4 = assets_dir / "highlights.mp4"
        highlights_mp4.write_bytes(b"fake video")
        return input_dir, assets_dir

    def _r2_config(self):
        return {
            "account_id": "acc123",
            "access_key_id": "key",
            "secret_access_key": "secret",
            "r2_bucket_name": "test-bucket",
        }

    def test_raises_when_assets_dir_missing(self, tmp_path):
        """Raises ValueError when birdbird/assets/ directory does not exist."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        with pytest.raises(ValueError, match="birdbird/assets/"):
            publish_to_r2(input_dir, self._r2_config())

    def test_raises_when_highlights_mp4_missing(self, tmp_path):
        """Raises ValueError when highlights.mp4 is absent from assets dir."""
        input_dir = tmp_path / "20260114"
        assets_dir = input_dir / "birdbird" / "assets"
        assets_dir.mkdir(parents=True)
        # highlights.mp4 deliberately not created

        with pytest.raises(ValueError, match="highlights.mp4"):
            publish_to_r2(input_dir, self._r2_config())

    def test_returns_correct_structure(self, mock_s3_client, tmp_path, mocker):
        """Return dict has all expected keys."""
        input_dir, assets_dir = self._setup_dirs(tmp_path)

        batch_meta = {
            "batch_id": "20260114_01",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 10,
            "highlights_duration": 120.0,
            "_upload_stats": {"uploaded": ["highlights.mp4", "metadata.json"], "skipped": []},
        }

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        mocker.patch("birdbird.publish.generate_batch_id", return_value=("20260114_01", False))
        mocker.patch("birdbird.publish.upload_batch", return_value=batch_meta)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[{}] * 5)
        mocker.patch("birdbird.publish.typer.echo")

        result = publish_to_r2(input_dir, self._r2_config())

        expected_keys = {
            "batch_id",
            "uploaded_files",
            "skipped_files",
            "uploaded_list",
            "skipped_list",
            "clip_count",
            "highlights_duration",
            "deleted_batches",
            "batch_replaced",
        }
        assert expected_keys.issubset(result.keys())

    def test_batch_replaced_false_for_new_batch(self, mock_s3_client, tmp_path, mocker):
        """batch_replaced is False when batch did not previously exist."""
        input_dir, _ = self._setup_dirs(tmp_path)

        batch_meta = {
            "batch_id": "20260114_01",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 0,
            "highlights_duration": 60.0,
            "_upload_stats": {"uploaded": ["highlights.mp4"], "skipped": []},
        }

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        mocker.patch("birdbird.publish.generate_batch_id", return_value=("20260114_01", False))
        mocker.patch("birdbird.publish.upload_batch", return_value=batch_meta)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[])
        mocker.patch("birdbird.publish.typer.echo")

        result = publish_to_r2(input_dir, self._r2_config())

        assert result["batch_replaced"] is False

    def test_detects_optional_songs_json(self, mock_s3_client, tmp_path, mocker):
        """Passes songs_path to upload_batch when songs.json is present."""
        input_dir, assets_dir = self._setup_dirs(tmp_path)
        songs_json = assets_dir / "songs.json"
        songs_json.write_text('{"summary": {}}')

        batch_meta = {
            "batch_id": "20260114_01",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 0,
            "highlights_duration": 60.0,
            "_upload_stats": {"uploaded": [], "skipped": []},
        }

        mock_upload_batch = MagicMock(return_value=batch_meta)

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        mocker.patch("birdbird.publish.generate_batch_id", return_value=("20260114_01", False))
        mocker.patch("birdbird.publish.upload_batch", mock_upload_batch)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[])
        mocker.patch("birdbird.publish.typer.echo")

        publish_to_r2(input_dir, self._r2_config())

        _, kwargs = mock_upload_batch.call_args
        assert kwargs["songs_path"] == songs_json

    def test_clip_count_from_detections(self, mock_s3_client, tmp_path, mocker):
        """clip_count in return dict reflects detections.json entry count."""
        input_dir, _ = self._setup_dirs(tmp_path)

        batch_meta = {
            "batch_id": "20260114_01",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 7,
            "highlights_duration": 60.0,
            "_upload_stats": {"uploaded": [], "skipped": []},
        }

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        mocker.patch("birdbird.publish.generate_batch_id", return_value=("20260114_01", False))
        mocker.patch("birdbird.publish.upload_batch", return_value=batch_meta)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[{}] * 7)
        mocker.patch("birdbird.publish.typer.echo")

        result = publish_to_r2(input_dir, self._r2_config())

        assert result["clip_count"] == 7

    def _setup_existing_batch(self, mock_s3_client, tmp_path, mocker, user_choice):
        """Helper: set up publish_to_r2 with an existing batch and user prompt."""
        input_dir, _ = self._setup_dirs(tmp_path)

        batch_meta = {
            "batch_id": "20260114_01",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 5,
            "highlights_duration": 60.0,
            "_upload_stats": {"uploaded": ["highlights.mp4"], "skipped": []},
        }

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        # batch_exists=True triggers the prompt
        mocker.patch("birdbird.publish.generate_batch_id", return_value=("20260114_01", True))
        mocker.patch("birdbird.publish.upload_batch", return_value=batch_meta)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[{}] * 5)
        mocker.patch("birdbird.publish.typer.echo")
        mocker.patch("birdbird.publish.typer.prompt", return_value=user_choice)

        return input_dir

    def test_existing_batch_option1_reuse(self, mock_s3_client, tmp_path, mocker):
        """User chooses option 1 to re-use existing batch."""
        input_dir = self._setup_existing_batch(mock_s3_client, tmp_path, mocker, user_choice=1)

        result = publish_to_r2(input_dir, self._r2_config())

        assert result["batch_id"] == "20260114_01"
        assert result["batch_replaced"] is True

    def test_existing_batch_option2_create_new(self, mock_s3_client, tmp_path, mocker):
        """User chooses option 2 to create a new batch sequence."""
        input_dir, _ = self._setup_dirs(tmp_path)

        batch_meta_new = {
            "batch_id": "20260114_02",
            "uploaded": "2026-01-14T12:00:00+00:00",
            "original_date": "2026-01-14",
            "start_date": "2026-01-14",
            "end_date": "2026-01-14",
            "clip_count": 5,
            "highlights_duration": 60.0,
            "_upload_stats": {"uploaded": ["highlights.mp4"], "skipped": []},
        }

        mocker.patch("birdbird.publish.create_r2_client", return_value=mock_s3_client)
        # First call returns existing batch, second call (create_new=True) returns new ID
        mocker.patch(
            "birdbird.publish.generate_batch_id",
            side_effect=[("20260114_01", True), ("20260114_02", False)],
        )
        mocker.patch("birdbird.publish.upload_batch", return_value=batch_meta_new)
        mocker.patch("birdbird.publish.update_latest_json")
        mocker.patch("birdbird.publish.cleanup_old_batches", return_value=[])
        mocker.patch("birdbird.publish.load_detections", return_value=[{}] * 5)
        mocker.patch("birdbird.publish.typer.echo")
        mocker.patch("birdbird.publish.typer.prompt", return_value=2)

        result = publish_to_r2(input_dir, self._r2_config())

        assert result["batch_id"] == "20260114_02"
        assert result["batch_replaced"] is False

    def test_existing_batch_option3_cancel(self, mock_s3_client, tmp_path, mocker):
        """User chooses option 3 to cancel."""
        import typer

        input_dir = self._setup_existing_batch(mock_s3_client, tmp_path, mocker, user_choice=3)

        with pytest.raises(typer.Exit):
            publish_to_r2(input_dir, self._r2_config())
