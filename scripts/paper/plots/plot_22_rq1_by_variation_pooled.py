#!/usr/bin/env python3
"""Plot 22: RQ1 (Strategic-ness) by Variation using pooled per-variation fits.

Unlike plot_02 which loads individual (model, variation) fits and does ad-hoc
weighted averaging across models, this plot loads directly from per-variation
pooled fits where the Bayesian regression already handles the pooling.

RQ1 = (A + C - B) / (2C)

Where:
    A = Strategic model improvement over trivial baseline (intercepts-only)
    B = Non-strategic model improvement over trivial baseline
    C = Combined model improvement over trivial baseline

The trivial baseline has per-model/variation intercepts but no parameter effects,
so A/B/C measure improvement from the parameter effects only.

Output:
    - figures/plot_22_rq1_by_variation_pooled.pdf

Usage:
    uv run scripts/paper/plots/plot_22_rq1_by_variation_pooled.py
"""

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.paper_style import (
    FIG_WIDTH_DOUBLE,
    FONTSIZE_AXIS_LABEL,
    FONTSIZE_TICK,
    FONTSIZE_TITLE,
    SLUG_TO_VARIATION,
    get_scenario_color,
    get_variation_display_name,
    setup_style,
    sort_variations,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-variation")
OUTPUT_DIR = Path("paper_cache/figures")


def load_variation_data() -> list[dict]:
    """Load RQ1 distributions from per-variation pooled fits.

    The A, B, C distributions are already computed relative to the trivial
    baseline (intercepts-only), so they measure improvement from parameter
    effects only. No adjustment needed.

    Returns list of dicts with:
        - variation: variation name
        - scenario: scenario name
        - rq1_dist: RQ1 posterior distribution
        - p_c_positive: P(C > 0)
        - n_samples: number of samples used in fit
        - n_models: number of models pooled
    """
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")

    npz_files = sorted(POSTERIORS_DIR.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")

    results = []
    for npz_path in npz_files:
        variation = npz_path.stem
        json_path = POSTERIORS_DIR / f"{variation}.json"

        # Get scenario from mapping
        if variation not in SLUG_TO_VARIATION:
            raise ValueError(f"Unknown variation: {variation!r}")
        scenario, _ = SLUG_TO_VARIATION[variation]

        # Load posteriors (A, B, C already computed vs trivial baseline)
        data = np.load(npz_path)

        if "RQ1_distribution" not in data:
            raise ValueError(f"Missing RQ1_distribution in {npz_path}")
        if "C_distribution" not in data:
            raise ValueError(f"Missing C_distribution in {npz_path}")

        rq1_dist = data["RQ1_distribution"]
        C_dist = data["C_distribution"]

        # Handle NaN values (from C=0 cases)
        valid_mask = ~np.isnan(rq1_dist)
        rq1_valid = rq1_dist[valid_mask]
        C_valid = C_dist[valid_mask]

        if len(rq1_valid) == 0:
            raise ValueError(f"All RQ1 values are NaN for {variation}")

        # Clip RQ1 to [0, 1]
        rq1_clipped = np.clip(rq1_valid, 0, 1)

        # Compute P(C > 0)
        p_c_positive = float(np.mean(C_valid > 0))

        # Load summary for metadata
        if not json_path.exists():
            raise FileNotFoundError(f"Missing summary JSON: {json_path}")
        with open(json_path) as f:
            summary = json.load(f)
        n_samples = summary.get("n_samples", 0)
        n_models = summary.get("n_models", 0)

        results.append(
            {
                "variation": variation,
                "scenario": scenario,
                "rq1_dist": rq1_clipped,
                "p_c_positive": p_c_positive,
                "n_samples": n_samples,
                "n_models": n_models,
            }
        )

        logger.debug(
            f"{get_variation_display_name(scenario, variation)}: "
            f"RQ1={np.mean(rq1_clipped):.3f}"
        )

    return results


def compute_rq1_summary(variation_data: list[dict]) -> pd.DataFrame:
    """Compute RQ1 summary statistics for each variation.

    Returns DataFrame with: scenario, variation, rq1_mean, rq1_lower, rq1_upper, p_c_positive, n_samples, n_models
    """
    rows = []
    for d in variation_data:
        rq1_dist = d["rq1_dist"]
        rows.append(
            {
                "scenario": d["scenario"],
                "variation": d["variation"],
                "rq1_mean": float(np.mean(rq1_dist)),
                "rq1_lower": float(np.percentile(rq1_dist, 2.5)),
                "rq1_upper": float(np.percentile(rq1_dist, 97.5)),
                "p_c_positive": d["p_c_positive"],
                "n_samples": d["n_samples"],
                "n_models": d["n_models"],
            }
        )
    return pd.DataFrame(rows)


def plot_rq1_by_variation(var_df: pd.DataFrame, output_path: Path) -> None:
    """Create bar chart of RQ1 by variation."""
    setup_style()

    # Sort variations by canonical order
    variations = sort_variations(
        [(r["scenario"], r["variation"]) for _, r in var_df.iterrows()]
    )

    # Reorder dataframe
    var_df = var_df.set_index(["scenario", "variation"]).loc[variations].reset_index()

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 4.5))

    x = np.arange(len(variations))
    colors = [get_scenario_color(s) for s, v in variations]

    # Plot bars
    ax.bar(
        x,
        var_df["rq1_mean"],
        color=colors,
        alpha=0.7,
        edgecolor="black",
        linewidth=0.5,
    )

    # Error bars (95% ETI)
    yerr_lower = (var_df["rq1_mean"] - var_df["rq1_lower"]).clip(lower=0)
    yerr_upper = (var_df["rq1_upper"] - var_df["rq1_mean"]).clip(lower=0)
    ax.errorbar(
        x,
        var_df["rq1_mean"],
        yerr=[yerr_lower, yerr_upper],
        fmt="none",
        color="black",
        capsize=3,
        linewidth=1,
    )

    # Reference lines
    ax.axhline(0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.3)

    # Labels
    ax.set_ylabel("Strategic contribution", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(
        "Relative explanatory power of strategic vs. non-strategic factors",
        fontsize=FONTSIZE_TITLE,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [get_variation_display_name(s, v) for s, v in variations],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    # Y-axis limits and percentages
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    # Add P(C>0) or n_samples annotation below each bar
    for i, (_, row) in enumerate(var_df.iterrows()):
        p_c = row["p_c_positive"]
        if p_c < 0.999:
            ax.text(
                i,
                0.02,
                f"P={p_c:.2f}",
                ha="center",
                va="bottom",
                fontsize=5,
                color="red",
            )
        else:
            ax.text(
                i,
                0.02,
                f"n={row['n_samples'] // 1000}k",
                ha="center",
                va="bottom",
                fontsize=5,
                color="gray",
            )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved plot to {output_path}")


def main():
    """Generate Plot 22: RQ1 by Variation (Pooled Fits)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load per-variation data (A, B, C already computed vs trivial baseline)
    logger.info("Loading per-variation pooled posteriors...")
    variation_data = load_variation_data()
    logger.info(f"Loaded {len(variation_data)} variations")

    # Compute summary statistics
    var_df = compute_rq1_summary(variation_data)

    # Generate plot
    plot_rq1_by_variation(var_df, OUTPUT_DIR / "plot_22_rq1_by_variation_pooled.pdf")

    # Print summary table
    print("\n=== RQ1 by Variation (Pooled Fits) ===\n")
    print(
        f"{'Variation':<25} {'RQ1':<10} {'95% ETI':<20} {'P(C>0)':<10} {'N Samples':<12} {'N Models'}"
    )
    print("-" * 90)

    # Sort by RQ1 descending
    var_df_sorted = var_df.sort_values("rq1_mean", ascending=False)

    for _, row in var_df_sorted.iterrows():
        display_name = get_variation_display_name(row["scenario"], row["variation"])
        print(
            f"{display_name:<25} "
            f"{row['rq1_mean']:.3f}     "
            f"[{row['rq1_lower']:.3f}, {row['rq1_upper']:.3f}]    "
            f"{row['p_c_positive']:.3f}     "
            f"{row['n_samples']:>10,}  "
            f"{row['n_models']:>7}"
        )

    # Overall statistics
    print(f"\n{'=' * 90}")
    print(
        f"Variations with RQ1 > 0.5: {(var_df['rq1_mean'] > 0.5).sum()} / {len(var_df)}"
    )
    print(f"Mean RQ1 across variations: {var_df['rq1_mean'].mean():.3f}")
    print(f"Median RQ1: {var_df['rq1_mean'].median():.3f}")
    print(f"\nTotal samples: {var_df['n_samples'].sum():,}")

    print(f"\nOutput saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
