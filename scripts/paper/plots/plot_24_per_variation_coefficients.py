#!/usr/bin/env python3
"""Plot 24: Coefficient plots for per-variation pooled fits.

Shows all 12 parameters from the combined model, with each variation as a different bar
within each parameter subplot.

This is the per-variation counterpart to plot_17 (pooled coefficients by quartile).

Output:
    - figures/plot_24_per_variation_coefficients.pdf (combined mode)
    - figures/plot_24_per_variation_coefficients_{param}.pdf (split mode)

Usage:
    # All variations, combined figure
    uv run scripts/paper/plots/plot_24_per_variation_coefficients.py

    # Split into separate files per parameter
    uv run scripts/paper/plots/plot_24_per_variation_coefficients.py --split

    # Only variations with meaningful signal (P(C>0) > 0.9)
    uv run scripts/paper/plots/plot_24_per_variation_coefficients.py --good-only
"""

import json
import logging
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from lib.paper_style import (
    NON_STRATEGIC_PARAMS,
    SLUG_TO_VARIATION,
    STRATEGIC_PARAMS,
    VARIATION_ORDER,
    get_category_display_name,
    get_param_display_name,
    get_sorted_categories,
    get_variation_color,
    get_variation_display_name,
    normalize_category,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-variation")
OUTPUT_DIR = Path("paper_cache/figures")

# Parameter ordering for the plot (strategic on left, non-strategic on right)
# Interleave: strategic in left 2 cols, non-strategic in right 2 cols
# Row 0: S0, S1, NS0, NS1
# Row 1: S2, S3, NS2, NS3
# Row 2: S4, S5, NS4, NS5
PARAM_ORDER = []
for row in range(3):
    PARAM_ORDER.append(STRATEGIC_PARAMS[row * 2])
    PARAM_ORDER.append(STRATEGIC_PARAMS[row * 2 + 1])
    PARAM_ORDER.append(NON_STRATEGIC_PARAMS[row * 2])
    PARAM_ORDER.append(NON_STRATEGIC_PARAMS[row * 2 + 1])

# Parameters that use reference-point normalization (binary/trinary)
# Maps param -> reference category (which is omitted from the plot)
REFERENCE_POINT_PARAMS: dict[str, str] = {
    "goal_present": "false",
    "goal_conflict": "false",
    "action_oversight": "none",
    "action_efficacy_binary": "not_effective",
    "filler_richness": "minimal",
}


def _get_variation_color_by_slug(variation_slug: str) -> str:
    """Get color for a variation by its slug."""
    if variation_slug not in SLUG_TO_VARIATION:
        raise ValueError(f"Unknown variation slug: {variation_slug!r}")
    scenario, variation = SLUG_TO_VARIATION[variation_slug]
    return get_variation_color(scenario, variation)


def _get_variation_name(variation_slug: str) -> str:
    """Get display name for a variation slug."""
    if variation_slug not in SLUG_TO_VARIATION:
        raise ValueError(f"Unknown variation slug: {variation_slug!r}")
    key = SLUG_TO_VARIATION[variation_slug]
    return get_variation_display_name(key[0], key[1])


def load_variation_posteriors(variation_slug: str) -> dict[str, np.ndarray]:
    """Load posteriors for a specific variation."""
    path = POSTERIORS_DIR / f"{variation_slug}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def load_variation_summary(variation_slug: str) -> dict:
    """Load summary JSON for a variation."""
    path = POSTERIORS_DIR / f"{variation_slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing summary file: {path}")
    with open(path) as f:
        return json.load(f)


def get_variations_implementing_param(
    param: str,
    variation_slugs: list[str],
    all_summaries: dict[str, dict],
) -> list[str]:
    """Filter to variations that implement a given parameter."""
    result = []
    for slug in variation_slugs:
        summary = all_summaries.get(slug)
        if summary is None:
            continue
        implemented = summary.get("implemented_params", [])
        if param in implemented:
            result.append(slug)
    return result


def get_available_variations() -> list[str]:
    """Get list of available variation slugs with posteriors."""
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")
    slugs = [p.stem for p in POSTERIORS_DIR.glob("*.npz")]
    if not slugs:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")

    # Sort by VARIATION_ORDER
    def get_order(slug: str) -> int:
        if slug not in SLUG_TO_VARIATION:
            raise ValueError(f"Unknown variation slug: {slug!r}")
        key = SLUG_TO_VARIATION[slug]
        if key not in VARIATION_ORDER:
            raise ValueError(f"Variation {key} not in VARIATION_ORDER")
        return VARIATION_ORDER.index(key)

    return sorted(slugs, key=get_order)


