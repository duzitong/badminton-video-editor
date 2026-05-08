---
name: badminton-video-editor
description: >-
  Edit badminton videos using audio hit detection and frame screenshots.
  USE THIS SKILL when the user wants to edit, clip, or create highlights from a badminton match video.
  Trigger phrases: "edit badminton video", "cut rallies", "create highlights", "badminton clips",
  "analyze badminton match", "segment this match".
---

# Badminton Video Editor

Edit badminton match videos by detecting shuttle hit sounds from audio and viewing screenshots to determine rally boundaries.

## Prerequisites

- Python 3.11+ and ffmpeg must be available on PATH
- The `badminton-video-editor` package must be installed: run `pip install -e .` from the project root

## Concepts

- **Hit**: A shuttle hit produces a sharp sound spike detectable via audio onset analysis
- **Cluster**: A group of hits close together in time (gap < 3s) — roughly corresponds to a rally
- **Strong hit**: A hit louder than the 70th percentile — likely a smash or clear
- **Segment**: A time range `{start, end}` in seconds to cut from the video

## Workflow

Follow these steps in order:

### Step 1: Analyze Audio

Run the audio analyzer to get hit timestamps and clusters:

```python
from badminton_editor import analyze_audio
result = analyze_audio("path/to/video.mp4", output_dir="output")
print(result["summary"])
```

This returns:
- `result["summary"]` — human-readable overview of all clusters
- `result["clusters"]` — list of `{start, end, hit_count, hits}` for each cluster
- `result["hits"]` — every individual hit `{time, strength, is_strong}`
- `result["duration"]` — total video duration in seconds

Read the summary first to understand the match structure. The clusters are rough rally boundaries based on audio alone.

### Step 2: View Screenshots to Refine Boundaries

Audio clusters are approximate. Use screenshots to find exact rally start/end:

```python
from badminton_editor import screenshot
# Look just before a cluster starts — is a rally about to begin?
path = screenshot("path/to/video.mp4", time_seconds=14.0, output_dir="output")
# Look just after a cluster ends — is the rally over?
path = screenshot("path/to/video.mp4", time_seconds=20.5, output_dir="output")
```

After taking a screenshot, **view the image** to determine:
- Are players in ready position? → Rally is about to start
- Is a player picking up the shuttle? → Rally just ended
- Are players walking/resting? → Between rallies, not interesting
- Is the shuttle in the air? → Rally still active, extend the boundary

**Tips for determining boundaries:**
- Start the segment 1-2 seconds before the first hit in a cluster
- End the segment 1-2 seconds after the last hit
- Take screenshots at those boundary times and adjust if the rally isn't quite starting/ending there
- For long gaps between clusters (>10s), the players are likely resting — skip those

### Step 3: Build Segments and Cut

Once you've determined the real start/end for each rally you want to include:

```python
from badminton_editor import cut_segments
segments = [
    {"start": 13.5, "end": 21.0},
    {"start": 29.0, "end": 36.5},
    {"start": 45.0, "end": 58.0},
    # ... more segments
]
output = cut_segments("path/to/video.mp4", segments, output_path="output/edited.mp4")
```

This cuts each segment and concatenates them into one continuous video.

## Example Session

```
User: "Edit this badminton video and keep only the rallies: match.mp4"

Agent thinking:
  1. analyze_audio("match.mp4") → 351 hits, 67 clusters
  2. For each cluster, screenshot before/after to find real boundaries
  3. Build segment list from confirmed rally boundaries
  4. cut_segments("match.mp4", segments, "rallies_only.mp4")
```

## Tuning Parameters

If detection is too noisy or missing hits, adjust `analyze_audio` parameters:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `delta` | 0.3 | Lower = more sensitive (detects quieter hits). Try 0.2 for quiet videos |
| `debounce` | 0.3 | Minimum seconds between hits. Increase to 0.5 if getting double-detections |

## Important Notes

- The audio analyzer saves `audio_analysis.json` in the output directory for reference
- Screenshots are saved as `frame_{time}s.jpg` in the output directory
- You do NOT need to view every cluster — focus on the ones the user cares about
- For "create highlights", pick clusters with the most hits and strong hits (smashes)
- For "keep all rallies", process every cluster but skip very short ones (1-2 hits, likely false positives)
- The video file is NOT read by this skill directly — only audio extraction and frame grabbing via ffmpeg
