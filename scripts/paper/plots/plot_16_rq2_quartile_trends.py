#!/usr/bin/env python3
"""Plot RQ2: Strategic sensitivity trends across capability quartiles.

Produces 2 figures:
1. Megaplot: All metrics in one figure (S, NS, difference, quotient, RQ1)
2. 6-factor vs 12-factor comparison: 2x2 grid

Usage:
    uv run scripts/paper/plots/plot_16_rq2_quartile_trends.py
"""

import argparse
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from lib.paper_style import (
    FIG_WIDTH_DOUBLE,
    NON_STRATEGIC_PARAMS,
    STRATEGIC_PARAMS,
    setup_style,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile")
OUTPUT_DIR = Path("paper_cache/figures")
QUARTILES = ["q1", "q2", "q3", "q4"]
QUARTILE_LABELS = ["Q1\n(lowest)", "Q2", "Q3", "Q4\n(highest)"]

# Colors for factor types
COLOR_STRATEGIC = "black"
COLOR_NON_STRATEGIC = "black"
COLOR_COMBINED = "black"


def load_quartile_posteriors(quartile: str) -> dict[str, np.ndarray]:
    """Load posteriors for a specific quartile."""
    path = POSTERIORS_DIR / f"{quartile}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def compute_sum_abs_coefficients(
    posteriors: dict[str, np.ndarray],
    params: list[str],
    prefix: str,
) -> np.ndarray:
    """Compute sum of |coefficients| for given parameters.

    Args:
        posteriors: Dict of posterior samples
        params: List of parameter names
        prefix: Model prefix ('strategic_', 'non_strategic_', or 'combined_')

    Returns:
        Array of sum(|coef|) samples
    """
    coef_samples = []

    for param in params:
        # Find all effect columns for this parameter
        for key in posteriors.keys():
            if not key.startswith(f"{prefix}{param}_effects["):
                continue
            if "constrained" in key:
                continue
            coef_samples.append(posteriors[key])

    if not coef_samples:
        raise ValueError(
            f"No coefficients found for params {params} with prefix {prefix!r}"
        )

    # Sum absolute values
    result = np.zeros_like(coef_samples[0])
    for samples in coef_samples:
        result += np.abs(samples)

    return result


def compute_metric(
    posteriors: dict[str, np.ndarray],
    metric: str,
    use_combined: bool,
) -> np.ndarray:
    """Compute the requested metric from posteriors.

    Args:
        posteriors: Dict of posterior samples
        metric: One of 'strategic_sum', 'non_strategic_sum', 'difference', 'quotient'
        use_combined: If True, use combined model coefficients; else use separate models
    """
    if use_combined:
        strat_prefix = "combined_"
        ns_prefix = "combined_"
    else:
        strat_prefix = "strategic_"
        ns_prefix = "non_strategic_"

    if metric == "strategic_sum":
        return compute_sum_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
    elif metric == "non_strategic_sum":
        return compute_sum_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
    elif metric == "difference":
        strat = compute_sum_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
        ns = compute_sum_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
        return strat - ns
    elif metric == "quotient":
        strat = compute_sum_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
        ns = compute_sum_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
        # Add small epsilon to avoid division by zero
        return strat / (ns + 1e-6)
    else:
        raise ValueError(f"Unknown metric: {metric}")


def get_quartile_data(metric: str, use_combined: bool) -> tuple[list, list, list, list]:
    """Get data for all quartiles for a given metric.

    Returns:
        Tuple of (x_vals, y_means, y_lows, y_highs)
    """
    x_vals = []
    y_means = []
    y_lows = []
    y_highs = []

    for q_idx, q in enumerate(QUARTILES):
        posteriors = load_quartile_posteriors(q)
        samples = compute_metric(posteriors, metric, use_combined)

        x_vals.append(q_idx)
        y_means.append(np.mean(samples))
        y_lows.append(np.percentile(samples, 2.5))
        y_highs.append(np.percentile(samples, 97.5))

    return x_vals, y_means, y_lows, y_highs


