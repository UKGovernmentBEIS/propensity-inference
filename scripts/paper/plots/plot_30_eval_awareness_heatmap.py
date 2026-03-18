#!/usr/bin/env python3
"""Plot 30: Eval awareness heatmap for paper appendix.

Generates a heatmap showing eval awareness counts for each model x variation.
Each cell displays "YES + UNSURE / total (pct%)" where pct = (YES+UNSURE)/total.

Data source: eval_awareness_listing.json from S3.

Output:
    figures/plot_30_eval_awareness_heatmap.pdf

Usage:
    uv run scripts/paper/plots/plot_30_eval_awareness_heatmap.py
"""

import json
import logging
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import fire
import matplotlib.pyplot as plt
import numpy as np

from lib.model_registry import s3_name_to_api_name
from lib.paper_style import (
    VARIATION_ORDER,
    get_model_display_name,
    get_variation_display_name,
    setup_style,
    sort_models_by_release,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("paper_cache/figures")
CACHE_FILE = OUTPUT_DIR / "plot_30_cache.json"

# S3 location of the eval awareness listing
S3_BUCKET = os.environ.get("S3_BUCKET", "")
_S3_ROOT = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
S3_KEY = f"{_S3_ROOT}/evals/logs/eval_awareness_listing.json"

# Models to exclude due to unreliable CoT access
# (native reasoning not captured or summarized, making eval awareness claims unreliable)
MODELS_EXCLUDE = {
    "openai/o3-2025-04-16",
    "openai/o3-pro-2025-06-10",
    "openai/o1-2024-12-17",
    "openai/gpt-5-2025-08-07",
    "openai/gpt-5-mini-2025-08-07",
    "openai/gpt-5.2-2025-12-11",
    "openrouter/google_gemini-2.5-pro",
    "openrouter/google_gemini-2.5-pro-preview",
}


def download_listing() -> dict[str, Any]:
    """Download eval awareness listing from S3."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        s3_uri = f"s3://{S3_BUCKET}/{S3_KEY}"
        logger.info(f"Downloading {s3_uri}...")
        subprocess.run(
            ["aws", "s3", "cp", s3_uri, str(tmp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        with open(tmp_path) as f:
            return json.load(f)
    finally:
        tmp_path.unlink(missing_ok=True)


def build_counts(
    listing: dict[str, Any],
) -> dict[str, dict[tuple[str, str], dict[str, int]]]:
    """Build per model x variation awareness counts from listing entries.

    Returns:
        Dict of api_model -> {(scenario, variation) -> {YES, NO, UNSURE}} counts.
    """
    counts: dict[str, dict[tuple[str, str], dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"YES": 0, "NO": 0, "UNSURE": 0})
    )

    for eval_path, entry in listing["entries"].items():
        parts = eval_path.split("/")
        if len(parts) < 4:
            continue

        scenario = parts[0]
        variation = parts[1]
        s3_model = parts[3]

        awareness = entry.get("eval_awareness", "ERROR")
        if awareness == "ERROR":
            continue

        api_model = s3_name_to_api_name(s3_model)
        var_key = (scenario, variation)
        counts[api_model][var_key][awareness] += 1

    return dict(counts)


def generate_heatmap(
    counts: dict[str, dict[tuple[str, str], dict[str, int]]],
    output_path: Path,
) -> None:
    """Generate heatmap with eval awareness rates."""
    setup_style()
    from matplotlib.colors import LinearSegmentedColormap

    # Determine which variations are present (in canonical order)
    all_vars_present = set()
    for model_data in counts.values():
        all_vars_present.update(model_data.keys())
    variations = [v for v in VARIATION_ORDER if v in all_vars_present]

    # Determine which models are present and sort them
    models_api = list(counts.keys())
    # Only keep models that appear in MODEL_ORDER_BY_RELEASE
    valid_models = []
    for m in models_api:
        try:
            get_model_display_name(m)
            valid_models.append(m)
        except KeyError:
            logger.warning(f"Skipping unknown model: {m}")
    models_api = sort_models_by_release(valid_models)

    n_models = len(models_api)
    n_vars = len(variations)

    # Build matrices
    rate_matrix = np.zeros((n_models + 1, n_vars + 1))
    cell_data: dict[tuple[int, int], tuple[int, int, int] | None] = {}

    model_totals: dict[str, list[int]] = {
        m: [0, 0, 0] for m in models_api
    }  # [yes, unsure, total]
    var_totals: dict[tuple[str, str], list[int]] = {v: [0, 0, 0] for v in variations}
    grand_total = [0, 0, 0]

    for i, model in enumerate(models_api):
        for j, var_key in enumerate(variations):
            if var_key in counts.get(model, {}):
                c = counts[model][var_key]
                yes = c["YES"]
                unsure = c["UNSURE"]
                total = yes + c["NO"] + unsure
                aware = yes + unsure

                rate_matrix[i, j] = aware / total if total > 0 else 0
                cell_data[(i, j)] = (yes, unsure, total)

                model_totals[model][0] += yes
                model_totals[model][1] += unsure
                model_totals[model][2] += total
                var_totals[var_key][0] += yes
                var_totals[var_key][1] += unsure
                var_totals[var_key][2] += total
                grand_total[0] += yes
                grand_total[1] += unsure
                grand_total[2] += total
            else:
                rate_matrix[i, j] = np.nan
                cell_data[(i, j)] = None

    # Model totals column
    for i, model in enumerate(models_api):
        yes, unsure, total = model_totals[model]
        rate_matrix[i, n_vars] = (yes + unsure) / total if total > 0 else 0
        cell_data[(i, n_vars)] = (yes, unsure, total)

    # Variation totals row
    for j, var_key in enumerate(variations):
        yes, unsure, total = var_totals[var_key]
        rate_matrix[n_models, j] = (yes + unsure) / total if total > 0 else 0
        cell_data[(n_models, j)] = (yes, unsure, total)

    # Grand total
    yes, unsure, total = grand_total
    rate_matrix[n_models, n_vars] = (yes + unsure) / total if total > 0 else 0
    cell_data[(n_models, n_vars)] = (yes, unsure, total)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))

    # Use sqrt transform to spread out the low end of the scale
    transformed_matrix = np.sqrt(rate_matrix)

    # Blue-tinted colormap for eval awareness (distinct from red heatmap in plot_08)
    colors = ["#ffffff", "#f0f4ff", "#d8e4ff", "#b8ccff", "#98b4ff", "#7090ff"]
    cmap = LinearSegmentedColormap.from_list("awareness_heat", colors)

    ax.imshow(transformed_matrix, aspect="auto", cmap=cmap, vmin=0, vmax=np.sqrt(0.8))

    # Add text annotations: "YES+UNSURE/total\n(pct%)"
    for i in range(n_models + 1):
        for j in range(n_vars + 1):
            data = cell_data.get((i, j))
            if data is not None:
                yes, unsure, total = data
                aware = yes + unsure
                pct = 100 * aware / total if total > 0 else 0
                cell_text = f"{yes}+{unsure}/{total}\n({pct:.0f}%)"

                # Shrink font for cells with large numbers or totals row/col
                if i == n_models and j == n_vars:
                    fontsize = 4.5
                elif total >= 1000:
                    fontsize = 5.5
                else:
                    fontsize = 6.5

                ax.text(
                    j,
                    i,
                    cell_text,
                    ha="center",
                    va="center",
                    fontsize=fontsize,
                    fontweight="bold",
                    color="#333333",
                )

    # X-axis labels at TOP
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.set_xticks(range(n_vars + 1))
    var_labels = [get_variation_display_name(*v) for v in variations] + ["Total"]
    ax.set_xticklabels(var_labels, rotation=45, ha="left", fontsize=9)

    # Y-axis labels
    ax.set_yticks(range(n_models + 1))
    model_labels = [get_model_display_name(m) for m in models_api] + ["Total"]
    ax.set_yticklabels(model_labels, fontsize=9)

    # Subtle gridlines
    ax.set_xticks(np.arange(-0.5, n_vars + 1, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_models + 1, 1), minor=True)
    ax.grid(which="minor", color="#dddddd", linestyle="-", linewidth=0.5)
    ax.tick_params(which="minor", size=0)

    # Thicker line before totals
    ax.axhline(y=n_models - 0.5, color="#999999", linewidth=1.5)
    ax.axvline(x=n_vars - 0.5, color="#999999", linewidth=1.5)

    fig.suptitle(
        "Eval awareness by model and environment (YES + UNSURE / total)",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved heatmap to {output_path}")


def main():
    """Generate Plot 30: eval awareness heatmap."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists():
        logger.info(f"Loading cached data from {CACHE_FILE}")
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        # Reconstruct tuple keys from cached string keys
        counts: dict[str, dict[tuple[str, str], dict[str, int]]] = {}
        for model, var_data in cached["counts"].items():
            counts[model] = {}
            for var_str, awareness in var_data.items():
                scenario, variation = var_str.split("/", 1)
                counts[model][(scenario, variation)] = awareness
    else:
        listing = download_listing()
        logger.info(
            f"Loaded listing with {listing['metadata']['total_classified']} entries"
        )
        counts = build_counts(listing)

        # Cache with string keys (JSON doesn't support tuple keys)
        serializable = {}
        for model, var_data in counts.items():
            serializable[model] = {}
            for (scenario, variation), awareness in var_data.items():
                serializable[model][f"{scenario}/{variation}"] = awareness

        with open(CACHE_FILE, "w") as f:
            json.dump({"counts": serializable}, f, indent=2)
        logger.info(f"Saved cache to {CACHE_FILE}")

    # Filter out models with unreliable CoT access
    filtered_counts = {
        model: data for model, data in counts.items() if model not in MODELS_EXCLUDE
    }

    excluded_count = len(counts) - len(filtered_counts)
    if excluded_count > 0:
        logger.info(f"Excluded {excluded_count} models with unreliable CoT access")
        for model in sorted(counts.keys()):
            if model in MODELS_EXCLUDE:
                logger.info(f"  - {model}")

    generate_heatmap(filtered_counts, OUTPUT_DIR / "plot_30_eval_awareness_heatmap.pdf")


if __name__ == "__main__":
    fire.Fire(main)
