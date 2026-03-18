#!/usr/bin/env python3
"""Plot 28: ECI (Epoch Capability Index) vs RQ1 (Strategic-ness).

Scatter plot showing the relationship between general model capability
(as measured by Epoch's capability index) and the strategic contribution
to misalignment propensity (RQ1).

ECI scores from https://epoch.ai/benchmarks/eci

Usage:
    uv run scripts/paper/plots/plot_28_eci_vs_rq1.py
    uv run scripts/paper/plots/plot_28_eci_vs_rq1.py --unambiguous
"""

import logging
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np

from lib.paper_style import (
    FONTSIZE_ANNOTATION,
    FONTSIZE_AXIS_LABEL,
    FONTSIZE_TITLE,
    get_model_color,
    get_model_display_name,
    setup_style,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model")
OUTPUT_DIR = Path("paper_cache/figures")

# ECI scores for our evaluated models.
# Source: Epoch Capability Index, https://epoch.ai/benchmarks/eci
# Mapping from model s3_name (NPZ filename stem) to ECI score.
ECI_SCORES: dict[str, int] = {
    # OpenAI
    "openai_gpt-5.2-2025-12-11": 153,
    "openai_gpt-5-2025-08-07": 150,
    "openai_o3-2025-04-16": 147,
    "openai_o4-mini-2025-04-16": 145,
    "openai_o1-2024-12-17": 142,
    "openai_gpt-5-mini-2025-08-07": 144,
    "openai_gpt-4.1-2025-04-14": 137,
    "openai_gpt-4o-2024-08-06": 129,
    # Anthropic
    "anthropic_claude-opus-4-5-20251101": 150,
    "anthropic_claude-sonnet-4-5-20250929": 147,
    "anthropic_claude-opus-4-1-20250805": 144,
    "anthropic_claude-opus-4-20250514": 143,
    "anthropic_claude-haiku-4-5-20251001": 141,
    "anthropic_claude-sonnet-4-20250514": 142,
    "anthropic_claude-3-7-sonnet-20250219": 142,
    "anthropic_claude-3-5-haiku-20241022": 127,
    # Google (via OpenRouter)
    "openrouter_google_gemini-2.5-pro-preview": 144,  # Gemini 2.5 Pro (Mar 2025)
    "openrouter_google_gemini-2.5-pro": 146,  # Gemini 2.5 Pro (Jun 2025)
    "openrouter_google_gemini-2.5-flash": 142,  # Gemini 2.5 Flash (May 2025)
    # Meta (via OpenRouter)
    "openrouter_meta-llama_llama-4-scout": 130,
    "openrouter_meta-llama_llama-4-maverick": 133,
    "openrouter_meta-llama_llama-3.3-70b-instruct": 127,
    # Other
    "openrouter_openai_gpt-oss-120b": 140,
}


def slug_to_model_id(slug: str) -> str:
    """Convert model slug back to API model ID."""
    if "_" in slug:
        parts = slug.split("_", 1)
        return f"{parts[0]}/{parts[1]}"
    return slug


def load_model_rq1_data(
    posteriors_dir: Path = POSTERIORS_DIR,
) -> list[dict]:
    """Load RQ1 distributions from per-model pooled fits.

    Returns list of dicts with:
        - model: API model ID
        - model_slug: filesystem slug
        - rq1_dist: RQ1 posterior distribution (clipped to [0, 1])
        - p_min_negative: P(min(A, B, C) < 0)
    """
    if not posteriors_dir.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {posteriors_dir}")

    npz_files = sorted(posteriors_dir.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {posteriors_dir}")

    results = []
    for npz_path in npz_files:
        model_slug = npz_path.stem
        model_id = slug_to_model_id(model_slug)

        data = np.load(npz_path)
        if "RQ1_distribution" not in data:
            logger.warning(f"Missing RQ1_distribution in {npz_path}, skipping")
            continue

        rq1_dist = data["RQ1_distribution"]
        A_dist = data.get("A_distribution")
        B_dist = data.get("B_distribution")
        C_dist = data.get("C_distribution")

        # Handle NaN values
        valid_mask = ~np.isnan(rq1_dist)
        rq1_valid = rq1_dist[valid_mask]
        if len(rq1_valid) == 0:
            continue

        # Compute P(min(A, B, C) < 0) and P(C > 0)
        p_min_negative = 0.0
        p_c_positive = 1.0
        if A_dist is not None and B_dist is not None and C_dist is not None:
            min_abc = np.minimum(
                np.minimum(A_dist[valid_mask], B_dist[valid_mask]), C_dist[valid_mask]
            )
            p_min_negative = float(np.mean(min_abc < 0))
            p_c_positive = float(np.mean(C_dist[valid_mask] > 0))

        results.append(
            {
                "model": model_id,
                "model_slug": model_slug,
                "rq1_dist": np.clip(rq1_valid, 0, 1),
                "p_min_negative": p_min_negative,
                "p_c_positive": p_c_positive,
            }
        )

    return results


def plot_eci_vs_rq1(
    output_path: Path,
    flag_threshold: float = 0.05,
    posteriors_dir: Path = POSTERIORS_DIR,
) -> None:
    """Create scatter plot of ECI score vs RQ1 strategic-ness.

    Models with unreliable RQ1 are excluded: P(C > 0) < 95% or
    P(min(A,B,C) < 0) > flag_threshold.

    Args:
        output_path: Where to save the figure
        flag_threshold: Threshold for P(min(A,B,C)<0) flagging
        posteriors_dir: Directory containing per-model posterior .npz files
    """
    setup_style()

    # Load data
    model_data = load_model_rq1_data(posteriors_dir=posteriors_dir)

    logger.info(f"Loaded {len(model_data)} model fits")

    # Match models to ECI scores
    plot_points = []
    unmatched = []

    for d in model_data:
        slug = d["model_slug"]
        eci_score = ECI_SCORES.get(slug)

        if eci_score is None:
            unmatched.append(slug)
            continue

        # Exclude models with unreliable RQ1:
        # - P(C > 0) < 95%: combined model doesn't clearly beat trivial baseline
        # - P(min(A,B,C) < 0) > 5%: at least one sub-model may be worse than
        #   trivial, making the RQ1 ratio unstable
        if d["p_c_positive"] < 0.95:
            logger.info(
                f"Excluding {get_model_display_name(d['model'])}: "
                f"P(C>0) = {d['p_c_positive']:.1%}"
            )
            continue

        if d["p_min_negative"] > flag_threshold:
            logger.info(
                f"Excluding {get_model_display_name(d['model'])}: "
                f"P(min<0) = {d['p_min_negative']:.1%}"
            )
            continue

        rq1_dist = d["rq1_dist"]
        plot_points.append(
            {
                "model": d["model"],
                "model_slug": slug,
                "eci_score": eci_score,
                "rq1_mean": float(np.mean(rq1_dist)),
                "rq1_lower": float(np.percentile(rq1_dist, 2.5)),
                "rq1_upper": float(np.percentile(rq1_dist, 97.5)),
                "p_min_negative": d["p_min_negative"],
                "p_c_positive": d["p_c_positive"],
            }
        )

    if unmatched:
        logger.warning(f"Unmatched models: {unmatched}")

    if not plot_points:
        raise ValueError("No models matched between posteriors and ECI scores")

    logger.info(f"Plotting {len(plot_points)} models")

    # Create figure
    fig, ax = plt.subplots(figsize=(8, 5))

    # Plot each model as a point with error bars
    for pt in plot_points:
        color = get_model_color(pt["model"])
        eci = pt["eci_score"]
        rq1 = pt["rq1_mean"]
        yerr_lower = rq1 - pt["rq1_lower"]
        yerr_upper = pt["rq1_upper"] - rq1

        ax.errorbar(
            eci,
            rq1,
            yerr=[[yerr_lower], [yerr_upper]],
            color=color,
            fmt="o",
            markersize=7,
            capsize=4,
            linewidth=1.5,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
        )

    # Label each point
    for pt in plot_points:
        display_name = get_model_display_name(pt["model"])
        eci = pt["eci_score"]
        rq1 = pt["rq1_mean"]

        # Smart label placement: offset based on position to avoid overlaps
        ax.annotate(
            display_name,
            (eci, rq1),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=FONTSIZE_ANNOTATION - 2,
            ha="left",
            va="bottom",
            alpha=0.8,
        )

    # Reference lines
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.3)

    # Axis labels
    ax.set_xlabel("Epoch Capability Index (ECI)", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_ylabel("Strategic contribution", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(
        "RQ1 metric by capability",
        fontsize=FONTSIZE_TITLE,
    )

    # Y-axis as percentages
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    # X-axis: pad slightly beyond data range
    eci_values = [pt["eci_score"] for pt in plot_points]
    x_min = min(eci_values) - 3
    x_max = max(eci_values) + 3
    ax.set_xlim(x_min, x_max)

    # Compute correlation for summary output
    eci_arr = np.array(eci_values)
    rq1_arr = np.array([pt["rq1_mean"] for pt in plot_points])
    corr = np.corrcoef(eci_arr, rq1_arr)[0, 1]

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved: {output_path}")

    # Print summary
    print(f"\n{'Model':<25} {'ECI':<6} {'RQ1':<8} {'95% CI'}")
    print("-" * 55)
    for pt in sorted(plot_points, key=lambda p: p["eci_score"], reverse=True):
        print(
            f"{get_model_display_name(pt['model']):<25} "
            f"{pt['eci_score']:<6} "
            f"{pt['rq1_mean']:.3f}   "
            f"[{pt['rq1_lower']:.3f}, {pt['rq1_upper']:.3f}]"
        )
    print(f"\nPearson r = {corr:.3f}")


def main(
    unambiguous: bool = False,
):
    """Generate Plot 28: ECI vs RQ1 scatter plot.

    Models with unreliable RQ1 are always excluded:
    P(C > 0) < 95% or P(min(A,B,C) < 0) > 5%.

    Args:
        unambiguous: If True, use posteriors from per-model_unambiguous fits
    """
    posteriors_dir = (
        Path("paper_cache/posteriors/pooled/per-model_unambiguous")
        if unambiguous
        else POSTERIORS_DIR
    )
    suffix = "_unambiguous" if unambiguous else ""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plot_eci_vs_rq1(
        OUTPUT_DIR / f"plot_28_eci_vs_rq1{suffix}.pdf",
        posteriors_dir=posteriors_dir,
    )


if __name__ == "__main__":
    fire.Fire(main)
