"""LLM-powered frame analyzer for player and shot analysis.

Sends extracted frames to multimodal LLMs (OpenAI / Anthropic) for:
- Player position and pose recognition
- Court geometry analysis
- Shot type estimation
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FRAME_ANALYSIS_PROMPT = """Analyze this badminton video frame. Describe:
1. **Players**: How many players are visible? Where are they on the court? What is their body position/pose (ready stance, hitting, lunging, etc.)?
2. **Court**: Can you see court lines? Which part of the court is visible?
3. **Action**: What action appears to be happening (serving, rallying, resting, between points)?
4. **Shot type** (if a player is hitting): Does it look like a smash (arm high, aggressive), clear (high arc), drop (gentle), or net shot (at net)?

Respond in JSON format:
{
  "player_count": <int>,
  "players": [{"position": "<front/mid/back>", "side": "<near/far>", "pose": "<description>"}],
  "court_visible": <true/false>,
  "action": "<serving|rallying|resting|between_points|unclear>",
  "shot_type": "<smash|clear|drop|net|serve|none|unclear>",
  "confidence": <0.0-1.0>,
  "notes": "<any additional observations>"
}"""


@dataclass
class FrameAnalysis:
    """Result of LLM analysis of a single frame."""
    timestamp: float
    frame_path: Path
    player_count: int = 0
    action: str = "unclear"
    shot_type: str = "unclear"
    confidence: float = 0.0
    raw_response: str = ""
    players: list[dict[str, str]] = field(default_factory=list)
    notes: str = ""


def _encode_image(image_path: Path) -> str:
    """Base64-encode an image file."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_frame_openai(
    frame_path: Path,
    timestamp: float,
    api_key: str,
    model: str = "gpt-5.4",
) -> FrameAnalysis:
    """Analyze a frame using OpenAI's vision API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    client = OpenAI(api_key=api_key)
    b64_image = _encode_image(frame_path)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": FRAME_ANALYSIS_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}",
                        },
                    },
                ],
            }
        ],
        max_tokens=500,
    )

    raw = response.choices[0].message.content or ""
    return _parse_frame_response(raw, timestamp, frame_path)


def analyze_frame_anthropic(
    frame_path: Path,
    timestamp: float,
    api_key: str,
    model: str = "claude-opus-4-7-20260219",
) -> FrameAnalysis:
    """Analyze a frame using Anthropic's vision API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    b64_image = _encode_image(frame_path)

    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64_image,
                        },
                    },
                    {"type": "text", "text": FRAME_ANALYSIS_PROMPT},
                ],
            }
        ],
    )

    raw = response.content[0].text if response.content else ""
    return _parse_frame_response(raw, timestamp, frame_path)


def _parse_frame_response(
    raw: str, timestamp: float, frame_path: Path,
) -> FrameAnalysis:
    """Parse the LLM's JSON response into a FrameAnalysis."""
    import json

    analysis = FrameAnalysis(
        timestamp=timestamp,
        frame_path=frame_path,
        raw_response=raw,
    )

    try:
        # Try to extract JSON from the response
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data: dict[str, Any] = json.loads(raw[json_start:json_end])
            analysis.player_count = data.get("player_count", 0)
            analysis.action = data.get("action", "unclear")
            analysis.shot_type = data.get("shot_type", "unclear")
            analysis.confidence = data.get("confidence", 0.0)
            analysis.players = data.get("players", [])
            analysis.notes = data.get("notes", "")
    except (json.JSONDecodeError, KeyError):
        pass  # Keep defaults if parsing fails

    return analysis


def analyze_frames_batch(
    frame_paths: list[tuple[Path, float]],
    provider: str = "openai",
    api_key: str = "",
    model: str | None = None,
) -> list[FrameAnalysis]:
    """Analyze multiple frames. Each item is (path, timestamp)."""
    results = []
    for path, ts in frame_paths:
        if provider == "openai":
            result = analyze_frame_openai(
                path, ts, api_key,
                model=model or "gpt-5.4",
            )
        elif provider == "anthropic":
            result = analyze_frame_anthropic(
                path, ts, api_key,
                model=model or "claude-opus-4-7-20260219",
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
        results.append(result)

    return results