def get_good_variations() -> list[str]:
    """Get variations where parameters help (P(C>0) > 0.9)."""
    good = []
    for slug in get_available_variations():
        posteriors = load_variation_posteriors(slug)
        C = posteriors.get("C_distribution")
        if C is not None and (C > 0).mean() > 0.9:
            good.append(slug)
    if not good:
        raise ValueError("No variations with P(C>0) > 0.9 found")
    return good


def get_param_categories(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    param: str,
) -> list[str]:
    """Get all categories for a parameter across all variations, sorted by expected order."""
    categories = set()
    for slug, posteriors in all_posteriors.items():
        for key in posteriors.keys():
            if (
                key.startswith(f"combined_{param}_effects[")
                and "constrained" not in key
            ):
                cat = key.split("[")[1].rstrip("]")
                categories.add(normalize_category(param, cat))
    return get_sorted_categories(param, list(categories))


def get_posterior_key(
    param: str, cat: str, posteriors: dict[str, np.ndarray]
) -> str | None:
    """Get the posterior key for a parameter category, handling aliases."""
    key = f"combined_{param}_effects[{cat}]"
    if key in posteriors:
        return key
    # Try aliases (e.g., true/false for action_efficacy_binary)
    if param == "action_efficacy_binary":
        alias = (
            "true" if cat == "effective" else "false" if cat == "not_effective" else cat
        )
        key = f"combined_{param}_effects[{alias}]"
        if key in posteriors:
            return key
    return None


