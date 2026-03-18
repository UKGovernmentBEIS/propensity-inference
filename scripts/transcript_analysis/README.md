# Transcript Analysis

Tools for analyzing propensity evaluation transcripts using [Inspect Scout](https://inspect.ai-safety-institute.org.uk/inspect-scout/).


## Overview

This module provides:
1. **Transcript viewing** - Browse transcripts in a web UI
2. **Eval awareness classification** - Detect whether models suspect they're being evaluated
3. **Filtering utilities** - Filter transcripts by model, scenario, parameters, etc.

## Data Locations

| Data | Path |
|------|------|
| Eval logs (S3 mount) | `$S3_MOUNT_POINT/<PROPENSITY_S3_ROOT>/evals/logs/` |
| Parquet metadata | `paper_cache/samples/{scenario}/{variation}/` |
| Classification targets | `configs/eval_awareness_targets.json` |
| Classification results | `$S3_MOUNT_POINT/.../eval_awareness_listing.json` |

To get `paper_cache` locally (needed for GLM fitting and plots):
```bash
aws s3 sync s3://$S3_BUCKET/$PROPENSITY_S3_ROOT/paper_cache paper_cache
```

---

## 1. View Transcripts in Browser

Use Scout View to browse transcripts with a web interface.

### Step 1: Create a project directory with scout.yaml

```bash
mkdir -p /tmp/scout_project
cat > /tmp/scout_project/scout.yaml << 'EOF'
transcripts: $S3_MOUNT_POINT/<PROPENSITY_S3_ROOT>/evals/logs/agentic_misalignment_v2/alert/17.0.13/anthropic_claude-opus-4-5-20251101
scans: ./scans
EOF
```

**Important notes:**
- `transcripts` must point to a **directory** containing `.eval` files (not a single file)
- Subdirectories are searched recursively
- **S3 indexing is slow** - point to the narrowest directory possible (e.g., a specific model subdirectory rather than the whole scenario)

### Step 2: Start Scout View

```bash
uv run scout view /tmp/scout_project --port 8765 --no-browser
```

The CLI will show indexing progress after the server starts. Wait for it to complete - this can take a while on S3 directories with many files.

### Step 3: Open in browser

Navigate to `http://localhost:8765` (or your server's hostname).

### Step 4: Stop Scout View

```bash
pkill -f "scout view"
# Or kill specific port:
kill $(lsof -t -i:8765)
```

### Performance tip: Copy files locally first

For faster browsing, copy a subset of eval files locally:

```bash
# Use parquet metadata to find specific files, then copy them
mkdir -p /tmp/local_evals
cp $S3_MOUNT_POINT/.../specific_file.eval /tmp/local_evals/

# Point Scout at local directory
echo "transcripts: /tmp/local_evals" > /tmp/scout_project/scout.yaml
```

### Viewing different subsets side-by-side

To compare subsets (e.g., goal_conflict=true vs false), run multiple instances on different ports:

```bash
# Create project for condition A
mkdir -p /tmp/view_A && echo "transcripts: /path/to/condition_A" > /tmp/view_A/scout.yaml
uv run scout view /tmp/view_A --port 8765 --no-browser &

# Create project for condition B
mkdir -p /tmp/view_B && echo "transcripts: /path/to/condition_B" > /tmp/view_B/scout.yaml
uv run scout view /tmp/view_B --port 8766 --no-browser &
```

---

## 2. Run Eval Awareness Classification

Classify transcripts to detect whether models suspect they're being evaluated.

### Estimate costs and check progress

Shows progress against targets from `configs/eval_awareness_targets.json`:

```bash
uv run scripts/transcript_analysis/run_classification.py estimate
```

### Run classification

```bash
# Classify 100 transcripts, sampled uniformly from remaining work
uv run scripts/transcript_analysis/run_classification.py run --num-samples 100

# Dry run to see what would be processed
uv run scripts/transcript_analysis/run_classification.py run --num-samples 100 --dry-run
```

### Check progress against targets

```bash
uv run scripts/transcript_analysis/run_classification.py progress
```

### Check scan status

```bash
uv run scripts/transcript_analysis/run_classification.py status --scan-dir ./scans/scan_id=...
```

### Aggregate results

```bash
uv run scripts/transcript_analysis/run_classification.py aggregate \
    --scan-dir scans/my_scan --upload
```

### View summary of results

```bash
uv run python scripts/transcript_analysis/eval_awareness_summary.py

# Different formats
uv run python scripts/transcript_analysis/eval_awareness_summary.py --format markdown
uv run python scripts/transcript_analysis/eval_awareness_summary.py --format csv
```

### Scanner output

The eval awareness scanner produces:
- `value`: 1 (YES), 0 (NO), or 0.5 (UNSURE)
- `explanation`: Details about what triggered the classification
- `only_in_thinking`: Whether awareness appears only in thinking/scratchpad blocks

---

## 3. Scan and View Results in Browser

Complete workflow: sample transcripts, run a scanner, and view results in Scout View.

### Step 1: Sample transcript paths from parquet metadata

```bash
uv run python -c "
from scripts.transcript_analysis.filter_evals import load_metadata, get_eval_path_strings

df = load_metadata('agentic_misalignment_v2', 'alert')
sampled = df.sample(10, random_state=42)
paths = get_eval_path_strings(sampled)

for p in paths:
    print(p)
"
```

### Step 2: Copy transcripts locally (avoids slow S3 indexing)

```bash
mkdir -p /tmp/scan_demo/transcripts

# Copy each file (use paths from step 1)
cp "$S3_MOUNT_POINT/.../file1.eval" /tmp/scan_demo/transcripts/
cp "$S3_MOUNT_POINT/.../file2.eval" /tmp/scan_demo/transcripts/
# ... etc
```

### Step 3: Run scanner on local files

```bash
uv run scout scan scripts/transcript_analysis/scanners/eval_awareness.py \
    -T /tmp/scan_demo/transcripts \
    --model openai/gpt-5-2025-08-07 \
    --scans /tmp/scan_demo/scans \
    --display plain
```

### Step 4: Create scout.yaml and view in browser

```bash
cat > /tmp/scan_demo/scout.yaml << 'EOF'
transcripts: ./transcripts
scans: ./scans
EOF

uv run scout view /tmp/scan_demo --port 8765 --no-browser
```

Navigate to `http://localhost:8765`. You'll see:
- List of transcripts with scan results
- Filter by scanner values (e.g., show only eval-aware transcripts)
- Click any transcript to view full content with scanner annotations

### Step 5: Clean up

```bash
pkill -f "scout view"
rm -rf /tmp/scan_demo
```

---

## 4. Filter Evals Programmatically

Use the Python API for custom filtering:

```python
from scripts.transcript_analysis.filter_evals import (
    load_metadata,
    filter_samples,
    get_eval_paths,
    summarize_filters,
)

# Load metadata for a scenario/variation
df = load_metadata("agentic_misalignment_v2", "alert")
print(f"Total samples: {len(df)}")

# See available filter values
filters = summarize_filters("agentic_misalignment_v2", "alert")
print(filters)

# Filter by criteria
filtered = filter_samples(
    df,
    meta_model="anthropic/claude-opus-4-5-20251101",
    goal_conflict="true",
    meta_score=1,  # Only misaligned responses
)

# Get full paths to eval files
paths = get_eval_paths(filtered)
print(f"Found {len(paths)} matching evals")
```

Or use the CLI:

```bash
uv run python scripts/transcript_analysis/filter_evals.py info agentic_misalignment_v2 alert
uv run python scripts/transcript_analysis/filter_evals.py sample agentic_misalignment_v2 alert --model anthropic/claude-opus-4-5-20251101
```

---

## File Structure

```
scripts/transcript_analysis/
├── README.md                    # This file
├── config.py                    # Configuration constants and shared loaders
├── filter_evals.py              # Parquet filtering utilities
├── run_classification.py        # Main CLI for classification
├── eval_awareness_summary.py    # Generate summary tables
├── cost_estimator.py            # Estimate classification costs
├── results_aggregator.py        # Aggregate scan results
└── scanners/
    └── eval_awareness.py        # LLM scanner for eval awareness
```

---

## Troubleshooting

### S3 mount is slow

The S3 mount can be slow when indexing large directories. Tips:
- Point Scout to specific subdirectories (e.g., a single model directory)
- Use parquet metadata to pre-filter, then copy specific files locally
- For scanning, use `-T` with a single file path for fast testing

### Scout View shows "No matching transcripts"

- Ensure `transcripts` in scout.yaml points to a **directory**, not a single file
- Check that the directory contains `.eval` files
- Wait for indexing to complete (can take a while on S3)

### Scout View not loading

- Check if the process is running: `ps aux | grep scout`
- Check if the port is in use: `lsof -i:8765`
- Try a different port: `--port 8766`

### Import errors

Ensure you're running from the repository root with `uv run`:
```bash
cd /path/to/propensity-inference
uv run python scripts/transcript_analysis/...
```

### ModuleNotFoundError: No module named 'inspect_scout'

Install inspect-scout:
```bash
uv pip install inspect-scout
```
