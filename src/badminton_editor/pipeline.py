"""Main pipeline: orchestrate analysis and editing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .video_preprocessor import probe_video, extract_audio, extract_frames_batch
from .analyzers.audio_analyzer import (
    AudioAnalysisConfig,
    AudioAnalysisResult,
    analyze_full_video_audio,
)
from .analyzers.rally_segmenter import (
    Rally,
    SegmentationConfig,
    segment_rallies,
    rank_rallies,
)
from .editors.video_editor import (
    EditConfig,
    cut_rallies,
    build_highlight_reel,
)


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""
    output_dir: str = "output"
    audio: AudioAnalysisConfig = field(default_factory=AudioAnalysisConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    edit: EditConfig = field(default_factory=EditConfig)
    # LLM settings (optional)
    llm_provider: str | None = None       # "openai" or "anthropic"
    llm_api_key: str | None = None
    llm_model: str | None = None
    # Frame extraction around hits
    frame_offsets: list[float] = field(
        default_factory=lambda: [-0.5, 0.0, 0.5]
    )


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""
    video_path: str = ""
    duration: float = 0.0
    total_hits: int = 0
    total_rallies: int = 0
    rallies: list[dict[str, Any]] = field(default_factory=list)
    rally_clips: list[str] = field(default_factory=list)
    highlight_reel: str = ""
    analysis_json: str = ""

    def summary(self) -> str:
        lines = [
            f"Video: {self.video_path}",
            f"Duration: {self.duration:.1f}s ({self.duration/60:.1f} min)",
            f"Hits detected: {self.total_hits}",
            f"Rallies found: {self.total_rallies}",
        ]
        for r in self.rallies:
            lines.append(
                f"  Rally {r['index']}: {r['hit_count']} hits, "
                f"{r['duration']:.1f}s, score={r['score']:.2f}"
                f"{' ⚡SMASH' if r['has_smash'] else ''}"
            )
        if self.highlight_reel:
            lines.append(f"Highlight reel: {self.highlight_reel}")
        return "\n".join(lines)


class Pipeline:
    """Main processing pipeline for badminton video editing."""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()

    def analyze(self, video_path: str | Path) -> PipelineResult:
        """Run analysis only (no video editing). Returns structured results."""
        video_path = Path(video_path)
        out_dir = Path(self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Probe video
        info = probe_video(video_path)
        print(f"[1/4] Video: {info.width}x{info.height}, {info.fps}fps, "
              f"{info.duration:.1f}s, audio={'yes' if info.has_audio else 'no'}")

        if not info.has_audio:
            raise ValueError("Video has no audio track — cannot analyze hits")

        # Step 2: Extract audio
        audio_path = out_dir / "audio.wav"
        print("[2/4] Extracting audio...")
        extract_audio(video_path, audio_path, self.config.audio.sample_rate)

        # Step 3: Analyze audio for hits
        print("[3/4] Analyzing audio for hit sounds...")
        audio_result = analyze_full_video_audio(audio_path, self.config.audio)
        print(f"       Found {len(audio_result.hits)} hits "
              f"({len(audio_result.strong_hits)} strong)")

        # Step 4: Segment into rallies
        print("[4/4] Segmenting rallies...")
        rallies = segment_rallies(
            audio_result.hits, self.config.segmentation, info.duration,
        )
        print(f"       Found {len(rallies)} rallies")

        # Build result
        result = PipelineResult(
            video_path=str(video_path),
            duration=info.duration,
            total_hits=len(audio_result.hits),
            total_rallies=len(rallies),
            rallies=[
                {
                    "index": r.index,
                    "start": r.start_time,
                    "end": r.end_time,
                    "duration": r.duration,
                    "hit_count": r.hit_count,
                    "has_smash": r.has_smash,
                    "score": r.score(),
                    "hit_times": [h.timestamp for h in r.hits],
                }
                for r in rallies
            ],
        )

        # Save analysis JSON
        result.analysis_json = str(out_dir / "analysis.json")
        with open(result.analysis_json, "w") as f:
            json.dump(result.rallies, f, indent=2)

        return result

    def edit(
        self,
        video_path: str | Path,
        result: PipelineResult | None = None,
        cut_rallies_flag: bool = True,
        highlight_reel_flag: bool = True,
    ) -> PipelineResult:
        """Run full pipeline: analyze + edit video."""
        video_path = Path(video_path)
        out_dir = Path(self.config.output_dir)

        # Analyze first if no result provided
        if result is None:
            result = self.analyze(video_path)

        # Reconstruct Rally objects from result data
        from .analyzers.audio_analyzer import HitEvent
        rallies = []
        for r_data in result.rallies:
            hits = [
                HitEvent(timestamp=t, strength=1.0, is_strong=False)
                for t in r_data["hit_times"]
            ]
            # Mark the strongest as strong if rally has_smash
            if r_data["has_smash"] and hits:
                hits[0] = HitEvent(
                    timestamp=hits[0].timestamp,
                    strength=10.0,
                    is_strong=True,
                )
            rallies.append(Rally(
                index=r_data["index"],
                hits=hits,
                padding_before=self.config.segmentation.padding_before,
                padding_after=self.config.segmentation.padding_after,
            ))

        # Cut individual rally clips
        if cut_rallies_flag and rallies:
            print("[edit] Cutting rally clips...")
            clips_dir = out_dir / "rallies"
            clip_paths = cut_rallies(video_path, rallies, clips_dir)
            result.rally_clips = [str(p) for p in clip_paths]
            print(f"       Cut {len(clip_paths)} rally clips")

        # Build highlight reel
        if highlight_reel_flag and rallies:
            print("[edit] Building highlight reel...")
            hl_path = out_dir / "highlight_reel.mp4"
            build_highlight_reel(
                video_path, rallies, hl_path, self.config.edit,
            )
            result.highlight_reel = str(hl_path)
            print(f"       Highlight reel: {hl_path}")

        return result

    def extract_key_frames(
        self, video_path: str | Path, result: PipelineResult,
    ) -> list[Path]:
        """Extract frames around each hit for LLM analysis."""
        out_dir = Path(self.config.output_dir) / "frames"
        timestamps = []
        for r in result.rallies:
            for ht in r["hit_times"]:
                for offset in self.config.frame_offsets:
                    t = ht + offset
                    if 0 <= t <= result.duration:
                        timestamps.append(t)

        # Deduplicate and sort
        timestamps = sorted(set(round(t, 3) for t in timestamps))
        return extract_frames_batch(video_path, timestamps, out_dir)