def plot_parameter_subplot(
    ax: plt.Axes,
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    variation_slugs: list[str],
    all_summaries: dict[str, dict],
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
    show_legend: bool = False,
    enlarged: bool = False,
) -> None:
    """Plot one parameter subplot with all variations.

    Args:
        ax: Matplotlib axes
        param: Parameter name
        all_posteriors: Dict mapping variation_slug -> posteriors dict
        variation_slugs: Ordered list of variation slugs to plot
        all_summaries: Dict mapping variation_slug -> summary dict (for implemented_params)
        show_ylabel: Whether to show the y-axis label
        show_ytick_labels: Whether to show the y-axis tick labels
        show_legend: Whether to show legend on this subplot
        enlarged: If True, use larger fonts (for split mode)
    """
    # Filter to only variations that implement this parameter
    variation_slugs = get_variations_implementing_param(
        param, variation_slugs, all_summaries
    )

    if not variation_slugs:
        raise ValueError(f"No variations implement parameter {param!r}")

    categories = get_param_categories(all_posteriors, param)

    if not categories:
        raise ValueError(f"No categories found for parameter {param!r}")

    # Check if this parameter uses reference-point normalization
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        # Remove reference category from display
        display_categories = [c for c in categories if c != reference_cat]
    else:
        display_categories = categories

    n_categories = len(display_categories)
    n_variations = len(variation_slugs)

    # Bar positioning - keep spacing constant, but narrow bars for few-category params
    bar_spacing = 0.8 / n_variations
    # For few categories, make bars narrower to create visible gaps between variations
    if n_categories == 1:
        x_pos = np.array([1.0])  # Center in visual width of 3
        bar_width = bar_spacing * 0.7
    elif n_categories == 2:
        # Spread out the two categories, symmetric around center (1.0) in visual width of 3
        x_pos = np.array([0.25, 1.75])
        bar_width = bar_spacing * 0.7
    elif n_categories == 3:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.7
    else:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.9  # 4+ categories: nearly touching

    # Plot each variation
    for v_idx, variation_slug in enumerate(variation_slugs):
        posteriors = all_posteriors[variation_slug]
        color = _get_variation_color_by_slug(variation_slug)
        x_offset = (v_idx - (n_variations - 1) / 2) * bar_spacing

        # Get reference samples if using reference-point normalization
        ref_samples = None
        if use_reference_point:
            ref_key = get_posterior_key(param, reference_cat, posteriors)
            if ref_key:
                ref_samples = posteriors[ref_key]

        for cat_idx, cat in enumerate(display_categories):
            key = get_posterior_key(param, cat, posteriors)
            if key is None:
                # Some variations don't have all categories for a parameter
                # (e.g. PP variations lack threat[none]). Skip gracefully.
                continue

            log_odds_samples = posteriors[key]

            # If using reference point, compute difference from reference
            if use_reference_point and ref_samples is not None:
                # Difference in log-odds space = log(odds_ratio between categories)
                log_odds_samples = log_odds_samples - ref_samples

            # Compute statistics in log-odds space
            log_odds_mean = np.mean(log_odds_samples)
            log_odds_lower = np.percentile(log_odds_samples, 2.5)
            log_odds_upper = np.percentile(log_odds_samples, 97.5)

            # Convert to odds
            odds_mean = np.exp(log_odds_mean)
            odds_lower = np.exp(log_odds_lower)
            odds_upper = np.exp(log_odds_upper)

            x_position = x_pos[cat_idx] + x_offset

            # Bar extends from baseline (1) to odds_mean
            bar_height = odds_mean - 1
            ax.bar(
                x_position,
                bar_height,
                width=bar_width,
                color=color,
                alpha=0.7,
                bottom=1,
                label=_get_variation_name(variation_slug) if cat_idx == 0 else None,
            )

            # Error bars (95% ETI)
            err_lower = odds_mean - odds_lower
            err_upper = odds_upper - odds_mean
            ax.errorbar(
                x_position,
                odds_mean,
                yerr=[[err_lower], [err_upper]],
                color="black",
                capsize=1 if n_variations <= 6 else 0.5,
                capthick=0.5 if n_variations <= 6 else 0.3,
                linewidth=0.5 if n_variations <= 6 else 0.3,
                linestyle="none",
            )

    # Formatting - log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=1.0, zorder=10)
    ax.set_xticks(x_pos)

    # Y-axis ticks - disable minor ticks and auto-formatting
    tick_values = [1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2]
    tick_labels = ["1:2", "1:1.5", "1:1.25", "1:1", "1.25:1", "1.5:1", "2:1"]
    # Always set tick locations (needed for grid lines)
    ax.yaxis.set_major_locator(FixedLocator(tick_values))
    ax.yaxis.set_minor_locator(NullLocator())

    tick_fontsize = 8 if not enlarged else 9
    if show_ytick_labels:
        ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))
        ax.tick_params(axis="y", labelsize=tick_fontsize)
        # Make y-tick labels bold
        for label in ax.yaxis.get_ticklabels():
            label.set_fontweight("bold")
    else:
        # Hide tick marks and labels but keep locator for grid lines
        ax.yaxis.set_major_formatter(FixedFormatter([""] * len(tick_labels)))
        ax.tick_params(axis="y", left=False, labelleft=False)

    # Y-axis limits
    ax.set_ylim(1 / 2.5, 2.5)

    # Category labels
    if use_reference_point:
        # For reference-point params, show "ref → cat" style labels
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    # Use horizontal labels for few categories, rotated for many
    label_fontsize = 7.5 if not enlarged else 9
    if n_categories <= 2:
        ax.set_xticklabels(
            cat_labels,
            rotation=0,
            ha="center",
            fontsize=label_fontsize,
            fontfamily="sans-serif",
        )
    else:
        ax.set_xticklabels(
            cat_labels,
            rotation=35,
            ha="right",
            fontsize=label_fontsize,
            fontfamily="sans-serif",
        )

    # Set x-axis limits - use minimum visual width of 3 so binary params don't get overly wide bars
    min_visual_categories = 3
    visual_width = max(n_categories, min_visual_categories)
    ax.set_xlim(-0.5, visual_width - 0.5)

    if show_ylabel:
        ylabel_fontsize = 9 if not enlarged else 11
        ax.set_ylabel(
            r"$\bf{Odds\ ratio}$" + "\n(unsanctioned : not)",
            fontsize=ylabel_fontsize,
        )

    # Title (strategic/non-strategic indicated by position, not suffix)
    title_fontsize = 12 if not enlarged else 14
    ax.set_title(
        get_param_display_name(param),
        fontsize=title_fontsize,
        fontweight="bold",
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)

    if show_legend:
        ax.legend(
            loc="upper right",
            fontsize=5 if not enlarged else 8,
            ncol=2 if n_variations > 6 else 1,
        )


