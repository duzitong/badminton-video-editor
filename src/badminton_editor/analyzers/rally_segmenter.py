"""Rally segmenter: group hit events into rallies based on timing gaps."""

from __future__ import annotations

from dataclasses import dataclass, field
from .audio_analyzer import HitEvent


@dataclass
class Rally:
    """A sequence of hits forming a rally."""
    index: int                           # rally number (0-based)
    hits: list[HitEvent] = field(default_factory=list)
    padding_before: float = 1.5          # seconds of video before first hit
    padding_after: float = 1.5           # seconds after last hit

    @property
    def start_time(self) -> float:
        """Start time including padding."""
        if not self.hits:
            return 0.0
        return max(0.0, self.hits[0].timestamp - self.padding_before)

    @property
    def end_time(self) -> float:
        """End time including padding."""
        if not self.hits:
            return 0.0
        return self.hits[-1].timestamp + self.padding_after

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def hit_count(self) -> int:
        return len(self.hits)

    @property
    def has_smash(self) -> bool:
        """Whether this rally contains a strong hit (likely smash)."""
        return any(h.is_strong for h in self.hits)

    @property
    def max_strength(self) -> float:
        if not self.hits:
            return 0.0
        return max(h.strength for h in self.hits)

    def score(self) -> float:
        """Score this rally for highlight potential.

        Higher = more interesting. Considers:
        - Number of hits (longer rallies are more exciting)
        - Presence of strong hits (smashes)
        - Hit variety (strength variance)
        """
        if self.hit_count < 2:
            return 0.0

        length_score = min(self.hit_count / 10.0, 1.0)  # cap at 10 hits
        smash_score = 1.0 if self.has_smash else 0.0
        strengths = [h.strength for h in self.hits]
        variety_score = float(max(strengths) - min(strengths)) / (max(strengths) + 0.01)

        return (length_score * 0.4) + (smash_score * 0.4) + (variety_score * 0.2)


@dataclass
class SegmentationConfig:
    """Configuration for rally segmentation."""
    gap_threshold: float = 3.0    # seconds of silence = rally boundary
    min_hits: int = 2             # minimum hits to count as a rally
    padding_before: float = 1.5   # seconds before first hit
    padding_after: float = 1.5    # seconds after last hit


def segment_rallies(
    hits: list[HitEvent],
    config: SegmentationConfig | None = None,
    video_duration: float | None = None,
) -> list[Rally]:
    """Group hits into rallies based on time gaps.

    A gap longer than `gap_threshold` seconds between consecutive hits
    marks a rally boundary.
    """
    cfg = config or SegmentationConfig()

    if not hits:
        return []

    # Sort by timestamp
    sorted_hits = sorted(hits, key=lambda h: h.timestamp)

    rallies: list[Rally] = []
    current_hits: list[HitEvent] = [sorted_hits[0]]

    for hit in sorted_hits[1:]:
        if hit.timestamp - current_hits[-1].timestamp > cfg.gap_threshold:
            # Gap detected — finalize current rally
            if len(current_hits) >= cfg.min_hits:
                rallies.append(Rally(
                    index=len(rallies),
                    hits=current_hits,
                    padding_before=cfg.padding_before,
                    padding_after=cfg.padding_after,
                ))
            current_hits = [hit]
        else:
            current_hits.append(hit)

    # Don't forget the last rally
    if len(current_hits) >= cfg.min_hits:
        rallies.append(Rally(
            index=len(rallies),
            hits=current_hits,
            padding_before=cfg.padding_before,
            padding_after=cfg.padding_after,
        ))

    # Clamp end times to video duration
    if video_duration is not None:
        for rally in rallies:
            if rally.end_time > video_duration:
                rally.padding_after = max(0, video_duration - rally.hits[-1].timestamp)

    return rallies


def rank_rallies(rallies: list[Rally], top_n: int | None = None) -> list[Rally]:
    """Rank rallies by highlight score, return top N."""
    ranked = sorted(rallies, key=lambda r: r.score(), reverse=True)
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked
