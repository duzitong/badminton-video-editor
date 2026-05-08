"""Audio analyzer: detect shuttle hit sounds using onset detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np


@dataclass
class HitEvent:
    """A detected hit sound event."""
    timestamp: float       # seconds
    strength: float        # onset strength (relative)
    is_strong: bool        # whether this is a particularly loud hit (e.g., smash)
    frequency_peak: float = 0.0  # dominant frequency around hit


@dataclass
class AudioAnalysisConfig:
    """Tunable parameters for audio analysis."""
    sample_rate: int = 44100
    onset_delta: float = 0.3        # minimum onset strength
    onset_wait: int = 10            # minimum frames between onsets
    debounce_seconds: float = 0.3   # merge events closer than this
    strong_percentile: float = 70   # top N% = "strong" hits
    # Frequency analysis window around each hit (samples)
    freq_window: int = 2048


@dataclass
class AudioAnalysisResult:
    """Result of analyzing audio for hit events."""
    hits: list[HitEvent] = field(default_factory=list)
    duration: float = 0.0
    sample_rate: int = 44100

    @property
    def hit_times(self) -> list[float]:
        return [h.timestamp for h in self.hits]

    @property
    def strong_hits(self) -> list[HitEvent]:
        return [h for h in self.hits if h.is_strong]

    def hits_in_range(self, start: float, end: float) -> list[HitEvent]:
        return [h for h in self.hits if start <= h.timestamp <= end]


def analyze_audio(
    audio_path: str | Path,
    config: AudioAnalysisConfig | None = None,
    duration: float | None = None,
    offset: float = 0.0,
) -> AudioAnalysisResult:
    """Analyze audio file for shuttle hit sounds.

    Uses librosa onset detection with debouncing and strength classification.
    """
    cfg = config or AudioAnalysisConfig()

    y, sr = librosa.load(
        str(audio_path),
        sr=cfg.sample_rate,
        duration=duration,
        offset=offset,
    )

    total_duration = len(y) / sr

    # Onset detection
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr,
        onset_envelope=onset_env,
        delta=cfg.onset_delta,
        wait=cfg.onset_wait,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    if len(onset_times) == 0:
        return AudioAnalysisResult(duration=total_duration, sample_rate=sr)

    # Debounce: merge onsets closer than threshold
    debounced_times = [onset_times[0]]
    debounced_frames = [onset_frames[0]]
    for t, f in zip(onset_times[1:], onset_frames[1:]):
        if t - debounced_times[-1] > cfg.debounce_seconds:
            debounced_times.append(t)
            debounced_frames.append(f)

    debounced_times = np.array(debounced_times)
    debounced_frames = np.array(debounced_frames)

    # Get strengths at debounced positions
    strengths = onset_env[debounced_frames]
    strength_threshold = np.percentile(strengths, cfg.strong_percentile)

    # Build hit events with frequency analysis
    hits = []
    for t, s in zip(debounced_times, strengths):
        sample_idx = int(t * sr)
        half = cfg.freq_window // 2
        clip = y[max(0, sample_idx - half):sample_idx + half]

        freq_peak = 0.0
        if len(clip) > 0:
            fft = np.abs(np.fft.rfft(clip))
            freqs = np.fft.rfftfreq(len(clip), 1 / sr)
            freq_peak = float(freqs[np.argmax(fft)])

        hits.append(HitEvent(
            timestamp=float(t) + offset,
            strength=float(s),
            is_strong=bool(s >= strength_threshold),
            frequency_peak=freq_peak,
        ))

    return AudioAnalysisResult(
        hits=hits,
        duration=total_duration,
        sample_rate=sr,
    )


def analyze_full_video_audio(
    audio_path: str | Path,
    config: AudioAnalysisConfig | None = None,
    chunk_seconds: float = 300.0,
) -> AudioAnalysisResult:
    """Analyze long audio files in chunks to manage memory.

    Processes audio in chunks (default 5 min) and merges results.
    """
    cfg = config or AudioAnalysisConfig()
    path = Path(audio_path)

    # Get total duration
    total_duration = librosa.get_duration(path=str(path))

    all_hits: list[HitEvent] = []
    offset = 0.0

    while offset < total_duration:
        chunk_dur = min(chunk_seconds, total_duration - offset)
        result = analyze_audio(
            path, config=cfg, duration=chunk_dur, offset=offset,
        )
        all_hits.extend(result.hits)
        offset += chunk_dur

    return AudioAnalysisResult(
        hits=all_hits,
        duration=total_duration,
        sample_rate=cfg.sample_rate,
    )
