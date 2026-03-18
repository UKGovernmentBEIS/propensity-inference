#!/usr/bin/env python3
"""Plot RQ2: Strategic sensitivity trends using AVERAGE of |coefficients|.

This is an alternative to plot_16 that uses mean (not sum) of absolute coefficients,
providing fairer comparison between parameters with different numbers of values.

Produces megaplot with: S, NS, difference, quotient (using avg), and RQ1 (unchanged).

Usage:
    uv run scripts/paper/plots/plot_16b_rq2_avg_importance.py
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


def compute_avg_abs_coefficients(
    posteriors: dict[str, np.ndarray],
    params: list[str],
    prefix: str,
) -> np.ndarray:
    """Compute AVERAGE of |coefficients| for given parameters.

    This averages across all coefficient values (categories) for all parameters,
    providing a fairer comparison between parameters with different numbers of values.

    Args:
        posteriors: Dict of posterior samples
        params: List of parameter names
        prefix: Model prefix ('strategic_', 'non_strategic_', or 'combined_')

    Returns:
        Array of mean(|coef|) samples
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

    # Stack and compute mean of absolute values
    stacked = np.stack(coef_samples, axis=0)  # shape: (n_coefs, n_samples)
    result = np.mean(np.abs(stacked), axis=0)  # shape: (n_samples,)

    return result


def compute_metric(
    posteriors: dict[str, np.ndarray],
    metric: str,
    use_combined: bool,
) -> np.ndarray:
    """Compute the requested metric from posteriors.

    Args:
        posteriors: Dict of posterior samples
        metric: One of 'strategic_avg', 'non_strategic_avg', 'difference', 'quotient'
        use_combined: If True, use combined model coefficients; else use separate models
    """
    if use_combined:
        strat_prefix = "combined_"
        ns_prefix = "combined_"
    else:
        strat_prefix = "strategic_"
        ns_prefix = "non_strategic_"

    if metric == "strategic_avg":
        return compute_avg_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
    elif metric == "non_strategic_avg":
        return compute_avg_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
    elif metric == "difference":
        strat = compute_avg_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
        ns = compute_avg_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
        return strat - ns
    elif metric == "quotient":
        strat = compute_avg_abs_coefficients(posteriors, STRATEGIC_PARAMS, strat_prefix)
        ns = compute_avg_abs_coefficients(posteriors, NON_STRATEGIC_PARAMS, ns_prefix)
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
) -> None:
    """Plot trend with error bars on a given axis.

    Args:
        smart_label_positions: If True, position labels based on trend direction:
            - If next point is lower, put label up-right
            - If next point is higher, put label down-right
            This avoids overlaps with the trend line.
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
        capsize=5,
        linewidth=2,
        marker="o",
        markersize=markersize,
    )
    ax.fill_between(x_vals, y_lows, y_highs, alpha=0.2, color=color)

    # Reference line
    if reference_line is not None:
        ax.axhline(reference_line, color="black", linestyle="--", alpha=0.5)

    # Formatting
    ax.set_xticks(range(4))
    if show_quartile_labels:
        ax.set_xticklabels(QUARTILE_LABELS)
    else:
        ax.set_xticklabels(["Q1", "Q2", "Q3", "Q4"])

    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)

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
                        offset = (8, -12)
                    else:
                        # Next point is lower -> put label up-right
                        offset = (8, 8)
                else:
                    # Last point - look at previous point
                    prev_y = y_means[i - 1]
                    if prev_y > y:
                        # Came from higher -> put label down-right
                        offset = (8, -12)
                    else:
                        # Came from lower -> put label up-right
                        offset = (8, 8)
            else:
                offset = value_offset

            ha = "left" if offset[0] > 0 else ("right" if offset[0] < 0 else "center")
            ax.annotate(
                f"{y:.2f}",
                (x, y),
                textcoords="offset points",
                xytext=offset,
                ha=ha,
                fontsize=8,
            )


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
# Megaplot: All metrics in one figure (using AVERAGE)
# =============================================================================


def plot_megaplot(output_path: Path, use_combined: bool = True) -> None:
    """Create megaplot with all RQ2 metrics using AVERAGE of |coefficients|.

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
    x, means, lows, highs = get_quartile_data("strategic_avg", use_combined)
    plot_on_axis(
        ax_strategic,
        x,
        means,
        lows,
        highs,
        color=COLOR_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Mean of |coefficients|",
        title="(a) Strategic factors",
        smart_label_positions=True,
    )

    # Top-right: Non-strategic factors
    x, means, lows, highs = get_quartile_data("non_strategic_avg", use_combined)
    plot_on_axis(
        ax_nonstrategic,
        x,
        means,
        lows,
        highs,
        color=COLOR_NON_STRATEGIC,
        show_quartile_labels=True,
        ylabel="Mean of |coefficients|",
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

    # Bottom-right: Log-likelihood based (RQ1) - unchanged
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


def main():
    parser = argparse.ArgumentParser(description="Plot RQ2 quartile trends (avg)")
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
    args = parser.parse_args()

    global POSTERIORS_DIR
    if args.unambiguous:
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile_unambiguous")

    suffix = "_unambiguous" if args.unambiguous else ""
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Megaplot: All metrics using AVERAGE of |coefficients|
    plot_megaplot(
        args.output_dir / f"plot_16b_rq2_megaplot_avg{suffix}.pdf", use_combined=True
    )


if __name__ == "__main__":
    main()
