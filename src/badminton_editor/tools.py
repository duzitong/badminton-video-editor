"""Three simple tools for an AI agent to edit badminton videos.

Usage by an agent:
  1. analyze_audio("match.mp4")       → list of hit timestamps + strengths
  2. screenshot("match.mp4", 14.5)    → saves a frame, agent views it
  3. cut_segments("match.mp4", [...]) → cuts & concats segments into output
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np


# ── Tool 1: Audio Analysis ──────────────────────────────────────────────

def analyze_audio(
    video_path: str,
    output_dir: str = "test-output",
    delta: float = 0.3,
    debounce: float = 0.3,
) -> dict:
    """Analyze audio from a video to detect hit sounds.

    Returns a dict with:
      - hits: list of {time, strength, is_strong}
      - duration: total video duration in seconds
      - summary: text summary an agent can read
    """
    video = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "audio.wav"

    # Extract audio
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video),
         "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
         str(wav_path)],
        capture_output=True, check=True,
    )

    # Load and analyze
    y, sr = librosa.load(str(wav_path), sr=44100)
    duration = len(y) / sr

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr, onset_envelope=onset_env,
        delta=delta, wait=10,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    if len(onset_times) == 0:
        return {"hits": [], "duration": duration, "summary": "No hits detected."}

    # Debounce
    times = [float(onset_times[0])]
    frames = [onset_frames[0]]
    for t, f in zip(onset_times[1:], onset_frames[1:]):
        if t - times[-1] > debounce:
            times.append(float(t))
            frames.append(f)

    # Classify strength
    strengths = onset_env[frames]
    threshold = np.percentile(strengths, 70)

    hits = [
        {"time": round(t, 2), "strength": round(float(s), 2), "is_strong": bool(s >= threshold)}
        for t, s in zip(times, strengths)
    ]

    # Build a concise summary for the agent
    # Group into clusters (gaps > 3s)
    clusters = []
    current = [hits[0]]
    for h in hits[1:]:
        if h["time"] - current[-1]["time"] > 3.0:
            clusters.append(current)
            current = [h]
        else:
            current.append(h)
    clusters.append(current)

    lines = [f"Duration: {duration:.1f}s ({duration/60:.1f}min), {len(hits)} hits, {len(clusters)} rally-like clusters"]
    for i, cl in enumerate(clusters):
        t0 = cl[0]["time"]
        t1 = cl[-1]["time"]
        n_strong = sum(1 for h in cl if h["is_strong"])
        lines.append(f"  Cluster {i}: {t0:.1f}s–{t1:.1f}s, {len(cl)} hits ({n_strong} strong)")

    result = {
        "hits": hits,
        "duration": round(duration, 2),
        "clusters": [
            {"start": cl[0]["time"], "end": cl[-1]["time"],
             "hit_count": len(cl), "hits": cl}
            for cl in clusters
        ],
        "summary": "\n".join(lines),
    }

    # Save JSON for reference
    with open(out_dir / "audio_analysis.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


# ── Tool 2: Screenshot ──────────────────────────────────────────────────

def screenshot(
    video_path: str,
    time_seconds: float,
    output_dir: str = "test-output",
) -> str:
    """Grab a single frame from the video at the given timestamp.

    Returns the path to the saved image so the agent can view it.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"frame_{time_seconds:.2f}s.jpg"

    subprocess.run(
        ["ffmpeg", "-y",
         "-ss", f"{time_seconds:.3f}",
         "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2",
         str(out_path)],
        capture_output=True, check=True,
    )
    return str(out_path)


# ── Tool 3: Cut & Concat Segments ───────────────────────────────────────

def cut_segments(
    video_path: str,
    segments: list[dict],
    output_path: str = "test-output/edited.mp4",
) -> str:
    """Cut segments from video and concatenate them.

    Args:
        video_path: source video
        segments: list of {"start": float, "end": float} in seconds
        output_path: where to save the final video

    Returns the output path.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise ValueError("No segments provided")

    # Cut each segment into a temp file
    tmp_dir = Path(tempfile.mkdtemp())
    clip_paths = []

    for i, seg in enumerate(segments):
        clip = tmp_dir / f"seg_{i:04d}.mp4"
        duration = seg["end"] - seg["start"]
        subprocess.run(
            ["ffmpeg", "-y",
             "-ss", f"{seg['start']:.3f}",
             "-i", str(video_path),
             "-t", f"{duration:.3f}",
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "aac",
             str(clip)],
            capture_output=True, check=True,
        )
        clip_paths.append(clip)

    # Concat
    concat_list = tmp_dir / "list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "concat", "-safe", "0",
         "-i", str(concat_list),
         "-c", "copy",
         str(out)],
        capture_output=True, check=True,
    )

    # Cleanup temp
    for p in clip_paths:
        p.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)
    tmp_dir.rmdir()

    return str(out)
