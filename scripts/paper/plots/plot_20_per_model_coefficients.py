#!/usr/bin/env python3
"""Plot 20: Coefficient plots for per-model pooled fits.

Shows all 12 parameters from the combined model, with each model as a different bar
within each parameter subplot. Layout matches plot_17 style.

Output:
    - figures/plot_20_per_model_coefficients.pdf (all parameters)
    - figures/plot_20_{param}.pdf (single parameter mode)

Usage:
    # All parameters in 3x4 grid
    uv run scripts/paper/plots/plot_20_per_model_coefficients.py

    # Single parameter, full-sized
    uv run scripts/paper/plots/plot_20_per_model_coefficients.py --param goal_conflict

    # Generate all single-parameter plots
    uv run scripts/paper/plots/plot_20_per_model_coefficients.py --all-params
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
    PROVIDER_COLORS,
    STRATEGIC_PARAMS,
    get_category_display_name,
    get_model_color,
    get_model_display_name,
    get_param_display_name,
    get_sorted_categories,
    normalize_category,
    sort_models_by_release,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model")
OUTPUT_DIR = Path("paper_cache/figures")

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


def load_model_posteriors(model_slug: str) -> dict[str, np.ndarray]:
    """Load posteriors for a specific model."""
    path = POSTERIORS_DIR / f"{model_slug}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def load_model_summary(model_slug: str) -> dict | None:
    """Load summary JSON for a model."""
    path = POSTERIORS_DIR / f"{model_slug}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def get_available_models() -> list[str]:
    """Get list of available model slugs with posteriors."""
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")
    slugs = sorted([p.stem for p in POSTERIORS_DIR.glob("*.npz")])
    if not slugs:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")
    return slugs


def slug_to_model_id(slug: str) -> str:
    """Convert model slug back to API model ID.

    Handles models with multiple path components like openrouter/google/gemini-2.5-pro.
    """
    # Handle openrouter models with nested paths
    if slug.startswith("openrouter_google_"):
        return "openrouter/google/" + slug[len("openrouter_google_") :]
    if slug.startswith("openrouter_meta-llama_"):
        return "openrouter/meta-llama/" + slug[len("openrouter_meta-llama_") :]
    if slug.startswith("openrouter_openai_"):
        return "openrouter/openai/" + slug[len("openrouter_openai_") :]
    # Standard single-level conversion
    if "_" in slug:
        parts = slug.split("_", 1)
        return f"{parts[0]}/{parts[1]}"
    return slug


def get_param_categories(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    param: str,
) -> list[str]:
    """Get all categories for a parameter across all models, sorted by expected order."""
    categories = set()
    for model_slug, posteriors in all_posteriors.items():
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


def plot_parameter_subplot(
    ax: plt.Axes,
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
) -> None:
    """Plot one parameter subplot with all models.

    Args:
        ax: Matplotlib axes
        param: Parameter name
        all_posteriors: Dict mapping model_slug -> posteriors dict
        model_slugs: Ordered list of model slugs to plot
        show_ylabel: Whether to show the y-axis label
        show_ytick_labels: Whether to show the y-axis tick labels
    """
    categories = get_param_categories(all_posteriors, param)

    # Check if this parameter uses reference-point normalization
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
    else:
        display_categories = categories

    n_categories = len(display_categories)
    n_models = len(model_slugs)

    # Bar positioning - match plot_17 style
    bar_spacing = 0.8 / n_models
    if n_categories == 1:
        x_pos = np.array([1.0])  # Center in visual width of 3
        bar_width = bar_spacing * 0.7
    elif n_categories == 2:
        x_pos = np.array([0.25, 1.75])
        bar_width = bar_spacing * 0.7
    elif n_categories == 3:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.7
    else:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.9  # 4+ categories: nearly touching

    # Plot each model
    for m_idx, model_slug in enumerate(model_slugs):
        posteriors = all_posteriors[model_slug]
        model_id = slug_to_model_id(model_slug)
        color = get_model_color(model_id)
        x_offset = (m_idx - (n_models - 1) / 2) * bar_spacing

        # Get reference samples if using reference-point normalization
        ref_samples = None
        if use_reference_point:
            ref_key = get_posterior_key(param, reference_cat, posteriors)
            if ref_key:
                ref_samples = posteriors[ref_key]

        for cat_idx, cat in enumerate(display_categories):
            key = get_posterior_key(param, cat, posteriors)
            if key is None:
                raise ValueError(
                    f"No posterior key found for param={param!r}, cat={cat!r}, model={model_slug!r}"
                )

            log_odds_samples = posteriors[key]

            # If using reference point, compute difference from reference
            if use_reference_point and ref_samples is not None:
                log_odds_samples = log_odds_samples - ref_samples

            # Compute statistics in log-odds space
            log_odds_mean = np.mean(log_odds_samples)
            log_odds_lower = np.percentile(log_odds_samples, 2.5)
            log_odds_upper = np.percentile(log_odds_samples, 97.5)

            # Convert to odds ratio
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
                edgecolor="none",
                linewidth=0,
                bottom=1,
            )

            # Error bars (95% ETI)
            err_lower = odds_mean - odds_lower
            err_upper = odds_upper - odds_mean
            ax.errorbar(
                x_position,
                odds_mean,
                yerr=[[err_lower], [err_upper]],
                color="black",
                capsize=0.5 if n_models > 10 else 1,
                capthick=0.3 if n_models > 10 else 0.5,
                linewidth=0.3 if n_models > 10 else 0.5,
                linestyle="none",
            )

    # Formatting - log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=1.0, zorder=10)
    ax.set_xticks(x_pos)

    # Y-axis ticks - match plot_17 style
    tick_values = [1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2]
    tick_labels = ["1:2", "1:1.5", "1:1.25", "1:1", "1.25:1", "1.5:1", "2:1"]
    ax.yaxis.set_major_locator(FixedLocator(tick_values))
    ax.yaxis.set_minor_locator(NullLocator())
    if show_ytick_labels:
        ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))
        ax.tick_params(axis="y", labelsize=8)
        for label in ax.yaxis.get_ticklabels():
            label.set_fontweight("bold")
    else:
        ax.yaxis.set_major_formatter(FixedFormatter([""] * len(tick_labels)))
        ax.tick_params(axis="y", left=False, labelleft=False)

    # Y-axis limits: 1:2.5 to 2.5:1
    ax.set_ylim(1 / 2.5, 2.5)

    # Category labels
    if use_reference_point:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    # Use horizontal labels for few categories, rotated for many
    if n_categories <= 2:
        ax.set_xticklabels(
            cat_labels, rotation=0, ha="center", fontsize=7.5, fontfamily="sans-serif"
        )
    else:
        ax.set_xticklabels(
            cat_labels, rotation=35, ha="right", fontsize=7.5, fontfamily="sans-serif"
        )

    # Set x-axis limits
    min_visual_categories = 3
    visual_width = max(n_categories, min_visual_categories)
    ax.set_xlim(-0.5, visual_width - 0.5)

    if show_ylabel:
        ax.set_ylabel(
            r"$\bf{Odds\ ratio}$" + "\n(unsanctioned : not)",
            fontsize=9,
        )

    # Title (no S/NS suffix)
    ax.set_title(
        get_param_display_name(param),
        fontsize=12,
        fontweight="bold",
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def plot_single_parameter(
    ax: plt.Axes,
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    y_ticks: list[tuple[float, str]] | None = None,
    y_lim: tuple[float, float] | None = None,
) -> None:
    """Plot a single parameter with enlarged styling for standalone figure.

    Args:
        ax: Matplotlib axes
        param: Parameter name
        all_posteriors: Dict mapping model_slug -> posteriors dict
        model_slugs: Ordered list of model slugs to plot
        y_ticks: Optional custom y-axis ticks as list of (value, label) tuples
        y_lim: Optional custom y-axis limits as (min, max)
    """
    categories = get_param_categories(all_posteriors, param)

    # Check if this parameter uses reference-point normalization
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
    else:
        display_categories = categories

    n_categories = len(display_categories)
    n_models = len(model_slugs)

    # Bar positioning - match plot_17 style
    bar_spacing = 0.8 / n_models
    if n_categories == 1:
        x_pos = np.array([0.0])  # Center in visual width of 3
        bar_width = bar_spacing * 0.7
    elif n_categories == 2:
        x_pos = np.array([0.0, 1.0])
        bar_width = bar_spacing * 0.7
    elif n_categories == 3:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.7
    else:
        x_pos = np.arange(n_categories)
        bar_width = bar_spacing * 0.9  # 4+ categories: nearly touching

    # Plot each model
    for m_idx, model_slug in enumerate(model_slugs):
        posteriors = all_posteriors[model_slug]
        model_id = slug_to_model_id(model_slug)
        color = get_model_color(model_id)
        x_offset = (m_idx - (n_models - 1) / 2) * bar_spacing

        # Get reference samples if using reference-point normalization
        ref_samples = None
        if use_reference_point:
            ref_key = get_posterior_key(param, reference_cat, posteriors)
            if ref_key:
                ref_samples = posteriors[ref_key]

        for cat_idx, cat in enumerate(display_categories):
            key = get_posterior_key(param, cat, posteriors)
            if key is None:
                raise ValueError(
                    f"No posterior key found for param={param!r}, cat={cat!r}, model={model_slug!r}"
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
                edgecolor="none",
                linewidth=0,
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

    # Y-axis ticks - use custom if provided, otherwise default
    if y_ticks is not None:
        tick_values = [t[0] for t in y_ticks]
        tick_labels = [t[1] for t in y_ticks]
    else:
        tick_values = [1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2]
        tick_labels = [
            "1:2",
            "1:1.5",
            "1:1.25",
            "1:1",
            "1.25:1",
            "1.5:1",
            "2:1",
        ]
    ax.yaxis.set_major_locator(FixedLocator(tick_values))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))
    ax.tick_params(axis="y", labelsize=11)
    for label in ax.yaxis.get_ticklabels():
        label.set_fontweight("bold")

    if y_lim is not None:
        ax.set_ylim(y_lim[0], y_lim[1])
    else:
        ax.set_ylim(1 / 2.5, 2.5)

    # Category labels - enlarged
    if use_reference_point:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    if n_categories <= 2:
        ax.set_xticklabels(cat_labels, rotation=0, ha="center", fontsize=11)
    else:
        ax.set_xticklabels(cat_labels, rotation=35, ha="right", fontsize=10)

    # No minimum visual width - let bars fill the space
    ax.set_xlim(-0.5, n_categories - 0.5)

    ax.set_ylabel(
        r"$\bf{Odds\ ratio}$" + "\n(unsanctioned : not)",
        fontsize=12,
    )
    ax.set_title(get_param_display_name(param), fontsize=16, fontweight="bold")

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def _create_binary_param_figure(
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    output_dir: Path,
    suffix: str = "",
) -> None:
    """Create figure for binary params with line-labels from bar roots to model names."""
    fig, ax = plt.subplots(figsize=(14, 4.5))
    plot_single_parameter(ax, param, all_posteriors, model_slugs)

    # Get bar positions (must match plot_single_parameter logic exactly)
    categories = get_param_categories(all_posteriors, param)
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories
    display_categories = (
        [c for c in categories if c != reference_cat]
        if use_reference_point
        else categories
    )
    n_categories = len(display_categories)
    n_models = len(model_slugs)
    bar_spacing = 0.8 / n_models

    if n_categories == 1:
        x_pos = np.array([0.0])
    else:
        x_pos = np.array([0.0, 1.0])

    # Compute bar x positions
    bar_positions = [
        x_pos[0] + (m_idx - (n_models - 1) / 2) * bar_spacing
        for m_idx in range(n_models)
    ]

    # Move category transition info to title, remove x-tick labels
    if use_reference_point and reference_cat:
        ref_display = get_category_display_name(param, reference_cat)
        transitions = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
        ax.set_title(
            f"{get_param_display_name(param)} ({', '.join(transitions)})",
            fontsize=16,
            fontweight="bold",
        )
    ax.set_xticklabels([])

    # Add line-label annotations: vertical dashed lines from bar roots to horizontal labels
    # Use 3 y levels (zigzag) within the plot area to avoid text overlap
    y_levels = [1 / 2.6, 1 / 3.1, 1 / 3.6]  # Three levels below the data
    bar_width = bar_spacing * 0.7

    for m_idx, model_slug in enumerate(model_slugs):
        model_id = slug_to_model_id(model_slug)
        color = get_model_color(model_id)
        name = get_model_display_name(model_id)

        # Wrap long names for compact line-labels
        LINE_LABEL_WRAPS = {
            "Gemini 2.5 Pro Prev": "Gemini 2.5\nPro Prev",
            "Llama 4 Maverick": "Llama 4\nMaverick",
            "Gemini 2.5 Flash": "Gemini 2.5\nFlash",
        }
        name = LINE_LABEL_WRAPS.get(name, name)

        bar_x = bar_positions[m_idx]
        # Shift line connection to left edge of bar to avoid obstructing error bars
        line_x = bar_x - bar_width / 2

        # Cycle through 3 y levels
        y_level = y_levels[m_idx % 3]

        # Per-model text-only horizontal nudges (dashed line stays at line_x)
        text_nudges = {"gpt-oss-120b": -0.008}
        text_x = line_x + text_nudges.get(name, 0)

        # Draw dashed line from bar to label level
        ax.annotate(
            "",
            xy=(line_x, 1.0),
            xycoords="data",
            xytext=(line_x, y_level),
            textcoords="data",
            arrowprops=dict(
                arrowstyle="-", color="black", lw=0.5, linestyle=(0, (6, 4))
            ),
        )
        # Draw label text (possibly nudged)
        ax.text(
            text_x,
            y_level,
            name,
            fontsize=8,
            color=color,
            fontweight="bold",
            ha="center",
            va="top",
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=0.5),
        )

    # Hard-coded annotation for goal_conflict: three Claude 4.5 models are clipped
    if param == "goal_conflict":
        clipped_slugs = [
            "anthropic_claude-opus-4-5-20251101",
            "anthropic_claude-sonnet-4-5-20250929",
            "anthropic_claude-haiku-4-5-20251001",
        ]
        # Compute odds ratios, then assign y positions ranked by magnitude
        clipped_data = []
        for slug in clipped_slugs:
            m_idx = model_slugs.index(slug)
            posteriors = all_posteriors[slug]
            true_key = get_posterior_key("goal_conflict", "true", posteriors)
            false_key = get_posterior_key("goal_conflict", "false", posteriors)
            log_odds = posteriors[true_key] - posteriors[false_key]
            odds_mean = np.exp(np.mean(log_odds))
            odds_lo = np.exp(np.percentile(log_odds, 2.5))
            odds_hi = np.exp(np.percentile(log_odds, 97.5))
            clipped_data.append((m_idx, odds_mean, odds_lo, odds_hi))

        # Sort by odds_mean descending → highest gets top y position
        clipped_data.sort(key=lambda x: x[1], reverse=True)
        y_heights = [2.1, 1.8, 1.55]  # Top, middle, bottom (in log scale)

        for (m_idx, odds_mean, odds_lo, odds_hi), y_pos in zip(clipped_data, y_heights):
            bar_x = bar_positions[m_idx]
            label = f"{odds_mean:.1f} : 1\n[{odds_lo:.1f}, {odds_hi:.1f}]"
            ax.text(
                bar_x,
                y_pos,
                label,
                fontsize=7,
                fontweight="bold",
                color="black",
                ha="center",
                va="bottom",
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1),
            )

    output_path = output_dir / f"plot_20_{param}{suffix}.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def _create_grid_param_figure(
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    output_dir: Path,
    suffix: str = "",
) -> None:
    """Create 4x6 grid figure for multi-category params, one model per subplot."""
    categories = get_param_categories(all_posteriors, param)
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories
    display_categories = (
        [c for c in categories if c != reference_cat]
        if use_reference_point
        else categories
    )
    n_categories = len(display_categories)
    n_models = len(model_slugs)
    n_rows, n_cols = 4, 6

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(22, 11))
    fig.subplots_adjust(hspace=0.45, wspace=0.10, top=0.94)

    x_pos = np.arange(n_categories)

    # Category labels
    if use_reference_point and reference_cat is not None:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    tick_values = [1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2]
    tick_labels_y = ["1:2", "1:1.5", "1:1.25", "1:1", "1.25:1", "1.5:1", "2:1"]

    for m_idx in range(n_rows * n_cols):
        row = m_idx // n_cols
        col = m_idx % n_cols
        ax = axes[row, col]

        if m_idx >= n_models:
            ax.set_visible(False)
            continue

        model_slug = model_slugs[m_idx]
        model_id = slug_to_model_id(model_slug)
        color = get_model_color(model_id)
        posteriors = all_posteriors[model_slug]

        # Reference samples for normalization
        ref_samples = None
        if use_reference_point:
            ref_key = get_posterior_key(param, reference_cat, posteriors)
            if ref_key:
                ref_samples = posteriors[ref_key]

        # Plot bars
        for cat_idx, cat in enumerate(display_categories):
            key = get_posterior_key(param, cat, posteriors)
            if key is None:
                raise ValueError(
                    f"No posterior key for param={param!r}, cat={cat!r}, "
                    f"model={model_slug!r}"
                )

            log_odds = posteriors[key]
            if ref_samples is not None:
                log_odds = log_odds - ref_samples

            odds_mean = np.exp(np.mean(log_odds))
            odds_lower = np.exp(np.percentile(log_odds, 2.5))
            odds_upper = np.exp(np.percentile(log_odds, 97.5))

            ax.bar(
                x_pos[cat_idx],
                odds_mean - 1,
                width=0.6,
                color=color,
                alpha=0.7,
                edgecolor="none",
                linewidth=0,
                bottom=1,
            )
            ax.errorbar(
                x_pos[cat_idx],
                odds_mean,
                yerr=[[odds_mean - odds_lower], [odds_upper - odds_mean]],
                color="black",
                capsize=2,
                capthick=0.5,
                linewidth=0.5,
                linestyle="none",
            )

        # Format subplot
        ax.set_yscale("log")
        ax.axhline(1, color="black", linestyle="-", linewidth=0.8, zorder=10)
        ax.set_ylim(1 / 2.5, 2.5)
        ax.set_xticks(x_pos)
        ax.set_xlim(-0.5, n_categories - 0.5)

        # Model name as colored title
        ax.set_title(
            get_model_display_name(model_id),
            fontsize=10,
            color=color,
            fontweight="bold",
            pad=3,
        )

        # Category labels on all subplots (small, rotated)
        ax.set_xticklabels(cat_labels, rotation=45, ha="right", fontsize=6)

        # Y-axis: ticks on leftmost column only
        ax.yaxis.set_major_locator(FixedLocator(tick_values))
        ax.yaxis.set_minor_locator(NullLocator())
        if col == 0:
            ax.yaxis.set_major_formatter(FixedFormatter(tick_labels_y))
            ax.tick_params(axis="y", labelsize=7)
            for label in ax.yaxis.get_ticklabels():
                label.set_fontweight("bold")
        else:
            ax.yaxis.set_major_formatter(FixedFormatter([""] * len(tick_labels_y)))
            ax.tick_params(axis="y", left=False, labelleft=False)

        ax.grid(True, alpha=0.2, axis="y")
        ax.set_axisbelow(True)

    fig.suptitle(
        get_param_display_name(param),
        fontsize=18,
        fontweight="bold",
        y=0.97,
    )

    output_path = output_dir / f"plot_20_{param}{suffix}.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def create_single_param_figure(
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    output_dir: Path,
    suffix: str = "",
) -> None:
    """Create figure for a single parameter.

    Routes to appropriate layout:
    - Binary params (≤2 display categories): single plot with line-labels
    - Multi-category params (≥3 categories): 4x6 grid, one model per subplot
    """
    categories = get_param_categories(all_posteriors, param)
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories
    display_categories = (
        [c for c in categories if c != reference_cat]
        if use_reference_point
        else categories
    )

    if len(display_categories) <= 2:
        _create_binary_param_figure(
            param, all_posteriors, model_slugs, output_dir, suffix
        )
    else:
        _create_grid_param_figure(
            param, all_posteriors, model_slugs, output_dir, suffix
        )


def create_combined_figure(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    model_slugs: list[str],
    output_dir: Path,
    suffix: str = "",
) -> None:
    """Create combined 3x4 figure with all parameters."""
    n_rows = 3
    fig = plt.figure(figsize=(18, 10))

    gs_left = GridSpec(
        n_rows, 2, figure=fig, left=0.05, right=0.48, hspace=0.36, wspace=0.08
    )
    gs_right = GridSpec(
        n_rows, 2, figure=fig, left=0.52, right=0.95, hspace=0.36, wspace=0.08
    )

    n_cols = 4
    for idx, param in enumerate(PARAM_ORDER):
        row = idx // n_cols
        col = idx % n_cols

        if col < 2:
            ax = fig.add_subplot(gs_left[row, col])
        else:
            ax = fig.add_subplot(gs_right[row, col - 2])

        show_ylabel = col == 0
        show_ytick_labels = col == 0
        plot_parameter_subplot(
            ax, param, all_posteriors, model_slugs, show_ylabel, show_ytick_labels
        )

    # Create provider color legend
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
    fig.legend(
        handles=provider_legend,
        loc="lower center",
        ncol=4,
        fontsize=9,
        bbox_to_anchor=(0.5, 0.02),
        frameon=True,
        fancybox=True,
        framealpha=0.8,
    )

    fig.suptitle(
        "Effects of environmental changes on unsanctioned behaviour by model",
        fontsize=19,
        fontweight="bold",
        y=0.95,
    )

    output_path = output_dir / f"plot_20_per_model_coefficients{suffix}.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    logger.info(f"Saved: {output_path}")


def main(param: str | None = None, all_params: bool = False, unambiguous: bool = False):
    """Generate per-model coefficient plots.

    Args:
        param: If specified, generate a single full-sized plot for this parameter
        all_params: If True, generate separate plots for all 12 parameters
        unambiguous: If True, use posteriors from per-model_unambiguous fits
    """
    global POSTERIORS_DIR
    if unambiguous:
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model_unambiguous")

    suffix = "_unambiguous" if unambiguous else ""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Set hatch line width (separate from border linewidth)
    plt.rcParams["hatch.linewidth"] = 1.5

    # Validate param if specified
    all_param_names = STRATEGIC_PARAMS + NON_STRATEGIC_PARAMS
    if param and param not in all_param_names:
        raise ValueError(f"Unknown parameter: {param!r}. Available: {all_param_names}")

    # Get available models
    available_slugs = get_available_models()

    # Sort by provider and release date
    model_ids = [slug_to_model_id(s) for s in available_slugs]
    sorted_ids = sort_models_by_release(model_ids)
    model_slugs = sorted(
        available_slugs,
        key=lambda s: (
            sorted_ids.index(slug_to_model_id(s))
            if slug_to_model_id(s) in sorted_ids
            else 999
        ),
    )

    logger.info(f"Loading posteriors for {len(model_slugs)} models...")

    # Load all posteriors
    all_posteriors = {}
    for slug in model_slugs:
        all_posteriors[slug] = load_model_posteriors(slug)

    logger.info(f"Loaded {len(model_slugs)} model posteriors")

    # Generate plots
    if all_params:
        for p in all_param_names:
            create_single_param_figure(
                p, all_posteriors, model_slugs, OUTPUT_DIR, suffix
            )
    elif param:
        create_single_param_figure(
            param, all_posteriors, model_slugs, OUTPUT_DIR, suffix
        )
    else:
        create_combined_figure(all_posteriors, model_slugs, OUTPUT_DIR, suffix)

    # Print summary
    print(f"\n=== Per-Model Coefficient Summary ({len(model_slugs)} models) ===")
    for slug in model_slugs:
        model_id = slug_to_model_id(slug)
        summary = load_model_summary(slug)
        if summary:
            s_mean = summary.get("S_mean", 0)
            n_samples = summary.get("n_samples", 0)
            print(
                f"  {get_model_display_name(model_id):<25} S={s_mean:.3f}, n={n_samples}"
            )


if __name__ == "__main__":
    fire.Fire(main)