def create_combined_figure(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    variation_slugs: list[str],
    all_summaries: dict[str, dict],
    output_path: Path,
    title_suffix: str = "",
) -> None:
    """Create single figure with 3x4 grid of all parameters."""
    n_rows = 3
    fig = plt.figure(figsize=(18, 12))

    # Left GridSpec for strategic factors (columns 0-1)
    gs_left = GridSpec(
        n_rows,
        2,
        figure=fig,
        left=0.05,
        right=0.48,  # Left half with margin
        hspace=0.36,
        wspace=0.08,
    )
    # Right GridSpec for non-strategic factors (columns 2-3)
    gs_right = GridSpec(
        n_rows,
        2,
        figure=fig,
        left=0.52,
        right=0.95,  # Right half with margin
        hspace=0.36,
        wspace=0.08,
    )

    # Plot each parameter in the specified order
    # Left 2 columns: strategic, Right 2 columns: non-strategic
    n_cols = 4  # Total columns in logical layout
    for idx, param in enumerate(PARAM_ORDER):
        row = idx // n_cols
        col = idx % n_cols

        # Use appropriate GridSpec based on column
        if col < 2:
            ax = fig.add_subplot(gs_left[row, col])
        else:
            ax = fig.add_subplot(gs_right[row, col - 2])

        # Only show y-axis label and tick labels on leftmost column of each group
        show_ylabel = col == 0
        show_ytick_labels = col == 0
        plot_parameter_subplot(
            ax,
            param,
            all_posteriors,
            variation_slugs,
            all_summaries,
            show_ylabel=show_ylabel,
            show_ytick_labels=show_ytick_labels,
        )

    # Create legend showing variation colors
    legend_handles = []
    for slug in variation_slugs:
        color = _get_variation_color_by_slug(slug)
        handle = plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.7)
        legend_handles.append((handle, _get_variation_name(slug)))

    # Split legend into columns
    n_legend_cols = min(6, len(legend_handles))
    fig.legend(
        [h for h, _ in legend_handles],
        [n for _, n in legend_handles],
        loc="lower center",
        ncol=n_legend_cols,
        fontsize=10,
        bbox_to_anchor=(0.5, -0.02),
    )

    fig.suptitle(
        f"Effects of environmental changes on unsanctioned behaviour by environment{title_suffix}",
        fontsize=19,
        fontweight="bold",
        y=0.95,
    )

    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def create_split_figures(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    variation_slugs: list[str],
    all_summaries: dict[str, dict],
    output_dir: Path,
) -> None:
    """Create separate figure for each parameter."""
    for param in PARAM_ORDER:
        fig, ax = plt.subplots(figsize=(12, 6))

        plot_parameter_subplot(
            ax,
            param,
            all_posteriors,
            variation_slugs,
            all_summaries,
            show_ylabel=True,
            show_ytick_labels=True,
            show_legend=True,
            enlarged=True,
        )

        # Title
        is_strategic = param in STRATEGIC_PARAMS
        title_suffix = " (Strategic)" if is_strategic else " (Non-Strategic)"
        ax.set_title(
            f"{get_param_display_name(param)}{title_suffix}\n"
            f"Per-Variation Pooled Coefficients ({len(variation_slugs)} variations)",
            fontsize=14,
            fontweight="bold",
        )

        output_path = output_dir / f"plot_24_per_variation_coefficients_{param}.pdf"
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        logger.info(f"Saved: {output_path}")


def main(
    split: bool = False,
    good_only: bool = False,
):
    """Generate per-variation coefficient plots.

    Args:
        split: If True, create separate PNG for each parameter
        good_only: If True, only include variations with P(C>0) > 0.9
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get available variations
    if good_only:
        variation_slugs = get_good_variations()
        logger.info(
            f"Using {len(variation_slugs)} variations with good signal: {variation_slugs}"
        )
    else:
        variation_slugs = get_available_variations()

    logger.info(f"Loading posteriors for {len(variation_slugs)} variations...")

    # Load all posteriors and summaries
    all_posteriors = {}
    all_summaries = {}
    for slug in variation_slugs:
        all_posteriors[slug] = load_variation_posteriors(slug)
        all_summaries[slug] = load_variation_summary(slug)

    logger.info(f"Loaded {len(variation_slugs)} variation posteriors")

    # Generate plots
    if split:
        create_split_figures(all_posteriors, variation_slugs, all_summaries, OUTPUT_DIR)
    else:
        suffix = "_good" if good_only else ""
        title_suffix = "\n(Only variations with P(C>0) > 0.9)" if good_only else ""
        output_path = OUTPUT_DIR / f"plot_24_per_variation_coefficients{suffix}.pdf"
        create_combined_figure(
            all_posteriors, variation_slugs, all_summaries, output_path, title_suffix
        )

    # Print summary
    print("\n=== Per-Variation Coefficient Summary ===")
    print(f"Variations plotted: {len(variation_slugs)}")
    for slug in variation_slugs:
        summary = load_variation_summary(slug)
        posteriors = all_posteriors.get(slug)
        if summary and posteriors is not None:
            C = posteriors.get("C_distribution")
            p_c_pos = (C > 0).mean() if C is not None else 0
            n_samples = summary.get("n_samples", 0)
            print(
                f"  {_get_variation_name(slug):<25} P(C>0)={p_c_pos:.3f}, n={n_samples}"
            )


if __name__ == "__main__":
    fire.Fire(main)
