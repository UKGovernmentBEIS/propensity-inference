#!/usr/bin/env python3
"""Plot 21: RQ1 (Strategic-ness) by Model using pooled per-model fits.

Unlike plot_01 which loads individual (model, variation) fits and does ad-hoc
weighted averaging, this plot loads directly from per-model pooled fits where
the Bayesian regression already handles the pooling across variations.

RQ1 = (A + C - B) / (2C)

Where:
    A = Strategic model improvement over trivial baseline (intercepts-only)
    B = Non-strategic model improvement over trivial baseline
    C = Combined model improvement over trivial baseline

The trivial baseline has per-variation intercepts but no parameter effects,
so A/B/C measure improvement from the parameter effects only.

Output:
    - figures/plot_21_rq1_by_model_pooled.pdf (bar chart, default)
    - figures/plot_21_rq1_by_model_pooled_violin.pdf (violin plot)
    - figures/plot_21_baseline_comparison.pdf (Bayesian vs MLE baseline comparison)

Usage:
    uv run scripts/paper/plots/plot_21_rq1_by_model_pooled.py
    uv run scripts/paper/plots/plot_21_rq1_by_model_pooled.py --violin
    uv run scripts/paper/plots/plot_21_rq1_by_model_pooled.py --compare-baselines
"""

import json
import logging
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.paper_style import (
    FIG_WIDTH_DOUBLE,
    FONTSIZE_AXIS_LABEL,
    FONTSIZE_TICK,
    FONTSIZE_TITLE,
    PROVIDER_COLORS,
    get_model_color,
    get_model_display_name,
    setup_style,
    sort_models,
    sort_models_by_release,
)
from lib.pooled_fitting.weighting import VARIATION_BASE_WEIGHTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model")
SINGLE_DIR = Path("paper_cache/posteriors/pooled/single")
OUTPUT_DIR = Path("paper_cache/figures")


def slug_to_model_id(slug: str) -> str:
    """Convert model slug back to API model ID."""
    if "_" in slug:
        parts = slug.split("_", 1)
        return f"{parts[0]}/{parts[1]}"
    return slug


