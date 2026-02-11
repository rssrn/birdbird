"""Species identification using BioCLIP on remote GPU.

@author Claude Opus 4.5 Anthropic
"""

import json
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from .config import RemoteConfig, SpeciesConfig, get_species_config


@dataclass
class Detection:
    """A single species detection from a frame.

    @author Claude Opus 4.5 Anthropic
    """

    timestamp_s: float
    species: str
    confidence: float
    runners_up: list[dict[str, float]]  # [{"species": str, "confidence": float}, ...]


@dataclass
class SpeciesResults:
    """Results from species identification.

    @author Claude Opus 4.5 Anthropic
    """

    generated_at: str
    processing_mode: str
    processing_time_s: float
    highlights_duration_s: float
    samples_per_minute: float
    total_frames: int
    species_summary: dict[str, dict]  # {"Blue Tit": {"count": 5, "avg_confidence": 0.87}, ...}
    detections: list[Detection]


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe.

    @author Claude Opus 4.5 Anthropic
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def sample_frames_from_video(
    video_path: Path,
    output_dir: Path,
    samples_per_minute: float = 6.0,
) -> list[tuple[Path, float]]:
    """Extract frames from video at regular intervals.

    Returns list of (frame_path, timestamp_s) tuples.

    @author Claude Opus 4.5 Anthropic
    """
    duration = get_video_duration(video_path)
    interval_s = 60.0 / samples_per_minute

    # Calculate timestamps to sample
    timestamps = []
    t = interval_s / 2  # Start halfway through first interval
    while t < duration:
        timestamps.append(t)
        t += interval_s

    if not timestamps:
        # Video shorter than one sample interval - take middle frame
        timestamps = [duration / 2]

    # Extract frames using ffmpeg
    frames = []
    for i, ts in enumerate(tqdm(timestamps, desc="Sampling frames")):
        frame_path = output_dir / f"frame_{i:04d}.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(ts),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",  # High quality JPEG
            str(frame_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        frames.append((frame_path, ts))

    return frames


def parse_labels_file(labels_path: Path) -> list[str]:
    """Parse species labels from file.

    Handles comments (lines starting with #) and blank lines.

    @author Claude Opus 4.5 Anthropic
    """
    labels = []
    with open(labels_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                labels.append(line)
    return labels


def check_remote_connection(config: RemoteConfig) -> tuple[bool, str]:
    """Test SSH connection to remote host.

    Returns (success, message).

    @author Claude Opus 4.5 Anthropic
    """
    # Simple SSH connection test
    cmd = ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", config.host, "echo ok"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "ok" in result.stdout:
            return True, "Connection successful"
        return False, f"SSH failed: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "Connection timed out"
    except Exception as e:
        return False, f"Connection error: {e}"


class RemoteProcessor:
    """Process frames on a remote GPU via SSH.

    @author Claude Opus 4.5 Anthropic
    """

    def __init__(self, config: RemoteConfig, labels: list[str], min_confidence: float = 0.5):
        self.config = config
        self.labels = labels
        self.min_confidence = min_confidence

    def process(
        self,
        frames: list[tuple[Path, float]],
        progress_callback=None,
    ) -> list[Detection]:
        """Send frames to remote and process with BioCLIP.

        @author Claude Opus 4.5 Anthropic
        """
        if not frames:
            return []

        # Create remote temp directory
        # Returns (scp_path, execution_path) - for WSL these differ
        scp_path, exec_path = self._create_remote_dir()

        try:
            # Transfer frames to remote (with progress bar)
            frame_paths = [f[0] for f in frames]
            self._transfer_files(frame_paths, scp_path, show_progress=True)

            # Transfer labels file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                for label in self.labels:
                    f.write(f"{label}\n")
                labels_local = Path(f.name)

            self._transfer_files([labels_local], scp_path)
            labels_local.unlink()

            # Create and transfer inference script
            script_content = self._generate_inference_script()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(script_content)
                script_local = Path(f.name)

            self._transfer_files([script_local], scp_path)
            script_local.unlink()

            # Run inference on remote
            if progress_callback:
                progress_callback("Running BioCLIP inference on remote GPU...")

            results_json = self._run_remote_inference(exec_path)

            # Parse results and create Detection objects
            detections = []
            for i, (frame_path, timestamp) in enumerate(frames):
                if str(i) in results_json:
                    result = results_json[str(i)]
                    if result["confidence"] >= self.min_confidence:
                        detections.append(Detection(
                            timestamp_s=timestamp,
                            species=result["species"],
                            confidence=result["confidence"],
                            runners_up=result.get("runners_up", []),
                        ))

            return detections

        finally:
            # Cleanup remote directory
            self._cleanup_remote(scp_path)

    def _create_remote_dir(self) -> tuple[str, str]:
        """Create temporary directory on remote host.

        Returns (windows_path, wsl_path) for WSL targets, or (path, path) for Linux.

        For WSL targets, creates directory in Windows temp folder which is
        accessible from both Windows (for SCP) and WSL (via /mnt/c).

        @author Claude Opus 4.5 Anthropic
        """
        if self.config.shell == "wsl":
            # For WSL, create a temp directory in Windows user's temp folder
            # This is accessible via SCP (Windows path) and WSL (/mnt/c/...)
            import uuid
            dir_name = f"birdbird_{uuid.uuid4().hex[:8]}"

            # Get Windows temp path and create directory
            # Use cmd.exe for simpler quoting
            cmd = f'cmd /c "mkdir %TEMP%\\{dir_name} && echo %TEMP%\\{dir_name}"'
            ssh_cmd = ["ssh", self.config.host, cmd]
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
            windows_path = result.stdout.strip()

            # Convert to WSL path: C:\Users\... -> /mnt/c/Users/...
            wsl_path = self._windows_to_wsl_path(windows_path)

            return (windows_path, wsl_path)
        else:
            cmd = "mktemp -d"
            ssh_cmd = ["ssh", self.config.host, cmd]
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
            path = result.stdout.strip()
            return (path, path)

    def _windows_to_wsl_path(self, windows_path: str) -> str:
        """Convert Windows path to WSL path.

        C:\\Users\\user\\AppData -> /mnt/c/Users/user/AppData

        @author Claude Opus 4.5 Anthropic
        """
        # Handle both backslash and forward slash
        path = windows_path.replace("\\", "/")
        # C:/Users/... -> /mnt/c/Users/...
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].lower()
            return f"/mnt/{drive}{path[2:]}"
        return path

    def _transfer_files(
        self,
        local_paths: list[Path],
        scp_path: str,
        show_progress: bool = False,
    ) -> None:
        """Transfer files to remote host using scp.

        For WSL targets, scp_path is a Windows path (e.g., C:\\Users\\...\\Temp\\birdbird_xxx)
        For native Linux targets, scp_path is a Linux path.

        @author Claude Opus 4.5 Anthropic
        """
        paths_iter: list[Path] | tqdm[Path] = local_paths
        if show_progress:
            paths_iter = tqdm(local_paths, desc="Transferring frames")

        for path in paths_iter:
            remote_path = f"{self.config.host}:{scp_path}/"
            cmd = ["scp", "-q", str(path), remote_path]
            subprocess.run(cmd, check=True)

    def _generate_inference_script(self) -> str:
        """Generate the Python script to run on remote.

        @author Claude Opus 4.5 Anthropic
        """
        return '''#!/usr/bin/env python3
"""BioCLIP inference script for remote execution.

@author Claude Opus 4.5 Anthropic
"""

import json
import sys
from pathlib import Path

def main():
    from bioclip import CustomLabelsClassifier

    work_dir = Path(sys.argv[1])
    labels_file = work_dir / "labels.txt"
    output_file = work_dir / "results.json"

    # Load labels
    with open(labels_file) as f:
        labels = [line.strip() for line in f if line.strip()]

    # Initialize classifier with GPU if available
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading BioCLIP with {len(labels)} labels on {device}...", file=sys.stderr)
    classifier = CustomLabelsClassifier(labels, device=device)
    print("BioCLIP loaded", file=sys.stderr)

    # Find all frame images
    frames = sorted(work_dir.glob("frame_*.jpg"))
    print(f"Processing {len(frames)} frames...", file=sys.stderr)

    results = {}
    for i, frame_path in enumerate(frames):
        # Classify - returns list of dicts with 'classification' and 'score' keys
        predictions = classifier.predict(str(frame_path))

        # Sort by score (descending)
        sorted_preds = sorted(predictions, key=lambda x: x["score"], reverse=True)

        top = sorted_preds[0]
        runners_up = [
            {"species": p["classification"], "confidence": round(p["score"], 4)}
            for p in sorted_preds[1:4]  # Top 3 runners-up
        ]

        results[str(i)] = {
            "species": top["classification"],
            "confidence": round(top["score"], 4),
            "runners_up": runners_up,
        }

        # Progress indicator
        print(f"Processed {i+1}/{len(frames)}: {top['classification']} ({top['score']:.1%})", file=sys.stderr)

    # Write results
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Completed {len(frames)} frames", file=sys.stderr)

if __name__ == "__main__":
    main()
'''

    def _run_remote_inference(self, exec_path: str) -> dict:
        """Execute inference script on remote and return results.

        exec_path is a WSL path for WSL targets, or Linux path for Linux targets.

        @author Claude Opus 4.5 Anthropic
        """
        # Build the command to run on remote
        python_activate = f"source {self.config.python_env}/bin/activate"

        # Rename the labels file to expected name
        rename_cmd = f"mv {exec_path}/*.txt {exec_path}/labels.txt 2>/dev/null || true"

        # Find and run the script
        script_cmd = f"python3 {exec_path}/*.py {exec_path}"

        script_content = f"{python_activate} && {rename_cmd} && {script_cmd}"

        if self.config.shell == "wsl":
            # For WSL over SSH to Windows, use stdin to avoid quote escaping issues
            # PowerShell + WSL + bash quote handling is extremely complex
            ssh_cmd = ["ssh", self.config.host, "wsl", "bash", "-s"]
        else:
            ssh_cmd = ["ssh", self.config.host, "bash", "-s"]

        result = subprocess.run(
            ssh_cmd,
            input=script_content,
            capture_output=True,
            text=True,
            timeout=self.config.timeout,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Remote inference failed: {result.stderr}")

        # Fetch results file
        results_json = self._fetch_results(exec_path)
        return results_json

    def _fetch_results(self, exec_path: str) -> dict:
        """Fetch results.json from remote host.

        exec_path is a WSL path for WSL targets, or Linux path for Linux targets.

        @author Claude Opus 4.5 Anthropic
        """
        if self.config.shell == "wsl":
            # For WSL, use cat over SSH to fetch the file (exec_path is a WSL path)
            cmd = ["ssh", self.config.host, "wsl", "cat", f"{exec_path}/results.json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parsed: dict[str, Any] = json.loads(result.stdout)
            return parsed
        else:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                local_path = Path(f.name)

            remote_path = f"{self.config.host}:{exec_path}/results.json"
            cmd = ["scp", "-q", remote_path, str(local_path)]
            subprocess.run(cmd, check=True)

            with open(local_path) as f:
                results: dict[str, Any] = json.load(f)

            local_path.unlink()
            return results

    def _cleanup_remote(self, scp_path: str) -> None:
        """Remove temporary directory on remote.

        scp_path is a Windows path for WSL targets, or Linux path for Linux targets.

        @author Claude Opus 4.5 Anthropic
        """
        try:
            if self.config.shell == "wsl":
                # Use cmd.exe to remove the Windows directory
                cmd = f'cmd /c "rmdir /s /q {scp_path}"'
                ssh_cmd = ["ssh", self.config.host, cmd]
            else:
                ssh_cmd = ["ssh", self.config.host, "rm", "-rf", scp_path]

            subprocess.run(ssh_cmd, capture_output=True, timeout=30)
        except Exception:
            pass  # nosec B110


def aggregate_species_summary(detections: list[Detection]) -> dict[str, dict]:
    """Aggregate detections into species summary.

    @author Claude Opus 4.5 Anthropic
    """
    species_data: dict[str, list[float]] = {}

    for det in detections:
        if det.species not in species_data:
            species_data[det.species] = []
        species_data[det.species].append(det.confidence)

    summary = {}
    for species, confidences in sorted(species_data.items(), key=lambda x: -len(x[1])):
        summary[species] = {
            "count": len(confidences),
            "avg_confidence": round(sum(confidences) / len(confidences), 3),
        }

    return summary


def identify_species(
    highlights_path: Path,
    config: SpeciesConfig | None = None,
    progress_callback=None,
) -> SpeciesResults:
    """Run species identification on highlights video.

    @author Claude Opus 4.5 Anthropic
    """
    if config is None:
        config = get_species_config()

    if not highlights_path.exists():
        raise ValueError(f"Highlights video not found: {highlights_path}")

    # Check remote connection if using remote mode
    if config.processing_mode == "remote":
        if config.remote is None:
            raise ValueError(
                "Remote processing mode requires remote configuration.\n"
                "Add to ~/.birdbird/config.json:\n"
                '  "species": {\n'
                '    "processing": {\n'
                '      "mode": "remote",\n'
                '      "remote": {\n'
                '        "host": "user@hostname",\n'
                '        "shell": "wsl",\n'
                '        "python_env": "~/bioclip_env"\n'
                '      }\n'
                '    }\n'
                '  }'
            )

        if progress_callback:
            progress_callback(f"Checking connection to {config.remote.host}...")

        connected, msg = check_remote_connection(config.remote)
        if not connected:
            raise RuntimeError(f"Remote GPU ({config.remote.host}) is not accessible: {msg}")

    elif config.processing_mode == "local":
        raise ValueError(
            "Local processing is disabled to prevent system slowdown.\n"
            "Configure remote GPU in ~/.birdbird/config.json or use --mode remote"
        )

    elif config.processing_mode == "cloud":
        raise ValueError("Cloud processing mode is not yet implemented")

    start_time = time.perf_counter()

    # Get video duration
    duration = get_video_duration(highlights_path)

    # Load labels
    labels = parse_labels_file(config.get_labels_file())

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Sample frames from video (tqdm progress bar shown)
        frames = sample_frames_from_video(
            highlights_path,
            temp_path,
            samples_per_minute=config.samples_per_minute,
        )

        # Process frames (tqdm progress bar shown for transfers)
        assert config.remote is not None, "Remote config required for remote processing"  # nosec B101
        processor = RemoteProcessor(
            config=config.remote,
            labels=labels,
            min_confidence=config.min_confidence,
        )

        detections = processor.process(frames, progress_callback=progress_callback)

    processing_time = time.perf_counter() - start_time

    # Aggregate results
    summary = aggregate_species_summary(detections)

    return SpeciesResults(
        generated_at=datetime.now(timezone.utc).isoformat(),
        processing_mode=config.processing_mode,
        processing_time_s=round(processing_time, 2),
        highlights_duration_s=round(duration, 1),
        samples_per_minute=config.samples_per_minute,
        total_frames=len(frames),
        species_summary=summary,
        detections=detections,
    )


def save_species_results(results: SpeciesResults, output_path: Path) -> None:
    """Save species results to JSON file.

    @author Claude Opus 4.5 Anthropic
    """
    data = {
        "generated_at": results.generated_at,
        "processing_mode": results.processing_mode,
        "processing_time_s": results.processing_time_s,
        "highlights_duration_s": results.highlights_duration_s,
        "samples_per_minute": results.samples_per_minute,
        "total_frames": results.total_frames,
        "species_summary": results.species_summary,
        "detections": [
            {
                "timestamp_s": d.timestamp_s,
                "species": d.species,
                "confidence": d.confidence,
                "runners_up": d.runners_up,
            }
            for d in results.detections
        ],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