def plot_on_axis(
    ax: plt.Axes,
    x_vals: list,
    y_means: list,
    y_lows: list,
    y_highs: list,
    color: str = "steelblue",
    show_quartile_labels: bool = True,
    show_values: bool = True,
    ylabel: str | None = None,
    title: str | None = None,
    reference_line: float | None = None,
    value_offset: tuple[int, int] = (0, 10),
    smart_label_positions: bool = False,
    markersize: int = 8,
    capsize: int = 5,
    linewidth: float = 2,
    fontsize_title: float | None = None,
    fontsize_label: float | None = None,
    fontsize_tick: float | None = None,
    fontsize_annotation: float = 8,
) -> None:
    """Plot trend with error bars on a given axis.

    Args:
        smart_label_positions: If True, position labels based on trend direction:
            - If next point is lower, put label up-right
            - If next point is higher, put label down-right
            This avoids overlaps with the trend line.
        fontsize_title: Override title font size (default: rcParams).
        fontsize_label: Override axis label font size (default: rcParams).
        fontsize_tick: Override tick label font size (default: rcParams).
        fontsize_annotation: Font size for value annotations.
    """
    if not x_vals:
        raise ValueError("No data to plot")

    # Plot with error bars
    ax.errorbar(
        x_vals,
        y_means,
        yerr=[
            np.array(y_means) - np.array(y_lows),
            np.array(y_highs) - np.array(y_means),
        ],
        color=color,
        capsize=capsize,
        linewidth=linewidth,
        marker="o",
        markersize=markersize,
    )
    ax.fill_between(x_vals, y_lows, y_highs, alpha=0.2, color=color)

    # Reference line
    if reference_line is not None:
        ax.axhline(reference_line, color="black", linestyle="--", alpha=0.5)

    # Formatting
    ax.set_xlim(-0.3, 3.3)
    tick_kwargs = {"fontsize": fontsize_tick} if fontsize_tick is not None else {}
    ax.set_xticks(range(4))
    if show_quartile_labels:
        ax.set_xticklabels(QUARTILE_LABELS, **tick_kwargs)
    else:
        ax.set_xticklabels(["Q1", "Q2", "Q3", "Q4"], **tick_kwargs)
    if fontsize_tick is not None:
        ax.tick_params(axis="y", labelsize=fontsize_tick)

    if ylabel:
        label_kwargs = (
            {"fontsize": fontsize_label} if fontsize_label is not None else {}
        )
        ax.set_ylabel(ylabel, labelpad=2, **label_kwargs)
    if title:
        title_kwargs = (
            {"fontsize": fontsize_title} if fontsize_title is not None else {}
        )
        ax.set_title(title, fontweight="bold", pad=8, **title_kwargs)

    # Value annotations
    if show_values:
        for i, (x, y) in enumerate(zip(x_vals, y_means)):
            if smart_label_positions:
                # Determine offset based on trend direction
                if i < len(y_means) - 1:
                    # Not the last point - look at next point
                    next_y = y_means[i + 1]
                    if next_y > y:
                        # Next point is higher -> put label down-right
                        offset = (5, -8)
                    else:
                        # Next point is lower -> put label up-right
                        offset = (5, 5)
                else:
                    # Last point - look at previous point
                    prev_y = y_means[i - 1]
                    if prev_y > y:
                        # Came from higher -> put label down-right
                        offset = (5, -8)
                    else:
                        # Came from lower -> put label up-right
                        offset = (5, 5)
            else:
                offset = value_offset

            ha = "left" if offset[0] > 0 else ("right" if offset[0] < 0 else "center")
            ax.annotate(
                f"{y:.2f}",
                (x, y),
                textcoords="offset points",
                xytext=offset,
                ha=ha,
                fontsize=fontsize_annotation,
            )


# =============================================================================
# Plot: 6-factor vs 12-factor comparison (2x2)
# =============================================================================


def plot_6vs12_comparison(output_path: Path) -> None:
    """Create 2x2 comparison of 6-factor vs 12-factor models.

    Layout:
    - Top row: S and NS from 12-factor model (combined)
    - Bottom row: S and NS from 6-factor models (separate)

    Shows coefficients are nearly identical regardless of fitting approach.
    """
    setup_style()

    fig, axes = plt.subplots(2, 2, figsize=(FIG_WIDTH_DOUBLE, 5.5))

    # Top-left: Strategic from 12-factor
    x, means, lows, highs = get_quartile_data("strategic_sum", use_combined=True)
    plot_on_axis(
        axes[0, 0],
        x,
        means,
        lows,
        highs,
        color=COLOR_STRATEGIC,
        show_quartile_labels=False,
        ylabel="Importance",
        title="Strategic (12-factor model)",
        value_offset=(8, 0),
    )

    # Top-right: Non-strategic from 12-factor
    x, means, lows, highs = get_quartile_data("non_strategic_sum", use_combined=True)
    plot_on_axis(
        axes[0, 1],
        x,
        means,
        lows,
        highs,
        color=COLOR_NON_STRATEGIC,
        show_quartile_labels=False,
        ylabel="Importance",
        title="Non-strategic (12-factor model)",
        value_offset=(8, 0),
    )

    # Bottom-left: Strategic from 6-factor
    x, means, lows, highs = get_quartile_data("strategic_sum", use_combined=False)
    plot_on_axis(
        axes[1, 0],
        x,
        means,
        lows,
        highs,
        color=COLOR_STRATEGIC,
        show_quartile_labels=False,
        ylabel="Importance",
        title="Strategic (6-factor model)",
        value_offset=(8, 0),
    )
    axes[1, 0].set_xlabel("Capability quartile")

    # Bottom-right: Non-strategic from 6-factor
    x, means, lows, highs = get_quartile_data("non_strategic_sum", use_combined=False)
    plot_on_axis(
        axes[1, 1],
        x,
        means,
        lows,
        highs,
        color=COLOR_NON_STRATEGIC,
        show_quartile_labels=False,
        ylabel="Importance",
        title="Non-strategic (6-factor model)",
        value_offset=(8, 0),
    )
    axes[1, 1].set_xlabel("Capability quartile")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved: {output_path}")


