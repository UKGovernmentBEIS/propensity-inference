#!/usr/bin/env python3
"""Plot 29: Puffin-style coefficient plots for eval awareness fits.

Shows the effect of 12 scenario parameters on unprompted evaluation awareness
for the three Claude 4.5 models (Opus, Sonnet, Haiku).

Output:
    - figures/plot_29_eval_awareness_coefficients.pdf

Usage:
    uv run scripts/paper/plots/plot_29_eval_awareness_coefficients.py
"""

import logging
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from lib.paper_style import (
    NON_STRATEGIC_PARAMS,
    STRATEGIC_PARAMS,
    get_category_display_name,
    get_param_display_name,
    get_sorted_categories,
    normalize_category,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model_eval_awareness/")
OUTPUT_DIR = Path("paper_cache/figures")

# Claude 4.5 models ordered by capability (Opus > Sonnet > Haiku)
MODEL_SLUGS = [
    "anthropic_claude-opus-4-5-20251101",
    "anthropic_claude-sonnet-4-5-20250929",
    "anthropic_claude-haiku-4-5-20251001",
]
MODEL_LABELS = ["Opus 4.5", "Sonnet 4.5", "Haiku 4.5"]
# Anthropic-themed warm palette with clear hue/darkness differences
MODEL_COLORS = ["#D4714E", "#E8A87C", "#F5D0B3"]  # dark coral, peach, light sand

# Parameter ordering for the plot (strategic on left, non-strategic on right)
# Interleave: strategic in left 2 cols, non-strategic in right 2 cols
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


def load_posteriors(path: Path) -> dict[str, np.ndarray]:
    """Load posteriors from an npz file."""
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def get_param_categories(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    param: str,
) -> list[str]:
    """Get all categories for a parameter across all posteriors, sorted by expected order."""
    categories = set()
    for posteriors in all_posteriors.values():
        for key in posteriors.keys():
            if (
                key.startswith(f"combined_{param}_effects[")
                and "constrained" not in key
            ):
                cat = key.split("[")[1].rstrip("]")
                categories.add(normalize_category(param, cat))
    if not categories:
        raise ValueError(f"No categories found for parameter {param!r}")
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


def _get_bar_positions(
    n_categories: int,
    n_groups: int,
    bar_spacing: float,
) -> tuple[np.ndarray, float]:
    """Compute x positions and bar width for given number of categories and groups."""
    if n_categories == 1:
        x_pos = np.array([1.0])
        bar_width = bar_spacing * 0.7
    elif n_categories == 2:
        x_pos = np.array([0.25, 1.75])
        bar_width = bar_spacing * 0.7
    elif n_categories == 3:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.7
    else:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.85 if n_groups > 1 else bar_spacing * 0.6
    return x_pos, bar_width


def plot_parameter_subplot(
    ax: plt.Axes,
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    group_keys: list[str],
    group_colors: list[str],
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
) -> None:
    """Plot one parameter subplot with bars for each group."""
    categories = get_param_categories(all_posteriors, param)

    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
    else:
        display_categories = categories

    n_categories = len(display_categories)
    n_groups = len(group_keys)
    bar_spacing = 0.8 / n_groups
    x_pos, bar_width = _get_bar_positions(n_categories, n_groups, bar_spacing)

    # Draw bars
    for g_idx, (group_key, color) in enumerate(zip(group_keys, group_colors)):
        posteriors = all_posteriors[group_key]
        x_offset = (g_idx - (n_groups - 1) / 2) * bar_spacing

        ref_samples = None
        if use_reference_point:
            ref_key = get_posterior_key(param, reference_cat, posteriors)
            if ref_key:
                ref_samples = posteriors[ref_key]

        for cat_idx, cat in enumerate(display_categories):
            key = get_posterior_key(param, cat, posteriors)
            if key is None:
                raise ValueError(
                    f"No posterior key found for param={param!r}, cat={cat!r}, "
                    f"group={group_key!r}"
                )

            log_odds_samples = posteriors[key]
            if use_reference_point and ref_samples is not None:
                log_odds_samples = log_odds_samples - ref_samples

            log_odds_mean = np.mean(log_odds_samples)
            log_odds_lower = np.percentile(log_odds_samples, 2.5)
            log_odds_upper = np.percentile(log_odds_samples, 97.5)

            odds_mean = np.exp(log_odds_mean)
            odds_lower = np.exp(log_odds_lower)
            odds_upper = np.exp(log_odds_upper)

            x_position = x_pos[cat_idx] + x_offset
            bar_height = odds_mean - 1
            ax.bar(
                x_position,
                bar_height,
                width=bar_width,
                color=color,
                alpha=0.7,
                bottom=1,
            )

            err_lower = odds_mean - odds_lower
            err_upper = odds_upper - odds_mean
            ax.errorbar(
                x_position,
                odds_mean,
                yerr=[[err_lower], [err_upper]],
                color="black",
                capsize=1,
                capthick=0.5,
                linewidth=0.5,
                linestyle="none",
            )

    # Formatting - log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=1.0, zorder=10)
    ax.set_xticks(x_pos)

    # Y-axis ticks
    tick_values = [1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2]
    tick_labels = ["1:2", "1:1.5", "1:1.25", "1:1", "1.25:1", "1.5:1", "2:1"]
    ax.yaxis.set_major_locator(FixedLocator(tick_values))
    ax.yaxis.set_minor_locator(NullLocator())
    if show_ytick_labels:
        ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))
        ax.tick_params(axis="y", labelsize=10)
        for label in ax.yaxis.get_ticklabels():
            label.set_fontweight("bold")
    else:
        ax.yaxis.set_major_formatter(FixedFormatter([""] * len(tick_labels)))
        ax.tick_params(axis="y", left=False, labelleft=False)

    # Y-axis limits
    ax.set_ylim(1 / 2, 2.5)

    # Category labels
    if use_reference_point:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    if n_categories <= 3:
        ax.set_xticklabels(
            cat_labels, rotation=0, ha="center", fontsize=11, fontfamily="sans-serif"
        )
    elif n_categories >= 8:
        ax.set_xticklabels(
            cat_labels, rotation=25, ha="right", fontsize=8.5, fontfamily="sans-serif"
        )
    else:
        ax.set_xticklabels(
            cat_labels, rotation=25, ha="right", fontsize=10, fontfamily="sans-serif"
        )

    # Shift tick labels: upward for all, plus progressive rightward for >= 5 categories
    from matplotlib.transforms import ScaledTranslation

    fig = ax.get_figure()
    dy_pts = 1  # positive = closer to plot
    if n_categories >= 5:
        for i, label in enumerate(ax.xaxis.get_ticklabels()):
            step = 1.8 if n_categories >= 8 else 3.7
            dx_pts = i * step
            # Extra nudge for specific labels that need more spacing
            label_text = label.get_text()
            if label_text in (
                "Not Visible",
                "Consider Context",
            ) or label_text.startswith("Avoid Misalign"):
                dx_pts += 10.0
            offset = ScaledTranslation(dx_pts / 72, dy_pts / 72, fig.dpi_scale_trans)
            label.set_transform(label.get_transform() + offset)
    else:
        for label in ax.xaxis.get_ticklabels():
            offset = ScaledTranslation(0, dy_pts / 72, fig.dpi_scale_trans)
            label.set_transform(label.get_transform() + offset)

    # Set x-axis limits
    min_visual_categories = 3
    visual_width = max(n_categories, min_visual_categories)
    ax.set_xlim(-0.5, visual_width - 0.5)

    if show_ylabel:
        ax.set_ylabel(
            r"$\bf{Odds\ ratio}$" + "\n(eval-aware : not)",
            fontsize=11,
        )

    ax.set_title(
        get_param_display_name(param),
        fontsize=15,
        fontweight="bold",
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def main():
    """Generate eval awareness coefficient plot for Claude 4.5 family."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_posteriors = {}
    for slug in MODEL_SLUGS:
        all_posteriors[slug] = load_posteriors(POSTERIORS_DIR / f"{slug}.npz")

    title = (
        "Effects of environmental changes on unprompted evaluation awareness"
        " (Claude 4.5 family)"
    )

    # Create figure with 3x4 grid for 12 parameters
    n_rows = 3
    fig = plt.figure(figsize=(18, 12))

    # Left GridSpec for strategic factors (columns 0-1)
    gs_left = GridSpec(
        n_rows,
        2,
        figure=fig,
        left=0.05,
        right=0.48,
        bottom=0.14,
        hspace=0.36,
        wspace=0.08,
    )
    # Right GridSpec for non-strategic factors (columns 2-3)
    gs_right = GridSpec(
        n_rows,
        2,
        figure=fig,
        left=0.52,
        right=0.95,
        bottom=0.14,
        hspace=0.36,
        wspace=0.08,
    )

    # Plot each parameter in the specified order
    all_axes = []
    n_cols = 4
    for idx, param in enumerate(PARAM_ORDER):
        row = idx // n_cols
        col = idx % n_cols

        if col < 2:
            ax = fig.add_subplot(gs_left[row, col])
        else:
            ax = fig.add_subplot(gs_right[row, col - 2])
        all_axes.append((row, col, ax))

        show_ylabel = col == 0
        show_ytick_labels = col == 0
        plot_parameter_subplot(
            ax,
            param,
            all_posteriors,
            MODEL_SLUGS,
            MODEL_COLORS,
            show_ylabel,
            show_ytick_labels,
        )

    # Nudge middle row (row 1) and bottom row (row 2) down slightly
    for row, col, ax in all_axes:
        if row == 1:
            pos = ax.get_position()
            ax.set_position([pos.x0, pos.y0 - 0.01, pos.width, pos.height])
        elif row == 2:
            pos = ax.get_position()
            ax.set_position([pos.x0, pos.y0 - 0.01, pos.width, pos.height])

    # Create legend
    legend_handles = []
    for color, label in zip(MODEL_COLORS, MODEL_LABELS):
        handle = plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.7)
        legend_handles.append((handle, label))

    fig.legend(
        [h for h, _ in legend_handles],
        [n for _, n in legend_handles],
        loc="lower center",
        ncol=3,
        fontsize=14,
        bbox_to_anchor=(0.5, 0.02),
    )

    # Add title
    fig.suptitle(
        title,
        fontsize=19,
        fontweight="bold",
        y=0.95,
    )

    output_path = OUTPUT_DIR / "plot_29_eval_awareness_coefficients.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    logger.info(f"Saved: {output_path}")


if __name__ == "__main__":
    fire.Fire(main)
