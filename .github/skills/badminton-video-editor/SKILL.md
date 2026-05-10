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

Videos are stored in the `raw/` directory. Output for each video goes in `output/<video_name>/` (where `<video_name>` is the filename without extension). This keeps each video's analysis, screenshots, and edited result isolated.

### Step 0: Discover Videos

List available videos and determine output directories:

```python
import os
from pathlib import Path

raw_dir = Path("raw")
videos = sorted(raw_dir.glob("*.mp4"))  # also check *.MP4, *.mov if needed
for video in videos:
    output_dir = Path("output") / video.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"{video} → {output_dir}/")
```

If the user specified particular videos, filter to those. If no video was specified, **list the available videos and ask the user which one(s) to edit** using the `ask_user` tool:

```python
# Example: ask_user with choices built from discovered videos
choices = [v.name for v in videos]
# present choices to user, wait for selection
```

Present the filenames as choices (not full paths). Wait for the user's answer before proceeding.

For **multiple videos**, process each video independently through Steps 1–3 below. Steps 1 and 2 for different videos can be parallelised.

Follow these steps in order for each video:

### Step 1: Analyze Audio

Run the audio analyzer to get hit timestamps and clusters:

```python
from badminton_editor import analyze_audio
result = analyze_audio("raw/match.mp4", output_dir="output/match")
print(result["summary"])
```

This returns:
- `result["summary"]` — human-readable overview of all clusters
- `result["clusters"]` — list of `{start, end, hit_count, hits}` for each cluster
- `result["hits"]` — every individual hit `{time, strength, is_strong}`
- `result["duration"]` — total video duration in seconds

Read the summary first to understand the match structure. The clusters are rough rally boundaries based on audio alone.

### Step 2: Delegate Boundary Detection to Subagents

Audio clusters only capture the hitting sounds — they miss the **serve wind-up** before the first hit and the **shuttle landing** after the last hit. Each segment should include the full play: from the server raising the racket to someone walking to pick up the shuttle.

**Delegate this visual boundary detection to subagents** — one subagent per cluster (or small batch of clusters). This allows all clusters to be processed in parallel.

Spawn each subagent using the `task` tool with **`model: "claude-opus-4.7"`** — this model handles visual frame analysis reliably.

#### Subagent prompt template

For each cluster, spawn a subagent with this context:

```
You are detecting the real start and end of a badminton rally in a video.

Video: raw/<video_name>.mp4
Output dir: output/<video_name>
Cluster: first_hit=<T1>s, last_hit=<T2>s

Use the `screenshot` function to take frames and find the real boundaries:

  from badminton_editor import screenshot
  path = screenshot("raw/<video_name>.mp4", time_seconds=12.0, output_dir="output/<video_name>")

FINDING THE START:
Work backwards from first_hit. Screenshot at first_hit - 3s and first_hit - 5s.
- Is a player in serving stance (arm raised, shuttle held out)? → This is the start
- Are players still walking to position? → Go forward a bit
- Is a rally already in progress? → Go further back
Typical serve happens 2-4 seconds before the first detected hit.

IF THIS CLUSTER HAS ONLY 1 HIT:
The single hit may be a serve ace or a direct-point serve (the server wins the point
without the opponent touching the shuttle). Do NOT discard it automatically.
Screenshot at first_hit - 3s to check:
- Is a player in serving stance? → Likely a serve ace. Keep it and find start/end normally.
- No clear serve or player activity visible? → Likely a false positive (background noise). Discard: return null.

FINDING THE END:
The last detected hit is the last *racket contact*. After that, the shuttle is still in the air
— this flight time can be 1-4 seconds and produces NO audio signal. Cutting too early is the
most common mistake. Always err on the side of too late rather than too early.

**Default starting point: last_hit + 3s**. Take screenshots at last_hit +3s, +4s, +5s, +6s in one batch. View all of them:
- Shuttle still visible in air → too early, go further
- Shuttle just hit the ground, players reacting → include 1 more second past this
- Player bending down or walking to pick up shuttle → ✅ correct end
- Players looking at sideline/baseline (judging in/out) → go 1-2s further
- Players celebrating or disputing → point just ended, include this
- Players already back in position or resting → you went too far, come back

If at +6s the shuttle has not clearly landed, take +7s and +8s.
**Do NOT stop at +6s by default.** The shuttle flight after the last hit routinely
exceeds 3-4 seconds in real match play.

Do NOT use a fixed offset. You must confirm the shuttle has landed.

Return ONLY: {"start": <seconds>, "end": <seconds>} or null if discarded.
```

#### Coordinator responsibilities

After all subagents finish:

1. Collect non-null `{start, end}` results and sort them by `start`.
2. **Merge overlapping or touching segments** before cutting:
   - Two segments overlap or are adjacent (gap < 5s) if `seg[i+1].start - seg[i].end < 5`
   - Merge by keeping `min(start)` and `max(end)`
   - Repeat until no overlaps or short gaps remain
3. Pass the merged list to Step 3.

**Tips:**
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
output = cut_segments("raw/match.mp4", segments, output_path="output/match/edited.mp4")
```

This cuts each segment and concatenates them into one continuous video.

## Example Session

```
User: "Edit this badminton video and keep only the rallies: match.mp4"

Agent:
  0. Finds raw/match.mp4 → output dir: output/match/

  1. analyze_audio("raw/match.mp4", output_dir="output/match") → 351 hits, 67 clusters

  2. Spawns 67 subagents (claude-opus-4.7) in parallel, each with video=raw/match.mp4,
     output_dir=output/match, and their cluster's first_hit/last_hit.
     Collects results, discards nulls, sorts and merges overlapping segments.

  3. cut_segments("raw/match.mp4", segments, "output/match/edited.mp4")
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
- For "keep all rallies", process every cluster including 1-hit clusters (they may be serve aces) — subagents will discard true false positives
- The video file is NOT read by this skill directly — only audio extraction and frame grabbing via ffmpeg
