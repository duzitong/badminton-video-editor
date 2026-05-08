# Badminton Video Editor

AI-powered badminton video editor that uses **audio analysis** to detect shuttle hit sounds and automatically segment rallies, build highlight reels, and apply effects.

## Why Audio-First?

Current multimodal LLMs (GPT-5.4, Claude Opus 4.7) **cannot**:
- Process video files directly
- Reliably detect the shuttlecock (too small, too fast)

But they **can**:
- Analyze extracted frames for player positions and actions
- Process audio for sound classification

This tool uses **librosa onset detection** as the primary signal for hit detection, optionally enhanced by LLM frame analysis for shot classification.

## Architecture

```
Input Video → ffmpeg → Audio Track → librosa onset detection → Hit timestamps
                    → Key Frames  → LLM analysis (optional)  → Shot classification
                                                              ↓
                    Hit timestamps + Shot types → Rally Segmentation → Highlight Scoring
                                                                    ↓
                    Video Editing ← Rally clips + Highlight reel + Slow-mo on smashes
```

## Installation

```bash
pip install -e .

# For LLM frame analysis (optional):
pip install -e ".[llm]"
```

**Requirements**: Python 3.11+, ffmpeg on PATH.

## Usage

### Analyze a video (detect rallies)

```bash
badminton-editor analyze video.mp4 -o output/

# Tune sensitivity:
badminton-editor analyze video.mp4 --delta 0.2 --gap 4.0 --min-hits 3
```

### Full edit (analyze + cut rallies + highlight reel)

```bash
badminton-editor edit video.mp4 -o output/ --top-n 10
```

### LLM-enhanced analysis (optional)

```bash
export LLM_API_KEY=sk-...
badminton-editor analyze-frames video.mp4 --provider openai
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--delta` | 0.3 | Onset detection sensitivity (lower = more sensitive) |
| `--debounce` | 0.3 | Min seconds between detected hits |
| `--gap` | 3.0 | Silence gap that marks rally boundary (seconds) |
| `--min-hits` | 2 | Minimum hits to count as a rally |
| `--top-n` | 5 | Number of rallies in highlight reel |

## Output

```
output/
├── audio.wav              # Extracted audio track
├── analysis.json          # Rally data with timestamps and scores
├── rallies/               # Individual rally clips
│   ├── rally_000.mp4
│   ├── rally_001.mp4
│   └── ...
└── highlight_reel.mp4     # Top-N rallies stitched together
```

## Python API

```python
from badminton_editor import Pipeline
from badminton_editor.pipeline import PipelineConfig

config = PipelineConfig(output_dir="output")
pipeline = Pipeline(config)

# Analyze only
result = pipeline.analyze("video.mp4")
print(result.summary())

# Analyze + edit
result = pipeline.edit("video.mp4")
```

## How It Works

1. **Audio extraction**: ffmpeg extracts mono WAV audio
2. **Hit detection**: librosa onset detection finds amplitude spikes (shuttle hits)
3. **Debouncing**: Merges events closer than 0.3s (same hit)
4. **Rally segmentation**: Groups hits by time gaps (>3s silence = new rally)
5. **Highlight scoring**: Ranks rallies by hit count, smash presence, and variety
6. **Video editing**: ffmpeg cuts rally clips and concatenates highlights

## Tested Results

On a 16-minute amateur doubles match:
- **351 hits** detected
- **67 rallies** segmented
- Top rally: 15 hits over 22.6s (score 0.92)
- Processing time: ~10 seconds for analysis