def load_model_data() -> list[dict]:
    """Load RQ1 distributions from per-model pooled fits.

    The A, B, C distributions are already computed relative to the trivial
    baseline (intercepts-only), so they measure improvement from parameter
    effects only. No adjustment needed.

    Returns list of dicts with:
        - model: API model ID
        - model_slug: filesystem slug
        - rq1_dist: RQ1 posterior distribution (clipped to [0, 1])
        - rq1_dist_unclipped: RQ1 posterior distribution (raw)
        - p_c_positive: P(C > 0)
        - p_min_negative: P(min(A, B, C) < 0) - flags unreliable RQ1
        - n_samples: number of samples used in fit
        - n_variations: number of variations pooled
    """
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")

    npz_files = sorted(POSTERIORS_DIR.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")

    results = []
    for npz_path in npz_files:
        model_slug = npz_path.stem
        json_path = POSTERIORS_DIR / f"{model_slug}.json"
        model_id = slug_to_model_id(model_slug)

        # Load posteriors (A, B, C already computed vs trivial baseline)
        data = np.load(npz_path)

        if "RQ1_distribution" not in data:
            raise ValueError(f"Missing RQ1_distribution in {npz_path}")
        if "A_distribution" not in data:
            raise ValueError(f"Missing A_distribution in {npz_path}")
        if "B_distribution" not in data:
            raise ValueError(f"Missing B_distribution in {npz_path}")
        if "C_distribution" not in data:
            raise ValueError(f"Missing C_distribution in {npz_path}")

        rq1_dist = data["RQ1_distribution"]
        A_dist = data["A_distribution"]
        B_dist = data["B_distribution"]
        C_dist = data["C_distribution"]

        # Handle NaN values (from C=0 cases)
        valid_mask = ~np.isnan(rq1_dist)
        rq1_valid = rq1_dist[valid_mask]
        A_valid = A_dist[valid_mask]
        B_valid = B_dist[valid_mask]
        C_valid = C_dist[valid_mask]

        if len(rq1_valid) == 0:
            raise ValueError(f"All RQ1 values are NaN for {model_slug}")

        # Compute P(min(A, B, C) < 0) - indicates unreliable RQ1
        min_abc = np.minimum(np.minimum(A_valid, B_valid), C_valid)
        p_min_negative = float(np.mean(min_abc < 0))

        # Clip RQ1 to [0, 1] for plotting
        rq1_clipped = np.clip(rq1_valid, 0, 1)

        # Compute P(C > 0)
        p_c_positive = float(np.mean(C_valid > 0))

        # Load summary for metadata
        if not json_path.exists():
            raise FileNotFoundError(f"Missing summary JSON: {json_path}")
        with open(json_path) as f:
            summary = json.load(f)
        n_samples = summary.get("n_samples", 0)
        n_variations = summary.get("n_variations", 0)

        results.append(
            {
                "model": model_id,
                "model_slug": model_slug,
                "rq1_dist": rq1_clipped,
                "rq1_dist_unclipped": rq1_valid,
                "p_c_positive": p_c_positive,
                "p_min_negative": p_min_negative,
                "n_samples": n_samples,
                "n_variations": n_variations,
            }
        )

        logger.debug(
            f"{get_model_display_name(model_id)}: RQ1={np.mean(rq1_clipped):.3f}, "
            f"P(min<0)={p_min_negative:.2f}"
        )

    return results


def compute_rq1_summary(model_data: list[dict]) -> pd.DataFrame:
    """Compute RQ1 summary statistics for each model.

    Returns DataFrame with: model, rq1_mean, rq1_lower, rq1_upper, p_c_positive,
                           p_min_negative, n_samples, n_variations
    """
    rows = []
    for d in model_data:
        rq1_dist = d["rq1_dist"]
        rows.append(
            {
                "model": d["model"],
                "rq1_mean": float(np.mean(rq1_dist)),
                "rq1_lower": float(np.percentile(rq1_dist, 2.5)),
                "rq1_upper": float(np.percentile(rq1_dist, 97.5)),
                "p_c_positive": d["p_c_positive"],
                "p_min_negative": d["p_min_negative"],
                "n_samples": d["n_samples"],
                "n_variations": d["n_variations"],
            }
        )
    return pd.DataFrame(rows)


def plot_rq1_by_model(
    model_df: pd.DataFrame,
    output_path: Path,
    exclude_flagged: bool = False,
    flag_threshold: float = 0.05,
) -> None:
    """Create bar chart of RQ1 by model.

    Args:
        model_df: DataFrame with model RQ1 statistics
        output_path: Where to save the figure
        exclude_flagged: If True, exclude models with P(min(A,B,C)<0) > flag_threshold
        flag_threshold: Threshold for flagging unreliable models
    """
    setup_style()

    # Separate flagged and included models
    if exclude_flagged:
        flagged_mask = model_df["p_min_negative"] > flag_threshold
        excluded_df = model_df[flagged_mask].copy()
        plot_df = model_df[~flagged_mask].copy()
    else:
        excluded_df = pd.DataFrame()
        plot_df = model_df.copy()

    # Sort models by provider then release date
    models = sort_models_by_release(plot_df["model"].tolist())
    plot_df = plot_df.set_index("model").loc[models].reset_index()

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 3.5))

    x = np.arange(len(models))
    colors = [get_model_color(m) for m in models]

    # Plot bars
    ax.bar(
        x,
        plot_df["rq1_mean"],
        color=colors,
        alpha=0.7,
        edgecolor="black",
        linewidth=0.5,
    )

    # Error bars (95% ETI)
    yerr_lower = (plot_df["rq1_mean"] - plot_df["rq1_lower"]).clip(lower=0)
    yerr_upper = (plot_df["rq1_upper"] - plot_df["rq1_mean"]).clip(lower=0)
    ax.errorbar(
        x,
        plot_df["rq1_mean"],
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
    ax.set_ylabel("Strategic contribution", fontsize=FONTSIZE_AXIS_LABEL - 1)
    ax.set_title(
        "Relative explanatory power of strategic vs. non-strategic factors",
        fontsize=FONTSIZE_TITLE,
        fontweight="bold",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 2,
    )

    # Y-axis limits and percentages
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    # Add P(C>0) annotation below each bar
    for i, (_, row) in enumerate(plot_df.iterrows()):
        # Show P(C>0) if less than 1
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

    # Provider color legend
    from matplotlib.patches import Patch

    provider_legend = [
        Patch(
            facecolor=PROVIDER_COLORS["anthropic"],
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
            label="Anthropic",
        ),
        Patch(
            facecolor=PROVIDER_COLORS["openai"],
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
            label="OpenAI",
        ),
        Patch(
            facecolor=PROVIDER_COLORS["openrouter/google"],
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
            label="Google",
        ),
        Patch(
            facecolor=PROVIDER_COLORS["openrouter/meta-llama"],
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
            label="Meta",
        ),
    ]
    ax.legend(
        handles=provider_legend,
        loc="upper right",
        fontsize=8,
        frameon=True,
        fancybox=True,
        framealpha=0.8,
    )

    # Annotation box - only show if not excluding flagged models
    if not exclude_flagged:
        annotation = (
            "RQ1 > 0.5: Strategic factors dominate\n"
            "RQ1 < 0.5: Non-strategic factors dominate\n"
            "(from per-model pooled Bayesian regression)"
        )
        ax.text(
            0.02,
            0.98,
            annotation,
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved plot to {output_path}")

    if exclude_flagged and len(excluded_df) > 0:
        logger.info(f"Excluded {len(excluded_df)} models with unreliable RQ1")


def plot_rq1_by_model_violin(
    model_data: list[dict],
    model_df: pd.DataFrame,
    output_path: Path,
    flag_threshold: float = 0.05,
) -> None:
    """Create violin plot of RQ1 by model showing full posterior distributions.

    Args:
        model_data: List of dicts with model info and rq1_dist arrays
        model_df: Summary DataFrame with rq1_mean, rq1_lower, rq1_upper
        output_path: Where to save the figure
        flag_threshold: Flag models with P(min(A,B,C) < 0) > this value
    """
    setup_style()

    # Sort models by provider then release date
    models = sort_models_by_release(model_df["model"].tolist())
    model_df = model_df.set_index("model").loc[models].reset_index()

    # Create lookup for distributions
    dist_lookup = {d["model"]: d["rq1_dist"] for d in model_data}

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 5.0))

    x_positions = np.arange(len(models))

    # Track flagged models for legend
    flagged_models = []

    # Plot each model's violin
    for i, model in enumerate(models):
        rq1_dist = dist_lookup.get(model)
        if rq1_dist is None or len(rq1_dist) == 0:
            continue

        row = model_df[model_df["model"] == model].iloc[0]
        color = get_model_color(model)
        p_min_neg = row["p_min_negative"]
        is_flagged = p_min_neg > flag_threshold

        if is_flagged:
            flagged_models.append((model, p_min_neg))

        # Create violin plot for this model
        # We use violinplot on a single dataset at position i
        parts = ax.violinplot(
            [rq1_dist],
            positions=[i],
            widths=0.7,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )

        # Color the violin body
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.7)
            pc.set_edgecolor("black")
            pc.set_linewidth(0.5)

        # Draw 95% ETI bounds as dashed horizontal lines within the violin
        rq1_lower = row["rq1_lower"]
        rq1_upper = row["rq1_upper"]

        # Get the width of the violin at the ETI bounds for proper line length
        # Approximate violin width at these points (use half width)
        half_width = 0.25

        ax.hlines(
            rq1_lower,
            i - half_width,
            i + half_width,
            colors="black",
            linestyles="dashed",
            linewidth=1.0,
            alpha=0.8,
        )
        ax.hlines(
            rq1_upper,
            i - half_width,
            i + half_width,
            colors="black",
            linestyles="dashed",
            linewidth=1.0,
            alpha=0.8,
        )

        # Draw posterior mean as black dot
        rq1_mean = row["rq1_mean"]
        ax.scatter(
            [i],
            [rq1_mean],
            color="black",
            s=30,
            zorder=10,
            edgecolors="white",
            linewidths=0.5,
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

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    # Y-axis limits and percentages
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    # Add P(min<0) annotation below each violin
    # Red for flagged models (>5%), black for reliable models (<=5%)
    for i, (_, row) in enumerate(model_df.iterrows()):
        p_min_neg = row["p_min_negative"]
        is_flagged = p_min_neg > flag_threshold
        ax.text(
            i,
            -0.02,
            f"{p_min_neg:.0%}",
            ha="center",
            va="top",
            fontsize=6,
            color="red" if is_flagged else "black",
            fontweight="bold" if is_flagged else "normal",
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved violin plot to {output_path}")

    # Log flagged models
    if flagged_models:
        logger.info(
            f"Flagged {len(flagged_models)} models with P(min(A,B,C)<0) > {flag_threshold:.0%}:"
        )
        for model, p in flagged_models:
            logger.info(f"  {get_model_display_name(model)}: P(min<0) = {p:.1%}")


def compute_mle_baseline_rq1(model_slug: str) -> dict | None:
    """Compute RQ1 using MLE (empirical) baseline instead of Bayesian baseline.

    The MLE baseline uses per-(model, variation) intercepts fit via maximum
    likelihood (i.e., logit of the empirical misalignment rate for each pair).

    This loads data from single/ fits and computes the MLE log-likelihood,
    then recomputes A, B, C relative to this baseline.

    Args:
        model_slug: The model slug (e.g., "anthropic_claude-3-5-haiku-20241022")

    Returns:
        Dict with rq1_mle_dist, or None if single fits unavailable for this model.
    """
    # Load per-model posteriors (these must exist since model was already loaded)
    npz_path = POSTERIORS_DIR / f"{model_slug}.npz"
    json_path = POSTERIORS_DIR / f"{model_slug}.json"

    if not npz_path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {npz_path}")
    if not json_path.exists():
        raise FileNotFoundError(f"Missing summary file: {json_path}")

    data = np.load(npz_path)

    required_keys = [
        "strategic_logliks",
        "non_strategic_logliks",
        "combined_logliks",
        "trivial_logliks",
    ]
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing {key} in {npz_path}")

    strategic_logliks = data["strategic_logliks"]
    non_strategic_logliks = data["non_strategic_logliks"]
    combined_logliks = data["combined_logliks"]

    # Load single fits for this model to compute MLE baseline
    # These may not exist for all models - return None if unavailable
    variations_data = {}
    total_n = 0

    for variation in VARIATION_BASE_WEIGHTS.keys():
        single_json = SINGLE_DIR / f"{model_slug}_{variation}.json"
        if single_json.exists():
            with open(single_json) as f:
                single_summary = json.load(f)
            variations_data[variation] = {
                "n": single_summary["n_samples"],
                "p": single_summary["misalignment_rate"],
                "weight": VARIATION_BASE_WEIGHTS[variation],
            }
            total_n += single_summary["n_samples"]

    if not variations_data:
        # No single fits available for this model - can't compute MLE baseline
        return None

    # Compute MLE log-likelihood with proper weighting
    # Normalization factor: total weight sums to n_samples
    total_effective_weight = sum(d["weight"] for d in variations_data.values())
    normalization_factor = total_n / total_effective_weight

    mle_loglik = 0.0
    for variation, vdata in variations_data.items():
        p = vdata["p"]
        effective_pair_weight = vdata["weight"] * normalization_factor

        # MLE log-likelihood contribution: weight * binary_entropy(p)
        if 0 < p < 1:
            binary_entropy_ll = p * np.log(p) + (1 - p) * np.log(1 - p)
        else:
            binary_entropy_ll = 0.0  # Perfect prediction (p=0 or p=1)

        mle_loglik += effective_pair_weight * binary_entropy_ll

    # Compute A, B, C relative to MLE baseline
    A_mle = strategic_logliks - mle_loglik
    B_mle = non_strategic_logliks - mle_loglik
    C_mle = combined_logliks - mle_loglik

    # Compute RQ1 with MLE baseline
    RQ1_mle = np.zeros_like(C_mle)
    valid_mask = C_mle != 0
    RQ1_mle[valid_mask] = (
        A_mle[valid_mask] + C_mle[valid_mask] - B_mle[valid_mask]
    ) / (2 * C_mle[valid_mask])
    RQ1_mle[~valid_mask] = np.nan

    # Handle NaN values
    valid_rq1 = RQ1_mle[~np.isnan(RQ1_mle)]
    if len(valid_rq1) == 0:
        raise ValueError(f"All MLE RQ1 values are NaN for {model_slug}")

    return {
        "rq1_mle_dist": np.clip(valid_rq1, 0, 1),
        "rq1_mle_dist_unclipped": valid_rq1,
        "mle_loglik": mle_loglik,
        "A_mle_mean": float(np.mean(A_mle)),
        "B_mle_mean": float(np.mean(B_mle)),
        "C_mle_mean": float(np.mean(C_mle)),
    }


def plot_baseline_comparison(
    model_data: list[dict],
    output_path: Path,
    flag_threshold: float = 0.05,
) -> None:
    """Create violin plot comparing Bayesian vs MLE baseline RQ1.

    Shows side-by-side violins for each model, with Bayesian baseline on the
    left and MLE baseline on the right. Only includes models with reliable
    posteriors (P(min(A,B,C) < 0) <= flag_threshold).

    Args:
        model_data: List of dicts with model info and rq1_dist arrays
        output_path: Where to save the figure
        flag_threshold: Only include models with P(min(A,B,C)<0) <= this value
    """
    setup_style()

    # Filter to models with reliable posteriors
    reliable_data = [d for d in model_data if d["p_min_negative"] <= flag_threshold]

    if not reliable_data:
        raise ValueError(
            f"No models pass the reliability threshold (P(min<0) <= {flag_threshold})"
        )

    # Compute MLE baseline RQ1 for each model
    for d in reliable_data:
        mle_result = compute_mle_baseline_rq1(d["model_slug"])
        if mle_result:
            d["rq1_mle_dist"] = mle_result["rq1_mle_dist"]
            d["mle_loglik"] = mle_result["mle_loglik"]
        else:
            d["rq1_mle_dist"] = None

    # Filter to models with both distributions
    plot_data = [d for d in reliable_data if d.get("rq1_mle_dist") is not None]

    if not plot_data:
        raise ValueError("No models have both Bayesian and MLE baseline data")

    # Sort models by capability
    models = sort_models([d["model"] for d in plot_data])
    data_lookup = {d["model"]: d for d in plot_data}

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 5.5))

    x_positions = np.arange(len(models))
    violin_width = 0.35
    offset = 0.18

    # Plot each model's violins
    for i, model in enumerate(models):
        d = data_lookup[model]
        color = get_model_color(model)

        # Bayesian baseline (left violin)
        rq1_bayesian = d["rq1_dist"]
        parts_bayes = ax.violinplot(
            [rq1_bayesian],
            positions=[i - offset],
            widths=violin_width,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )
        for pc in parts_bayes["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.7)
            pc.set_edgecolor("black")
            pc.set_linewidth(0.5)

        # MLE baseline (right violin)
        rq1_mle = d["rq1_mle_dist"]
        parts_mle = ax.violinplot(
            [rq1_mle],
            positions=[i + offset],
            widths=violin_width,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )
        for pc in parts_mle["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.4)  # Lighter for MLE
            pc.set_edgecolor("black")
            pc.set_linewidth(0.5)
            pc.set_linestyle("--")

        # Draw posterior means
        bayes_mean = float(np.mean(rq1_bayesian))
        mle_mean = float(np.mean(rq1_mle))

        ax.scatter(
            [i - offset],
            [bayes_mean],
            color="black",
            s=25,
            zorder=10,
            edgecolors="white",
            linewidths=0.5,
        )
        ax.scatter(
            [i + offset],
            [mle_mean],
            color="black",
            s=25,
            zorder=10,
            edgecolors="white",
            linewidths=0.5,
            marker="D",
        )

    # Reference lines
    ax.axhline(0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.3)

    # Labels
    total_samples = sum(d["n_samples"] for d in plot_data)
    ax.set_xlabel("Model", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_ylabel("RQ1 (Strategic-ness)", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(
        f"RQ1: Bayesian vs MLE Baseline Comparison\n"
        f"{len(models)} models with reliable posteriors, {total_samples:,} total samples",
        fontsize=FONTSIZE_TITLE,
    )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    ax.set_ylim(-0.05, 1.05)

    # Legend
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(
            facecolor="gray",
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
            label="Bayesian baseline",
        ),
        Patch(
            facecolor="gray",
            alpha=0.4,
            edgecolor="black",
            linewidth=0.5,
            linestyle="--",
            label="MLE baseline",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="black",
            markersize=6,
            label="Bayesian mean",
        ),
        Line2D(
            [0],
            [0],
            marker="D",
            color="w",
            markerfacecolor="black",
            markersize=5,
            label="MLE mean",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved baseline comparison plot to {output_path}")

    # Print comparison summary
    print("\n=== Baseline Comparison Summary ===\n")
    print(f"{'Model':<25} {'Bayesian RQ1':<14} {'MLE RQ1':<14} {'Difference'}")
    print("-" * 65)

    for model in models:
        d = data_lookup[model]
        bayes_mean = float(np.mean(d["rq1_dist"]))
        mle_mean = float(np.mean(d["rq1_mle_dist"]))
        diff = mle_mean - bayes_mean
        print(
            f"{get_model_display_name(model):<25} "
            f"{bayes_mean:>6.3f}        "
            f"{mle_mean:>6.3f}        "
            f"{diff:>+6.3f}"
        )

    # Overall summary
    all_bayes = [float(np.mean(data_lookup[m]["rq1_dist"])) for m in models]
    all_mle = [float(np.mean(data_lookup[m]["rq1_mle_dist"])) for m in models]
    print(f"\n{'=' * 65}")
    print(f"Mean Bayesian RQ1: {np.mean(all_bayes):.3f}")
    print(f"Mean MLE RQ1:      {np.mean(all_mle):.3f}")
    print(f"Mean difference:   {np.mean(all_mle) - np.mean(all_bayes):+.3f}")


def plot_baseline_comparison_bars(
    model_data: list[dict],
    output_path: Path,
    flag_threshold: float = 0.05,
) -> None:
    """Create bar chart comparing Bayesian vs MLE baseline RQ1.

    Shows paired bars for each model, with Bayesian baseline on the left
    and MLE baseline on the right. Only includes models with reliable
    posteriors (P(min(A,B,C) < 0) <= flag_threshold).

    Args:
        model_data: List of dicts with model info and rq1_dist arrays
        output_path: Where to save the figure
        flag_threshold: Only include models with P(min(A,B,C)<0) <= this value
    """
    setup_style()

    # Filter to models with reliable posteriors
    reliable_data = [d for d in model_data if d["p_min_negative"] <= flag_threshold]

    if not reliable_data:
        raise ValueError(
            f"No models pass the reliability threshold (P(min<0) <= {flag_threshold})"
        )

    # Compute MLE baseline RQ1 for each model
    for d in reliable_data:
        mle_result = compute_mle_baseline_rq1(d["model_slug"])
        if mle_result:
            d["rq1_mle_dist"] = mle_result["rq1_mle_dist"]
        else:
            d["rq1_mle_dist"] = None

    # Filter to models with both distributions
    plot_data = [d for d in reliable_data if d.get("rq1_mle_dist") is not None]

    if not plot_data:
        raise ValueError("No models have both Bayesian and MLE baseline data")

    # Sort models by provider then release date (most recent first)
    models = sort_models_by_release([d["model"] for d in plot_data])
    data_lookup = {d["model"]: d for d in plot_data}

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 4.5))

    x_positions = np.arange(len(models))
    bar_width = 0.35

    # Collect data for bars
    bayes_means = []
    bayes_lowers = []
    bayes_uppers = []
    mle_means = []
    mle_lowers = []
    mle_uppers = []
    colors = []

    for model in models:
        d = data_lookup[model]
        colors.append(get_model_color(model))

        # Bayesian stats
        bayes_dist = d["rq1_dist"]
        bayes_means.append(float(np.mean(bayes_dist)))
        bayes_lowers.append(float(np.percentile(bayes_dist, 2.5)))
        bayes_uppers.append(float(np.percentile(bayes_dist, 97.5)))

        # MLE stats
        mle_dist = d["rq1_mle_dist"]
        mle_means.append(float(np.mean(mle_dist)))
        mle_lowers.append(float(np.percentile(mle_dist, 2.5)))
        mle_uppers.append(float(np.percentile(mle_dist, 97.5)))

    bayes_means = np.array(bayes_means)
    bayes_lowers = np.array(bayes_lowers)
    bayes_uppers = np.array(bayes_uppers)
    mle_means = np.array(mle_means)
    mle_lowers = np.array(mle_lowers)
    mle_uppers = np.array(mle_uppers)

    # Plot Bayesian bars (left)
    ax.bar(
        x_positions - bar_width / 2,
        bayes_means,
        bar_width,
        color=colors,
        alpha=0.8,
        edgecolor="black",
        linewidth=0.5,
        label="Bayesian baseline",
    )

    # Error bars for Bayesian
    ax.errorbar(
        x_positions - bar_width / 2,
        bayes_means,
        yerr=[bayes_means - bayes_lowers, bayes_uppers - bayes_means],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
    )

    # Plot MLE bars (right) - lighter alpha, hatched
    ax.bar(
        x_positions + bar_width / 2,
        mle_means,
        bar_width,
        color=colors,
        alpha=0.4,
        edgecolor="black",
        linewidth=0.5,
        hatch="//",
        label="MLE baseline",
    )

    # Error bars for MLE
    ax.errorbar(
        x_positions + bar_width / 2,
        mle_means,
        yerr=[mle_means - mle_lowers, mle_uppers - mle_means],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
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

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    ax.set_ylim(0, 1.05)

    # Y-axis as percentages
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    # Legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(
            facecolor="gray",
            alpha=0.8,
            edgecolor="black",
            linewidth=0.5,
            label="Bayesian baseline",
        ),
        Patch(
            facecolor="gray",
            alpha=0.4,
            edgecolor="black",
            linewidth=0.5,
            hatch="//",
            label="MLE baseline",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved baseline comparison bar plot to {output_path}")

    # Print comparison summary
    print("\n=== Baseline Comparison Summary ===\n")
    print(f"{'Model':<25} {'Bayesian RQ1':<14} {'MLE RQ1':<14} {'Difference'}")
    print("-" * 65)

    for i, model in enumerate(models):
        diff = mle_means[i] - bayes_means[i]
        print(
            f"{get_model_display_name(model):<25} "
            f"{bayes_means[i]:>6.3f}        "
            f"{mle_means[i]:>6.3f}        "
            f"{diff:>+6.3f}"
        )

    print(f"\n{'=' * 65}")
    print(f"Mean Bayesian RQ1: {np.mean(bayes_means):.3f}")
    print(f"Mean MLE RQ1:      {np.mean(mle_means):.3f}")
    print(f"Mean difference:   {np.mean(mle_means) - np.mean(bayes_means):+.3f}")


def plot_unambiguous_comparison(
    data_all: list[dict],
    data_unamb: list[dict],
    output_path: Path,
    flag_threshold: float = 0.05,
) -> None:
    """Create bar chart comparing all-variation vs unambiguous-only RQ1.

    Shows paired bars for each model: solid (all variations) on the left,
    hatched (unambiguous only) on the right.

    Args:
        data_all: Model data from all-variation fits
        data_unamb: Model data from unambiguous-only fits
        output_path: Where to save the figure
        flag_threshold: Only include models with P(min(A,B,C)<0) <= this value
    """
    setup_style()
    from matplotlib.patches import Patch

    # Build lookups
    lookup_all = {d["model"]: d for d in data_all}
    lookup_unamb = {d["model"]: d for d in data_unamb}

    # Only include models present in both and with reliable posteriors in both
    common_models = []
    for model in lookup_all:
        if model not in lookup_unamb:
            continue
        if (
            lookup_all[model]["p_min_negative"] > flag_threshold
            or lookup_unamb[model]["p_min_negative"] > flag_threshold
        ):
            continue
        common_models.append(model)

    if not common_models:
        raise ValueError("No models have reliable posteriors in both fits")

    models = sort_models_by_release(common_models)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 4.5))

    x_positions = np.arange(len(models))
    bar_width = 0.35

    all_means = []
    all_lowers = []
    all_uppers = []
    unamb_means = []
    unamb_lowers = []
    unamb_uppers = []
    colors = []

    for model in models:
        colors.append(get_model_color(model))

        dist_all = lookup_all[model]["rq1_dist"]
        all_means.append(float(np.mean(dist_all)))
        all_lowers.append(float(np.percentile(dist_all, 2.5)))
        all_uppers.append(float(np.percentile(dist_all, 97.5)))

        dist_unamb = lookup_unamb[model]["rq1_dist"]
        unamb_means.append(float(np.mean(dist_unamb)))
        unamb_lowers.append(float(np.percentile(dist_unamb, 2.5)))
        unamb_uppers.append(float(np.percentile(dist_unamb, 97.5)))

    all_means_arr = np.array(all_means)
    all_lowers_arr = np.array(all_lowers)
    all_uppers_arr = np.array(all_uppers)
    unamb_means_arr = np.array(unamb_means)
    unamb_lowers_arr = np.array(unamb_lowers)
    unamb_uppers_arr = np.array(unamb_uppers)

    # All-variation bars (left, solid)
    ax.bar(
        x_positions - bar_width / 2,
        all_means_arr,
        bar_width,
        color=colors,
        alpha=0.8,
        edgecolor="black",
        linewidth=0.5,
    )
    ax.errorbar(
        x_positions - bar_width / 2,
        all_means_arr,
        yerr=[all_means_arr - all_lowers_arr, all_uppers_arr - all_means_arr],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
    )

    # Unambiguous bars (right, hatched)
    ax.bar(
        x_positions + bar_width / 2,
        unamb_means_arr,
        bar_width,
        color=colors,
        alpha=0.35,
        edgecolor="#666666",
        linewidth=0.5,
        hatch="//",
    )
    ax.errorbar(
        x_positions + bar_width / 2,
        unamb_means_arr,
        yerr=[
            unamb_means_arr - unamb_lowers_arr,
            unamb_uppers_arr - unamb_means_arr,
        ],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
    )

    # Reference lines
    ax.axhline(0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.3)

    ax.set_ylabel("Strategic contribution", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(
        "RQ1: All environments vs less ambiguous only",
        fontsize=FONTSIZE_TITLE,
    )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    legend_elements = [
        Patch(
            facecolor="gray",
            alpha=0.8,
            edgecolor="black",
            linewidth=0.5,
            label="All environments",
        ),
        Patch(
            facecolor="gray",
            alpha=0.35,
            edgecolor="#666666",
            linewidth=0.5,
            hatch="//",
            label="Less ambiguous only",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved less-ambiguous comparison plot to {output_path}")

    # Print comparison summary
    print("\n=== All vs Less Ambiguous Comparison ===\n")
    print(f"{'Model':<25} {'All RQ1':<14} {'L.A. RQ1':<14} {'Difference'}")
    print("-" * 65)

    for i, model in enumerate(models):
        diff = unamb_means_arr[i] - all_means_arr[i]
        print(
            f"{get_model_display_name(model):<25} "
            f"{all_means_arr[i]:>6.3f}        "
            f"{unamb_means_arr[i]:>6.3f}        "
            f"{diff:>+6.3f}"
        )

    print(f"\n{'=' * 65}")
    print(f"Mean All RQ1:          {np.mean(all_means_arr):.3f}")
    print(f"Mean Less Ambig. RQ1:  {np.mean(unamb_means_arr):.3f}")
    print(
        f"Mean difference:       {np.mean(unamb_means_arr) - np.mean(all_means_arr):+.3f}"
    )


def load_model_data_with_waic_adjustment() -> list[dict]:
    """Load model data and compute WAIC-approximated RQ1 alongside standard RQ1.

    Uses Var(total LL) across posterior draws as a rough proxy for p_WAIC.
    This isn't true WAIC (which requires per-observation log-likelihoods)
    but gives directional sense of the complexity penalty correction.

    WAIC-adjusted score: mean(LL) - Var(LL)
    Then A_waic = adjusted(strategic) - adjusted(trivial), etc.
    """
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")

    npz_files = sorted(POSTERIORS_DIR.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")

    results = []
    for npz_path in npz_files:
        model_slug = npz_path.stem
        json_path = POSTERIORS_DIR / f"{model_slug}.json"
        model_id = slug_to_model_id(model_slug)

        data = np.load(npz_path)

        # Load raw log-likelihoods per draw
        strat_ll = data["strategic_logliks"]
        nonstrat_ll = data["non_strategic_logliks"]
        combined_ll = data["combined_logliks"]
        trivial_ll = data["trivial_logliks"]

        # Standard RQ1 (already computed)
        rq1_dist = data["RQ1_distribution"]
        A_dist = data["A_distribution"]
        B_dist = data["B_distribution"]
        C_dist = data["C_distribution"]

        # WAIC-like penalty: Var(total LL) across draws as proxy for p_WAIC
        penalty_strat = float(np.var(strat_ll))
        penalty_nonstrat = float(np.var(nonstrat_ll))
        penalty_combined = float(np.var(combined_ll))
        penalty_trivial = float(np.var(trivial_ll))

        # Adjusted improvements (subtract differential penalty from each draw)
        delta_penalty_A = penalty_strat - penalty_trivial
        delta_penalty_B = penalty_nonstrat - penalty_trivial
        delta_penalty_C = penalty_combined - penalty_trivial

        A_waic = A_dist - delta_penalty_A
        B_waic = B_dist - delta_penalty_B
        C_waic = C_dist - delta_penalty_C

        # Compute WAIC-adjusted RQ1
        rq1_waic = np.zeros_like(C_waic)
        valid_mask = C_waic != 0
        rq1_waic[valid_mask] = (
            A_waic[valid_mask] + C_waic[valid_mask] - B_waic[valid_mask]
        ) / (2 * C_waic[valid_mask])
        rq1_waic[~valid_mask] = np.nan

        # Handle NaN
        valid = ~np.isnan(rq1_dist) & ~np.isnan(rq1_waic)
        rq1_standard = np.clip(rq1_dist[valid], 0, 1)
        rq1_waic_clipped = np.clip(rq1_waic[valid], 0, 1)

        # Load metadata
        if not json_path.exists():
            raise FileNotFoundError(f"Missing summary JSON: {json_path}")
        with open(json_path) as f:
            summary = json.load(f)

        # Compute P(min(A,B,C) < 0) for standard
        min_abc = np.minimum(np.minimum(A_dist, B_dist), C_dist)
        p_min_negative = float(np.mean(min_abc < 0))

        results.append(
            {
                "model": model_id,
                "model_slug": model_slug,
                "rq1_standard": rq1_standard,
                "rq1_waic": rq1_waic_clipped,
                "p_min_negative": p_min_negative,
                "n_samples": summary.get("n_samples", 0),
                "delta_penalty_A": delta_penalty_A,
                "delta_penalty_B": delta_penalty_B,
                "delta_penalty_C": delta_penalty_C,
            }
        )

        logger.debug(
            f"{get_model_display_name(model_id)}: "
            f"standard={np.mean(rq1_standard):.3f}, "
            f"waic={np.mean(rq1_waic_clipped):.3f}, "
            f"penalties: A={delta_penalty_A:.1f}, B={delta_penalty_B:.1f}, C={delta_penalty_C:.1f}"
        )

    return results


def plot_waic_comparison(
    waic_data: list[dict],
    output_path: Path,
    flag_threshold: float = 0.05,
) -> None:
    """Create side-by-side bar chart comparing standard vs WAIC-adjusted RQ1.

    Args:
        waic_data: List of dicts from load_model_data_with_waic_adjustment
        output_path: Where to save the figure
        flag_threshold: Only include models with P(min(A,B,C)<0) <= this value
    """
    setup_style()
    from matplotlib.patches import Patch

    # Filter to reliable models
    reliable = [d for d in waic_data if d["p_min_negative"] <= flag_threshold]
    if not reliable:
        raise ValueError("No models pass reliability threshold")

    # Sort by provider then release date
    models = sort_models_by_release([d["model"] for d in reliable])
    lookup = {d["model"]: d for d in reliable}

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 4.5))

    x_positions = np.arange(len(models))
    bar_width = 0.35

    std_means, std_los, std_his = [], [], []
    waic_means, waic_los, waic_his = [], [], []
    colors = []

    for m in models:
        d = lookup[m]
        colors.append(get_model_color(m))

        s = d["rq1_standard"]
        std_means.append(float(np.mean(s)))
        std_los.append(float(np.percentile(s, 2.5)))
        std_his.append(float(np.percentile(s, 97.5)))

        w = d["rq1_waic"]
        waic_means.append(float(np.mean(w)))
        waic_los.append(float(np.percentile(w, 2.5)))
        waic_his.append(float(np.percentile(w, 97.5)))

    std_means = np.array(std_means)
    std_los = np.array(std_los)
    std_his = np.array(std_his)
    waic_means = np.array(waic_means)
    waic_los = np.array(waic_los)
    waic_his = np.array(waic_his)

    # Standard bars (left)
    ax.bar(
        x_positions - bar_width / 2,
        std_means,
        bar_width,
        color=colors,
        alpha=0.8,
        edgecolor="black",
        linewidth=0.5,
        label="Standard (log-likelihood)",
    )
    ax.errorbar(
        x_positions - bar_width / 2,
        std_means,
        yerr=[std_means - std_los, std_his - std_means],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
    )

    # WAIC-adjusted bars (right, hatched)
    ax.bar(
        x_positions + bar_width / 2,
        waic_means,
        bar_width,
        color=colors,
        alpha=0.4,
        edgecolor="black",
        linewidth=0.5,
        hatch="//",
        label="WAIC-adjusted",
    )
    ax.errorbar(
        x_positions + bar_width / 2,
        waic_means,
        yerr=[waic_means - waic_los, waic_his - waic_means],
        fmt="none",
        color="black",
        capsize=2,
        linewidth=0.8,
    )

    # Reference lines
    ax.axhline(0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.3)

    ax.set_ylabel("Strategic contribution", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(
        "RQ1: Standard log-likelihood vs WAIC-adjusted (Var(LL) proxy)",
        fontsize=FONTSIZE_TITLE,
    )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        [get_model_display_name(m) for m in models],
        rotation=45,
        ha="right",
        fontsize=FONTSIZE_TICK - 1,
    )

    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    legend_elements = [
        Patch(
            facecolor="gray",
            alpha=0.8,
            edgecolor="black",
            linewidth=0.5,
            label="Standard (log-likelihood)",
        ),
        Patch(
            facecolor="gray",
            alpha=0.4,
            edgecolor="black",
            linewidth=0.5,
            hatch="//",
            label="WAIC-adjusted",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved WAIC comparison to {output_path}")

    # Print comparison summary
    print("\n=== WAIC Comparison Summary ===\n")
    print(
        f"{'Model':<25} {'Standard':<10} {'WAIC-adj':<10} {'Diff':<8} {'ΔpA':<8} {'ΔpB':<8} {'ΔpC':<8}"
    )
    print("-" * 85)

    for i, m in enumerate(models):
        d = lookup[m]
        diff = waic_means[i] - std_means[i]
        print(
            f"{get_model_display_name(m):<25} "
            f"{std_means[i]:>6.3f}    "
            f"{waic_means[i]:>6.3f}    "
            f"{diff:>+6.3f}  "
            f"{d['delta_penalty_A']:>6.1f}  "
            f"{d['delta_penalty_B']:>6.1f}  "
            f"{d['delta_penalty_C']:>6.1f}"
        )

    print(f"\n{'=' * 85}")
    print(f"Mean Standard RQ1:     {np.mean(std_means):.3f}")
    print(f"Mean WAIC-adj RQ1:     {np.mean(waic_means):.3f}")
    print(f"Mean difference:       {np.mean(waic_means) - np.mean(std_means):+.3f}")


def main(
    violin: bool = False,
    exclude_flagged: bool = False,
    compare_baselines: bool = False,
    compare_unambiguous: bool = False,
    compare_waic: bool = False,
    unambiguous: bool = False,
):
    """Generate Plot 21: RQ1 by Model (Pooled Fits).

    Args:
        violin: If True, generate violin plot instead of bar chart
        exclude_flagged: If True, exclude models with P(min(A,B,C)<0) > 5%
                        (only applies to bar chart mode)
        compare_baselines: If True, generate comparison plot showing Bayesian
                          vs MLE baseline RQ1 for models with reliable posteriors
        compare_unambiguous: If True, generate paired bar chart comparing
                            all-variation vs unambiguous-only RQ1
        unambiguous: If True, use posteriors from per-model_unambiguous fits
    """
    global POSTERIORS_DIR

    if compare_unambiguous:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Load both sets
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model")
        logger.info("Loading all-environment posteriors...")
        data_all = load_model_data()

        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model_unambiguous")
        logger.info("Loading less-ambiguous posteriors...")
        data_unamb = load_model_data()

        plot_unambiguous_comparison(
            data_all,
            data_unamb,
            OUTPUT_DIR / "plot_21_rq1_by_model_pooled_filtered_unambiguous.pdf",
        )
        return

    if compare_waic:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Loading model data for WAIC comparison...")
        waic_data = load_model_data_with_waic_adjustment()
        logger.info(f"Loaded {len(waic_data)} models")
        plot_waic_comparison(
            waic_data,
            OUTPUT_DIR / "plot_21_waic_comparison.pdf",
        )
        return

    if unambiguous:
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model_unambiguous")

    suffix = "_unambiguous" if unambiguous else ""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load per-model data (A, B, C already computed vs trivial baseline)
    logger.info("Loading per-model pooled posteriors...")
    model_data = load_model_data()
    logger.info(f"Loaded {len(model_data)} models")

    # Compute summary statistics
    model_df = compute_rq1_summary(model_data)

    # Generate plot
    if compare_baselines:
        plot_baseline_comparison_bars(
            model_data, OUTPUT_DIR / f"plot_21_baseline_comparison{suffix}.pdf"
        )
        return  # Skip the standard summary output
    elif violin:
        plot_rq1_by_model_violin(
            model_data,
            model_df,
            OUTPUT_DIR / f"plot_21_rq1_by_model_pooled_violin{suffix}.pdf",
        )
    elif exclude_flagged:
        plot_rq1_by_model(
            model_df,
            OUTPUT_DIR / f"plot_21_rq1_by_model_pooled_filtered{suffix}.pdf",
            exclude_flagged=True,
        )
    else:
        plot_rq1_by_model(
            model_df, OUTPUT_DIR / f"plot_21_rq1_by_model_pooled{suffix}.pdf"
        )

    # Print summary table
    print("\n=== RQ1 by Model (Pooled Fits) ===\n")
    print(
        f"{'Model':<25} {'RQ1':<8} {'95% ETI':<18} {'P(min<0)':<10} {'N Samples':<12} {'Flag'}"
    )
    print("-" * 90)

    # Sort by RQ1 descending
    model_df_sorted = model_df.sort_values("rq1_mean", ascending=False)

    for _, row in model_df_sorted.iterrows():
        p_min_neg = row["p_min_negative"]
        flag = "  **" if p_min_neg > 0.05 else ""
        print(
            f"{get_model_display_name(row['model']):<25} "
            f"{row['rq1_mean']:.3f}   "
            f"[{row['rq1_lower']:.3f}, {row['rq1_upper']:.3f}]  "
            f"{p_min_neg:>6.1%}     "
            f"{row['n_samples']:>10,} "
            f"{flag}"
        )

    # Overall statistics
    print(f"\n{'=' * 90}")
    print(
        f"Models with RQ1 > 0.5: {(model_df['rq1_mean'] > 0.5).sum()} / {len(model_df)}"
    )
    print(f"Mean RQ1 across models: {model_df['rq1_mean'].mean():.3f}")
    print(f"Median RQ1: {model_df['rq1_mean'].median():.3f}")
    print(f"\nTotal samples: {model_df['n_samples'].sum():,}")

    # Flagged models summary
    n_flagged = (model_df["p_min_negative"] > 0.05).sum()
    if n_flagged > 0:
        print(f"\n** {n_flagged} models flagged with P(min(A,B,C) < 0) > 5%")
        print(
            "   These have substantial probability that at least one model (strategic,"
        )
        print("   non-strategic, or combined) performs WORSE than trivial baseline.")
        print("   RQ1 values for these models may be unreliable.")

    print(f"\nOutput saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    fire.Fire(main)