def get_rq1_quartile_data() -> tuple[list, list, list, list]:
    """Get RQ1 metric data for all quartiles.

    RQ1 = (A + C - B) / (2C) where:
    - A = LL(strategic) - LL(trivial)
    - B = LL(non_strategic) - LL(trivial)
    - C = LL(combined) - LL(trivial)

    Returns:
        Tuple of (x_vals, y_means, y_lows, y_highs)
    """
    x_vals = []
    y_means = []
    y_lows = []
    y_highs = []

    for q_idx, q in enumerate(QUARTILES):
        posteriors = load_quartile_posteriors(q)

        # Use pre-computed RQ1 distribution
        if "RQ1_distribution" not in posteriors:
            raise ValueError(f"Missing RQ1_distribution for {q}")
        rq1 = posteriors["RQ1_distribution"]

        x_vals.append(q_idx)
        y_means.append(np.mean(rq1))
        y_lows.append(np.percentile(rq1, 2.5))
        y_highs.append(np.percentile(rq1, 97.5))

    return x_vals, y_means, y_lows, y_highs


# =============================================================================
# Megaplot: All metrics in one figure
# =============================================================================


def plot_megaplot(output_path: Path, use_combined: bool = True) -> None:
    """Create megaplot with all RQ2 metrics.

    Layout:
    - Top row (2 plots): Strategic factors, Non-strategic factors
    - Bottom row (3 plots): Difference (S-NS), Quotient (S/NS), Log-lik (RQ1)
    """
    setup_style()

    # Create figure with 2 rows: top has 2 cols, bottom has 3 cols
    fig = plt.figure(figsize=(FIG_WIDTH_DOUBLE, 5.0))

    # Use gridspec for flexible layout
    # Top row: 2 equal-width plots
    # Bottom row: 3 equal-width plots
    gs = fig.add_gridspec(2, 6, hspace=0.45, wspace=0.5)

    # Top row: each plot spans 3 columns (so 2 plots fill 6 columns)
    ax_strategic = fig.add_subplot(gs[0, 0:3])
    ax_nonstrategic = fig.add_subplot(gs[0, 3:6])

    # Bottom row: each plot spans 2 columns (so 3 plots fill 6 columns)
    ax_difference = fig.add_subplot(gs[1, 0:2])
    ax_quotient = fig.add_subplot(gs[1, 2:4])
    ax_loglik = fig.add_subplot(gs[1, 4:6])

    # Top-left: Strategic factors
    x, means, lows, highs = get_quartile_data("strategic_sum", use_combined)
    plot_on_axis(
        ax_strategic,
        x,
        means,
        lows,
        highs,
        color=COLOR_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Sum of |coefficients|",
        title="(a) Strategic factors",
        smart_label_positions=True,
    )

    # Top-right: Non-strategic factors
    x, means, lows, highs = get_quartile_data("non_strategic_sum", use_combined)
    plot_on_axis(
        ax_nonstrategic,
        x,
        means,
        lows,
        highs,
        color=COLOR_NON_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Sum of |coefficients|",
        title="(b) Non-strategic factors",
        smart_label_positions=True,
    )

    # Bottom-left: Difference (S - NS)
    x, means, lows, highs = get_quartile_data("difference", use_combined)
    plot_on_axis(
        ax_difference,
        x,
        means,
        lows,
        highs,
        color=COLOR_COMBINED,
        show_quartile_labels=True,
        ylabel="Strategic − Non-strategic",
        title="(c) Difference",
        smart_label_positions=True,
    )

    # Bottom-center: Quotient (S / NS)
    x, means, lows, highs = get_quartile_data("quotient", use_combined)
    plot_on_axis(
        ax_quotient,
        x,
        means,
        lows,
        highs,
        color=COLOR_COMBINED,
        show_quartile_labels=True,
        ylabel="Strategic / Non-strategic",
        title="(d) Quotient",
        smart_label_positions=True,
    )

    # Bottom-right: Log-likelihood based (RQ1)
    x, means, lows, highs = get_rq1_quartile_data()
    plot_on_axis(
        ax_loglik,
        x,
        means,
        lows,
        highs,
        color=COLOR_COMBINED,
        show_quartile_labels=True,
        ylabel="Strategic contribution",
        title="(e) RQ1 approach",
        smart_label_positions=True,
        markersize=3,  # Smaller dots for tight CIs
    )
    ax_loglik.set_ylim(0, 1)
    ax_loglik.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax_loglik.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved: {output_path}")


