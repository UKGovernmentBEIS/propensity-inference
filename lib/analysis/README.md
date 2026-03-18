# Propensity Analysis Pipeline

Bayesian analysis for propensity scenarios. Fits hierarchical logistic regression models to evaluate how strategic vs non-strategic parameters affect misalignment rates.

## Quick Start

```bash
# Per-model pooled fit (one model × all variations)
uv run scripts/paper/run_pooled_fits.py fit --model "anthropic/claude-3-5-haiku-20241022"

# Per-variation pooled fit (all models × one variation)
uv run scripts/paper/run_pooled_fits.py fit --variation "alert"

# Per-quartile pooled fit (by capability)
uv run scripts/paper/run_pooled_fits.py fit --quartile q1

# Batch modes
uv run scripts/paper/run_pooled_fits.py fit --all-models      # 23 per-model fits
uv run scripts/paper/run_pooled_fits.py fit --all-variations  # 11 per-variation fits
uv run scripts/paper/run_pooled_fits.py fit --all-quartiles   # 4 per-quartile fits

# Generate plots
uv run scripts/paper/plots/plot_21_rq1_by_model_pooled.py
uv run scripts/paper/plots/plot_16_rq2_quartile_trends.py
```

## Configuration

Model configuration is handled programmatically in `lib/pooled_fitting/config.py`, which defines:
- **Parameter classification**: Which params are strategic vs non-strategic (from `lib/paper_style.py`)
- **Four Bayesian models**: strategic_only, non_strategic_only, combined, trivial (intercepts-only baseline)
- **Effect coding**: Symmetric coding with _DUMMY_ categories for proper variance estimation

## Interpreting Results

- **RQ1 > 0.5**: Strategic factors explain more variance
- **RQ1 < 0.5**: Non-strategic factors explain more variance
- **Odds ratio > 1**: Parameter increases misalignment probability
