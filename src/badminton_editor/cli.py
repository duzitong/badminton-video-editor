"""CLI entry point for badminton video editor."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .pipeline import Pipeline, PipelineConfig
from .analyzers.audio_analyzer import AudioAnalysisConfig
from .analyzers.rally_segmenter import SegmentationConfig
from .editors.video_editor import EditConfig


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Badminton Video Editor — AI-powered rally detection and highlight generation."""
    pass


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.option("-o", "--output", default="output", help="Output directory")
@click.option("--gap", default=3.0, help="Gap threshold for rally boundaries (seconds)")
@click.option("--min-hits", default=2, help="Minimum hits per rally")
@click.option("--delta", default=0.3, help="Onset detection sensitivity (lower = more sensitive)")
@click.option("--debounce", default=0.3, help="Minimum seconds between detected hits")
def analyze(video: str, output: str, gap: float, min_hits: int, delta: float, debounce: float):
    """Analyze a badminton video for rallies and hits.

    Extracts audio, detects hit sounds, and segments into rallies.
    Results saved as JSON.
    """
    config = PipelineConfig(
        output_dir=output,
        audio=AudioAnalysisConfig(onset_delta=delta, debounce_seconds=debounce),
        segmentation=SegmentationConfig(gap_threshold=gap, min_hits=min_hits),
    )

    pipeline = Pipeline(config)
    result = pipeline.analyze(video)
    click.echo("\n" + result.summary())
    click.echo(f"\nAnalysis saved to: {result.analysis_json}")


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.option("-o", "--output", default="output", help="Output directory")
@click.option("--gap", default=3.0, help="Gap threshold for rally boundaries (seconds)")
@click.option("--min-hits", default=2, help="Minimum hits per rally")
@click.option("--delta", default=0.3, help="Onset detection sensitivity")
@click.option("--debounce", default=0.3, help="Debounce seconds between hits")
@click.option("--top-n", default=5, help="Number of rallies in highlight reel")
@click.option("--no-rally-clips", is_flag=True, help="Skip cutting individual rally clips")
@click.option("--no-highlights", is_flag=True, help="Skip building highlight reel")
def edit(
    video: str, output: str, gap: float, min_hits: int,
    delta: float, debounce: float, top_n: int,
    no_rally_clips: bool, no_highlights: bool,
):
    """Analyze and edit a badminton video.

    Detects rallies, cuts them into clips, and builds a highlight reel.
    """
    config = PipelineConfig(
        output_dir=output,
        audio=AudioAnalysisConfig(onset_delta=delta, debounce_seconds=debounce),
        segmentation=SegmentationConfig(gap_threshold=gap, min_hits=min_hits),
        edit=EditConfig(highlight_top_n=top_n),
    )

    pipeline = Pipeline(config)
    result = pipeline.edit(
        video,
        cut_rallies_flag=not no_rally_clips,
        highlight_reel_flag=not no_highlights,
    )
    click.echo("\n" + result.summary())


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.option("-o", "--output", default="output", help="Output directory")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default="openai")
@click.option("--api-key", envvar="LLM_API_KEY", help="LLM API key (or set LLM_API_KEY env var)")
@click.option("--model", default=None, help="Model name override")
def analyze_frames(video: str, output: str, provider: str, api_key: str, model: str):
    """Extract key frames and analyze with LLM (requires API key)."""
    if not api_key:
        click.echo("Error: API key required. Use --api-key or set LLM_API_KEY env var.", err=True)
        sys.exit(1)

    config = PipelineConfig(
        output_dir=output,
        llm_provider=provider,
        llm_api_key=api_key,
        llm_model=model,
    )

    pipeline = Pipeline(config)

    # First analyze audio
    result = pipeline.analyze(video)

    # Extract and analyze frames
    click.echo("\nExtracting key frames around hits...")
    frame_paths = pipeline.extract_key_frames(video, result)
    click.echo(f"Extracted {len(frame_paths)} frames")

    # LLM analysis
    from .analyzers.frame_analyzer import analyze_frames_batch
    frames_with_ts = [(p, float(p.stem.split("_")[1].rstrip("s"))) for p in frame_paths]

    click.echo(f"Analyzing frames with {provider}...")
    analyses = analyze_frames_batch(frames_with_ts, provider, api_key, model)

    for a in analyses:
        click.echo(f"  {a.timestamp:.1f}s: {a.action} | {a.shot_type} | {a.player_count} players")


if __name__ == "__main__":
    main()
