# Badminton Video Editor

Three simple tools for an AI agent to edit badminton videos.

## How It Works

The **agent** is the brain. These tools are its hands:

1. **`analyze_audio`** — Extract audio, detect hit sounds → returns timestamps & clusters
2. **`screenshot`** — Grab a frame at any time → agent views it to understand what's happening
3. **`cut_segments`** — Cut & concat segments → final edited video

### Agent Workflow
```
Agent calls analyze_audio("match.mp4")
  → gets: "67 clusters, cluster 3: 14.5s–19.8s, 5 hits (2 strong)"
  
Agent calls screenshot("match.mp4", 14.0)  # just before cluster
  → views frame: players in ready position → rally hasn't started yet

Agent calls screenshot("match.mp4", 20.5)  # just after cluster  
  → views frame: player picking up shuttle → rally is over

Agent decides: segment = {start: 13.5, end: 21.0}
  ... repeats for each cluster ...

Agent calls cut_segments("match.mp4", segments)
  → done: edited.mp4
```

## Install

```bash
pip install -e .
```

Requires: Python 3.11+, ffmpeg on PATH.

## Python API

```python
from badminton_editor import analyze_audio, screenshot, cut_segments

# 1. Understand the audio
result = analyze_audio("match.mp4")
print(result["summary"])
# Duration: 965.8s (16.1min), 351 hits, 67 rally-like clusters
#   Cluster 0: 0.0s–5.3s, 2 hits (1 strong)
#   Cluster 1: 14.6s–16.4s, 3 hits (1 strong)
#   ...

# 2. Look at key moments
screenshot("match.mp4", 14.0)   # agent views this image
screenshot("match.mp4", 20.0)   # agent views this image

# 3. Cut & concat
cut_segments("match.mp4", [
    {"start": 13.5, "end": 21.0},
    {"start": 29.0, "end": 36.0},
], "highlights.mp4")
```
