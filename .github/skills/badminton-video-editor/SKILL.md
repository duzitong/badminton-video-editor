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

**Do NOT just add a fixed offset to the last hit.** You MUST screenshot and verify the end visually.

The last detected hit is the last *racket contact*. After that, the shuttle is still in the air — this flight time produces NO audio signal. The audio tells you nothing about the end — only your eyes can find it.

**Procedure — always do this, do not skip:**

Take 4 screenshots in one batch at last_hit +2s, +3s, +4s, +5s. View all of them:

```python
for offset in [2, 3, 4, 5]:
    screenshot(video, last_hit + offset, output_dir="output")
```

Then look at each frame and pick the one where a player is about to pick up or is picking up the shuttle:

- **+2s**: shuttle likely still in the air or just landing
- **+3s**: shuttle has landed, players reacting
- **+4s**: player walking to pick up shuttle ← often the right one
- **+5s**: player picking up or already picked up

Pick the frame where the shuttle has clearly landed and a player is moving to pick it up. Use that timestamp as your end. If even at +5s the players are still reacting (e.g., disputing a line call), take +6s and +7s.

**You must see the pickup moment.** Do not guess. Do not use a fixed offset.

Visual cues:
- Player **bending down or walking to pick up shuttle** → ✅ correct end
- Players **looking at sideline / baseline** (judging in/out) → shuttle just landed, go 1-2s further
- Players **celebrating or disputing** → point just ended, include this
- Players **turning away from the net** → point is over, this or +1s is your end
- Players **already back in position or resting** → you went too far, come back

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
- For "keep all rallies", process every cluster including short ones
- The video file is NOT read by this skill directly — only audio extraction and frame grabbing via ffmpeg
