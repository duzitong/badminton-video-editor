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

Audio clusters only capture the hitting sounds — they miss the **serve wind-up** before the first hit and the **shuttle landing** after the last hit. Each segment should include the full play: from the server raising the racket to someone walking to pick up the shuttle.

Use screenshots to find these real boundaries:

```python
from badminton_editor import screenshot
# Look BEFORE the cluster — find where the serve starts
path = screenshot("path/to/video.mp4", time_seconds=12.0, output_dir="output")
# Look AFTER the cluster — find where the shuttle has landed
path = screenshot("path/to/video.mp4", time_seconds=22.0, output_dir="output")
```

#### Finding the START (serve)

Work backwards from the first hit in the cluster. Screenshot at 3-5 seconds before:
- Is a player in serving stance (arm raised, shuttle held out)? → This is the start
- Are players still walking to position? → Go forward a bit
- Is a rally already in progress? → Go further back

Typical serve happens 2-4 seconds before the first detected hit.

#### Finding the END (shuttle lands / pickup)

**Important**: The last detected hit is the last *racket contact*, but the shuttle is still flying after that for 1-3 seconds. This flying time is NOT captured in the audio. If the last shot goes out of court or is a lob/clear, the shuttle may fly even longer before landing. You must account for this.

Start screenshotting at **4-6 seconds** after the last hit, not 2:

1. Screenshot at last_hit + 4s:
   - Players still watching the shuttle / pointing at lines → shuttle just landed, extend further
   - A player is walking toward the shuttle to pick it up → **good end point**
   - Players already chatting / resting / high-fiving → you can come back 1-2s

2. If players are still reacting at +4s, try +5s or +6s

Key visual cues for "the point is over":
- A player is **bending down or walking to pick up the shuttle** → ideal end frame
- Players are **turning away from the net** → point just ended
- Players are **looking at the sideline / baseline** (judging if in/out) → shuttle just landed, wait 1-2s more
- Players are **celebrating or disputing** → point ended, include this moment

Typical end is **4-6 seconds** after the last detected hit (1-3s of shuttle flight + 1-3s for the reaction and pickup).

#### Binary search for boundaries

If unsure, take 2-3 screenshots at different times and converge:
1. Screenshot at cluster_start - 5s → too early? too late?
2. Screenshot at cluster_start - 3s → adjust based on what you see
3. Same approach for the end: cluster_end + 5s, then ±1s to fine-tune

**Tips:**
- For long gaps between clusters (>10s), the players are likely resting — skip those
- Adjacent clusters with <5s gap are likely the same rally with a brief pause — merge them into one segment

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

Agent:
  1. analyze_audio("match.mp4") → 351 hits, 67 clusters

  2. For cluster 0 (first hit at 14.6s, last hit at 16.4s):
     - screenshot at 11.0s → players walking to position, too early
     - screenshot at 12.5s → server holding shuttle, raising racket → START = 12.5
     - screenshot at 20.5s → player still looking at shuttle (out of court shot)
     - screenshot at 22.0s → player walking to pick up shuttle → END = 22.0
     → segment: {start: 12.5, end: 22.0}

  3. Repeat for remaining clusters...

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
