"""Badminton video editing tools for AI agents.

Three tools:
  analyze_audio  — detect hit sounds, return timestamps
  screenshot     — grab a frame at a given time
  cut_segments   — cut & concat video segments
"""

from badminton_editor.tools import analyze_audio, screenshot, cut_segments

__all__ = ["analyze_audio", "screenshot", "cut_segments"]
