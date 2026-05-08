"""Video preprocessor: extract audio and frames using ffmpeg."""

from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoInfo:
    path: Path
    duration: float  # seconds
    width: int
    height: int
    fps: float
    has_audio: bool


def probe_video(video_path: str | Path) -> VideoInfo:
    """Get video metadata using ffprobe."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)

    video_stream = next(
        (s for s in info["streams"] if s["codec_type"] == "video"), None
    )
    audio_stream = next(
        (s for s in info["streams"] if s["codec_type"] == "audio"), None
    )

    if video_stream is None:
        raise ValueError(f"No video stream found in {path}")

    fps_parts = video_stream.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0

    return VideoInfo(
        path=path,
        duration=float(info["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        has_audio=audio_stream is not None,
    )


def extract_audio(
    video_path: str | Path,
    output_path: str | Path,
    sample_rate: int = 44100,
) -> Path:
    """Extract audio track as mono WAV."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", str(sample_rate), "-ac", "1",
            str(output),
        ],
        capture_output=True, check=True,
    )
    return output


def extract_frame(
    video_path: str | Path,
    timestamp: float,
    output_path: str | Path,
    quality: int = 2,
) -> Path:
    """Extract a single frame at the given timestamp."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", f"{timestamp:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", str(quality),
            str(output),
        ],
        capture_output=True, check=True,
    )
    return output


def extract_frames_batch(
    video_path: str | Path,
    timestamps: list[float],
    output_dir: str | Path,
    prefix: str = "frame",
) -> list[Path]:
    """Extract multiple frames at given timestamps."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for ts in timestamps:
        out_path = out_dir / f"{prefix}_{ts:.3f}s.jpg"
        extract_frame(video_path, ts, out_path)
        paths.append(out_path)

    return paths


def clip_video(
    video_path: str | Path,
    start: float,
    end: float,
    output_path: str | Path,
    slow_factor: float = 1.0,
) -> Path:
    """Clip a segment of video. slow_factor > 1 means slow motion."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(video_path),
        "-t", f"{end - start:.3f}",
    ]

    if slow_factor != 1.0:
        # Slow motion via setpts and atempo
        cmd.extend([
            "-filter_complex",
            f"[0:v]setpts={slow_factor}*PTS[v];[0:a]atempo={1/slow_factor}[a]",
            "-map", "[v]", "-map", "[a]",
        ])

    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", str(output)])
    subprocess.run(cmd, capture_output=True, check=True)
    return output


def concat_videos(
    video_paths: list[str | Path],
    output_path: str | Path,
) -> Path:
    """Concatenate multiple video clips into one."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Write concat list file
    list_file = output.parent / "_concat_list.txt"
    with open(list_file, "w") as f:
        for p in video_paths:
            f.write(f"file '{Path(p).resolve()}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ],
        capture_output=True, check=True,
    )

    list_file.unlink(missing_ok=True)
    return output