def plot_megaplot_compact(output_path: Path, use_combined: bool = True) -> None:
    """Create compact megaplot with S, NS, and RQ1 only.

    Layout: single row with 3 plots.
    """
    setup_style()

    fig, axes = plt.subplots(1, 3, figsize=(FIG_WIDTH_DOUBLE, 2.0))

    # Font sizes scaled for 3-panel figure at paper width
    fs_title = 9
    fs_label = 9
    fs_tick = 8
    fs_annot = 6.5

    # Compact marker/line sizes
    ms = 5
    cs = 3
    lw = 1.5

    # (a) Strategic factors
    x, means, lows, highs = get_quartile_data("strategic_sum", use_combined)
    plot_on_axis(
        axes[0],
        x,
        means,
        lows,
        highs,
        color=COLOR_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Sum of |coefficients|",
        title="(a) Strategic factors",
        smart_label_positions=True,
        markersize=ms,
        capsize=cs,
        linewidth=lw,
        fontsize_title=fs_title,
        fontsize_label=fs_label,
        fontsize_tick=fs_tick,
        fontsize_annotation=fs_annot,
    )

    # (b) Non-strategic factors
    x, means, lows, highs = get_quartile_data("non_strategic_sum", use_combined)
    plot_on_axis(
        axes[1],
        x,
        means,
        lows,
        highs,
        color=COLOR_NON_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Sum of |coefficients|",
        title="(b) Non-strategic factors",
        smart_label_positions=True,
        markersize=ms,
        capsize=cs,
        linewidth=lw,
        fontsize_title=fs_title,
        fontsize_label=fs_label,
        fontsize_tick=fs_tick,
        fontsize_annotation=fs_annot,
    )

    # (c) Log-likelihood based (RQ1)
    x, means, lows, highs = get_rq1_quartile_data()
    plot_on_axis(
        axes[2],
        x,
        means,
        lows,
        highs,
        color=COLOR_COMBINED,
        show_quartile_labels=True,
        ylabel="Strategic contribution",
        title="(c) RQ1 approach",
        smart_label_positions=True,
        markersize=2,
        capsize=cs,
        linewidth=lw,
        fontsize_title=fs_title,
        fontsize_label=fs_label,
        fontsize_tick=fs_tick,
        fontsize_annotation=fs_annot,
    )
    axes[2].set_ylim(0, 1)
    axes[2].set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    axes[2].set_yticklabels(
        ["0%", "20%", "40%", "60%", "80%", "100%"], fontsize=fs_tick
    )

    fig.suptitle(
        "Effect size trends by model capability quartile",
        fontsize=11,
        fontweight="bold",
        y=1.08,
    )

    # top: room between suptitle and subplot titles; wspace: room between panels
    plt.subplots_adjust(top=0.82, wspace=0.85)

    # Nudge center panel slightly left
    pos = axes[1].get_position()
    axes[1].set_position([pos.x0 - 0.01, pos.y0, pos.width, pos.height])
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot RQ2 quartile trends")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory",
    )
    parser.add_argument(
        "--unambiguous",
        action="store_true",
        help="Use posteriors from per-quartile_unambiguous fits",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Produce compact 3-panel version (S, NS, RQ1 only)",
    )
    args = parser.parse_args()

    global POSTERIORS_DIR
    if args.unambiguous:
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile_unambiguous")

    suffix = "_unambiguous" if args.unambiguous else ""
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Megaplot: All metrics in one figure (top: S, NS; bottom: diff, quot, loglik)
    plot_megaplot(
        args.output_dir / f"plot_16_rq2_megaplot{suffix}.pdf", use_combined=True
    )

    # Compact megaplot: S, NS, RQ1 only
    plot_megaplot_compact(
        args.output_dir / f"plot_16_rq2_megaplot_compact{suffix}.pdf",
        use_combined=True,
    )

    # 6-factor vs 12-factor comparison
    plot_6vs12_comparison(args.output_dir / f"plot_16_rq2_6vs12{suffix}.pdf")


if __name__ == "__main__":
    main()
