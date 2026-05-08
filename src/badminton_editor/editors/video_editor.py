"""Video editor: cut rallies, build highlights, apply effects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..analyzers.rally_segmenter import Rally, rank_rallies
from ..video_preprocessor import clip_video, concat_videos


@dataclass
class EditConfig:
    """Configuration for video editing operations."""
    output_dir: Path = Path("output")
    slow_motion_factor: float = 2.0     # 2x slow for smashes
    slow_motion_window: float = 1.0     # seconds around smash to slow down
    highlight_top_n: int = 5            # number of rallies in highlight reel
    rally_padding_before: float = 1.5   # already in Rally, but can override
    rally_padding_after: float = 1.5


def cut_rallies(
    video_path: str | Path,
    rallies: list[Rally],
    output_dir: str | Path,
) -> list[Path]:
    """Cut video into individual rally clips."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []

    for rally in rallies:
        out_path = out_dir / f"rally_{rally.index:03d}.mp4"
        clip_video(video_path, rally.start_time, rally.end_time, out_path)
        clips.append(out_path)

    return clips


def build_highlight_reel(
    video_path: str | Path,
    rallies: list[Rally],
    output_path: str | Path,
    config: EditConfig | None = None,
) -> Path:
    """Build a highlight reel from top-ranked rallies."""
    cfg = config or EditConfig()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Rank and select top rallies
    top_rallies = rank_rallies(rallies, top_n=cfg.highlight_top_n)

    # Sort selected rallies by time for chronological order
    top_rallies.sort(key=lambda r: r.start_time)

    # Cut individual clips
    temp_dir = output.parent / "_temp_highlights"
    temp_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []

    for i, rally in enumerate(top_rallies):
        clip_path = temp_dir / f"highlight_{i:03d}.mp4"
        clip_video(video_path, rally.start_time, rally.end_time, clip_path)
        clip_paths.append(clip_path)

    # Concatenate clips
    if clip_paths:
        concat_videos(clip_paths, output)

    # Cleanup temp files
    for p in clip_paths:
        p.unlink(missing_ok=True)
    temp_dir.rmdir()

    return output


def apply_slow_motion_on_smashes(
    video_path: str | Path,
    rallies: list[Rally],
    output_dir: str | Path,
    config: EditConfig | None = None,
) -> list[Path]:
    """Create rally clips with slow-motion applied to smash moments."""
    cfg = config or EditConfig()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []

    for rally in rallies:
        out_path = out_dir / f"rally_{rally.index:03d}_slowmo.mp4"

        if rally.has_smash:
            # Find the strongest hit (likely smash)
            smash_hit = max(rally.hits, key=lambda h: h.strength)
            smash_start = max(rally.start_time,
                              smash_hit.timestamp - cfg.slow_motion_window / 2)
            smash_end = min(rally.end_time,
                            smash_hit.timestamp + cfg.slow_motion_window / 2)

            # For simplicity, apply slow-mo to the entire smash segment
            clip_video(
                video_path, smash_start, smash_end, out_path,
                slow_factor=cfg.slow_motion_factor,
            )
        else:
            clip_video(video_path, rally.start_time, rally.end_time, out_path)

        clips.append(out_path)

    return clips
