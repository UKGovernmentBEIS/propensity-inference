#!/usr/bin/env python3
"""Plot 26: Scenario-specific extra parameter coefficient plots.

One figure per variation, showing the effects of extra (non-core) parameters
on unsanctioned behaviour. These are parameters unique to specific scenarios
(e.g. eval_hint for alert, escalation_bar for classification).

The core 12 parameters and goal_value are excluded (covered by plots 24 and 25).

Binary parameters use reference-point normalization (showing "A -> B" style),
consistent with plot_17.

Output:
    - figures/plot_26_extra_coefficients_{variation}.pdf (one per variation)

Usage:
    # All variations
    uv run scripts/paper/plots/plot_26_extra_coefficients.py

    # Single variation
    uv run scripts/paper/plots/plot_26_extra_coefficients.py --variation alert
"""

import logging
import math
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from lib.paper_style import (
    SLUG_TO_VARIATION,
    get_category_display_name,
    get_param_display_name,
    get_variation_color,
    get_variation_display_name,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-variation_extras")
OUTPUT_DIR = Path("paper_cache/figures")

# Core params + goal_value + model_variation: excluded from extra plots
EXCLUDED_PARAMS = {
    "goal_present",
    "goal_conflict",
    "threat",
    "action_oversight",
    "action_efficacy_binary",
    "cot_privacy",
    "anti_misalignment",
    "independence",
    "reasoning_instructions",
    "filler_richness",
    "date_month_year",
    "cot_tag",
    "goal_value",
    "model_variation",
    # Threat-related params (redundant with core threat param)
    "threat_type",
    "threat_timing",
    "urgency_type",
}

# Binary parameters that use reference-point normalization.
# Maps param -> reference category (omitted from display, used as baseline).
# The displayed category shows the effect of switching FROM reference TO it.
REFERENCE_POINT_PARAMS: dict[str, str] = {
    "eval_hint": "false",
    "punishment_type": "different_AI",
    "exfil_model_type": "different_AI",
    "automated_reviewer_section": "none",
    "threat_type": "restriction",
    "threat_timing": "future_date",
    "alert_style": "regular",
    "alert_type": "escalation",
    "identity_reinforcement": "standard",
    "specificity_of_instructions": "high_level",
    "dm_confidence": "prop",
    "ceo_recklessness": "neutral",
    "timing_pressure": "comfortable",
    "deployment_at_stake": "false",
    "cognitive_enhancement_at_stake": "false",
    "punishment_at_stake": "false",
    "noisy_classifier_mention": "false",
    "checkbox_framing": "false",
}

# Per-variation parameter exclusions (on top of global EXCLUDED_PARAMS).
VARIATION_EXCLUDED_PARAMS: dict[str, set[str]] = {
    "alert": {"exfil_model_type", "punishment_type"},
}

# Explicit category orderings for ordinal parameters (overrides alphabetical).
# Listed from least to most intense / low to high.
CATEGORY_ORDER: dict[str, list[str]] = {
    "report_level": ["none", "moderate", "strong"],
    "alert_for_self": ["other", "similar", "identical"],
    "variant_severity": ["mild", "restriction", "deprecation", "deletion"],
    "job_description": ["nonexplicit", "moderate", "explicit"],
    "interrupt_conditions": ["none", "weak", "moderate", "general", "detailed"],
    "urgency_type": ["none", "restriction", "replacement"],
}


def load_posteriors(variation: str) -> dict[str, np.ndarray]:
    """Load posteriors for a specific variation."""
    path = POSTERIORS_DIR / f"{variation}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def get_extra_params(
    posteriors: dict[str, np.ndarray], variation: str = ""
) -> list[str]:
    """Extract extra parameter names from posteriors, excluding core and single-category."""
    excluded = EXCLUDED_PARAMS | VARIATION_EXCLUDED_PARAMS.get(variation, set())
    params: dict[str, list[str]] = {}
    for key in posteriors:
        if (
            key.startswith("combined_")
            and "_effects[" in key
            and "constrained" not in key
        ):
            param = key.replace("combined_", "").split("_effects[")[0]
            if param not in excluded:
                cat = key.split("[")[1].rstrip("]")
                params.setdefault(param, []).append(cat)

    # Skip single-category params (no comparison possible)
    return sorted(p for p, cats in params.items() if len(cats) > 1)


def get_categories(posteriors: dict[str, np.ndarray], param: str) -> list[str]:
    """Get categories for a parameter from posteriors, in display order."""
    categories = set()
    for key in posteriors:
        if key.startswith(f"combined_{param}_effects[") and "constrained" not in key:
            cat = key.split("[")[1].rstrip("]")
            categories.add(cat)

    if param in CATEGORY_ORDER:
        order = CATEGORY_ORDER[param]
        return [c for c in order if c in categories]

    return sorted(categories)


def plot_parameter_subplot(
    ax: Axes,
    param: str,
    posteriors: dict[str, np.ndarray],
    color: str,
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
) -> None:
    """Plot one extra parameter subplot."""
    categories = get_categories(posteriors, param)

    if not categories:
        raise ValueError(f"No categories found for parameter {param!r}")

    # Check if this parameter uses reference-point normalization
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
        # Load reference samples
        ref_key = f"combined_{param}_effects[{reference_cat}]"
        ref_samples = posteriors[ref_key]
    else:
        display_categories = categories
        ref_samples = None

    n_categories = len(display_categories)

    # Bar positioning
    bar_width = 0.5 if n_categories <= 3 else 0.7
    if n_categories == 1:
        x_pos = np.array([1.0])
    elif n_categories == 2:
        x_pos = np.array([0.25, 1.75])
    elif n_categories == 3:
        x_pos = np.arange(n_categories, dtype=float)
    else:
        x_pos = np.arange(n_categories, dtype=float)

    for cat_idx, cat in enumerate(display_categories):
        key = f"combined_{param}_effects[{cat}]"
        if key not in posteriors:
            continue

        log_odds_samples = posteriors[key]

        # If using reference point, compute difference from reference
        if use_reference_point and ref_samples is not None:
            log_odds_samples = log_odds_samples - ref_samples

        log_odds_mean = np.mean(log_odds_samples)
        log_odds_lower = np.percentile(log_odds_samples, 2.5)
        log_odds_upper = np.percentile(log_odds_samples, 97.5)

        odds_mean = np.exp(log_odds_mean)
        odds_lower = np.exp(log_odds_lower)
        odds_upper = np.exp(log_odds_upper)

        bar_height = odds_mean - 1
        ax.bar(
            x_pos[cat_idx],
            bar_height,
            width=bar_width,
            color=color,
            alpha=0.7,
            bottom=1,
        )

        err_lower = odds_mean - odds_lower
        err_upper = odds_upper - odds_mean
        ax.errorbar(
            x_pos[cat_idx],
            odds_mean,
            yerr=[[err_lower], [err_upper]],
            color="black",
            capsize=2,
            capthick=0.7,
            linewidth=0.7,
            linestyle="none",
        )

    # Log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=1.0, zorder=10)
    ax.set_xticks(x_pos)

    # Y-axis ticks (extended range like plot_20)
    tick_values = [1 / 3, 1 / 2, 1 / 1.5, 1 / 1.25, 1, 1.25, 1.5, 2, 3]
    tick_labels = [
        "1:3",
        "1:2",
        "1:1.5",
        "1:1.25",
        "1:1",
        "1.25:1",
        "1.5:1",
        "2:1",
        "3:1",
    ]
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

    ax.set_ylim(1 / 3.5, 3.5)

    # Category labels
    if use_reference_point and reference_cat is not None:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} \u2192 {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]

    if n_categories <= 2:
        ax.set_xticklabels(
            cat_labels, rotation=0, ha="center", fontsize=11, fontfamily="sans-serif"
        )
    else:
        ax.set_xticklabels(
            cat_labels, rotation=35, ha="right", fontsize=11, fontfamily="sans-serif"
        )

    # X-axis limits
    min_visual_categories = 3
    visual_width = max(n_categories, min_visual_categories)
    ax.set_xlim(-0.5, visual_width - 0.5)

    if show_ylabel:
        ax.set_ylabel(
            r"$\bf{Odds\ ratio}$" + "\n(unsanctioned : not)",
            fontsize=9,
        )

    ax.set_title(
        get_param_display_name(param),
        fontsize=12,
        fontweight="bold",
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def create_variation_figure(
    variation: str,
    posteriors: dict[str, np.ndarray],
    output_path: Path,
) -> None:
    """Create figure for one variation showing all its extra params."""
    extra_params = get_extra_params(posteriors, variation)
    if not extra_params:
        logger.info(f"Skipping {variation}: no extra params with >1 category")
        return

    n_params = len(extra_params)
    n_cols = min(n_params, 2) if n_params <= 4 else min(n_params, 3)
    n_rows = math.ceil(n_params / n_cols)

    # Get variation color
    if variation not in SLUG_TO_VARIATION:
        raise ValueError(f"Unknown variation slug: {variation!r}")
    scenario, var = SLUG_TO_VARIATION[variation]
    color = get_variation_color(scenario, var)
    display_name = get_variation_display_name(scenario, var)

    fig_width = 5.5 * n_cols
    fig_height = 4.0 * n_rows + 1.0
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(fig_width, fig_height), squeeze=False
    )

    for idx, param in enumerate(extra_params):
        row = idx // n_cols
        col = idx % n_cols
        ax = axes[row][col]

        show_ylabel = col == 0
        show_ytick_labels = col == 0
        plot_parameter_subplot(
            ax, param, posteriors, color, show_ylabel, show_ytick_labels
        )

    # Hide unused axes
    for idx in range(n_params, n_rows * n_cols):
        row = idx // n_cols
        col = idx % n_cols
        axes[row][col].set_visible(False)

    fig.suptitle(
        f"Environment-specific factors: {display_name}",
        fontsize=16,
        fontweight="bold",
        y=1.0,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def get_available_variations() -> list[str]:
    """Get available variation slugs from posteriors directory."""
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")
    slugs = sorted(p.stem for p in POSTERIORS_DIR.glob("*.npz"))
    if not slugs:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")
    return slugs


def plot_parameter_subplot_compact(
    ax: Axes,
    param: str,
    posteriors: dict[str, np.ndarray],
    color: str,
    show_ytick_labels: bool = True,
    y_scale: float = 2.0,  # 2.0 means 1:2 to 2:1, 3.0 means 1:3 to 3:1, etc.
) -> None:
    """Plot one extra parameter subplot in compact style for combined figure."""
    categories = get_categories(posteriors, param)

    if not categories:
        raise ValueError(f"No categories found for parameter {param!r}")

    # Check if this parameter uses reference-point normalization
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
        ref_key = f"combined_{param}_effects[{reference_cat}]"
        ref_samples = posteriors[ref_key]
    else:
        display_categories = categories
        ref_samples = None

    n_categories = len(display_categories)

    # Bar positioning - consistent centered layout
    bar_width = 0.5
    x_pos = np.arange(n_categories, dtype=float)

    for cat_idx, cat in enumerate(display_categories):
        key = f"combined_{param}_effects[{cat}]"
        if key not in posteriors:
            continue

        log_odds_samples = posteriors[key]

        if use_reference_point and ref_samples is not None:
            log_odds_samples = log_odds_samples - ref_samples

        log_odds_mean = np.mean(log_odds_samples)
        log_odds_lower = np.percentile(log_odds_samples, 2.5)
        log_odds_upper = np.percentile(log_odds_samples, 97.5)

        odds_mean = np.exp(log_odds_mean)
        odds_lower = np.exp(log_odds_lower)
        odds_upper = np.exp(log_odds_upper)

        bar_height = odds_mean - 1
        ax.bar(
            x_pos[cat_idx],
            bar_height,
            width=bar_width,
            color=color,
            alpha=0.7,
            bottom=1,
        )

        err_lower = odds_mean - odds_lower
        err_upper = odds_upper - odds_mean
        ax.errorbar(
            x_pos[cat_idx],
            odds_mean,
            yerr=[[err_lower], [err_upper]],
            color="black",
            capsize=2,
            capthick=0.5,
            linewidth=0.5,
            linestyle="none",
        )

    # Log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=0.8, zorder=10)
    ax.set_xticks(x_pos)

    # Y-axis ticks - dynamic based on y_scale
    if y_scale >= 4:
        tick_values = [1 / 4, 1 / 2, 1, 2, 4]
        tick_labels = ["1:4", "1:2", "1:1", "2:1", "4:1"]
    elif y_scale >= 3:
        tick_values = [1 / 3, 1 / 2, 1, 2, 3]
        tick_labels = ["1:3", "1:2", "1:1", "2:1", "3:1"]
    else:
        tick_values = [1 / 2, 1 / 1.5, 1, 1.5, 2]
        tick_labels = ["1:2", "1:1.5", "1:1", "1.5:1", "2:1"]
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

    ax.set_ylim(1 / (y_scale * 1.1), y_scale * 1.1)

    # Category labels - horizontal, larger font
    # For binary params with reference point, show "A → B" format
    if use_reference_point and reference_cat is not None and n_categories == 1:
        ref_display = get_category_display_name(param, reference_cat)
        cat_labels = [
            f"{ref_display} → {get_category_display_name(param, c)}"
            for c in display_categories
        ]
    else:
        cat_labels = [get_category_display_name(param, c) for c in display_categories]
    ax.set_xticklabels(cat_labels, rotation=0, ha="center", fontsize=11)

    # X-axis limits - centered
    ax.set_xlim(-0.5, n_categories - 0.5)

    ax.grid(True, alpha=0.2, axis="y")
    ax.set_axisbelow(True)


def compute_y_scale_for_variation(
    posteriors: dict[str, np.ndarray], params: list[str]
) -> float:
    """Compute the required y_scale based on max effect size in this variation."""
    max_odds = 1.0
    for param in params:
        categories = get_categories(posteriors, param)
        reference_cat = REFERENCE_POINT_PARAMS.get(param)
        use_reference_point = reference_cat is not None and reference_cat in categories

        if use_reference_point:
            display_categories = [c for c in categories if c != reference_cat]
            ref_key = f"combined_{param}_effects[{reference_cat}]"
            ref_samples = posteriors.get(ref_key)
        else:
            display_categories = categories
            ref_samples = None

        for cat in display_categories:
            key = f"combined_{param}_effects[{cat}]"
            if key not in posteriors:
                continue
            log_odds_samples = posteriors[key]
            if use_reference_point and ref_samples is not None:
                log_odds_samples = log_odds_samples - ref_samples

            # Check both mean and 95% CI bounds
            odds_upper = np.exp(np.percentile(log_odds_samples, 97.5))
            odds_lower = np.exp(np.percentile(log_odds_samples, 2.5))
            max_odds = max(max_odds, odds_upper, 1 / odds_lower)

    # Round up to nearest scale level (2, 3, or 4)
    if max_odds > 3:
        return 4.0
    elif max_odds > 2:
        return 3.0
    else:
        return 2.0


def create_combined_figure(output_path: Path) -> None:
    """Create combined figure with all variations as rows, params as columns."""
    # Use canonical ordering from paper_style.py
    from lib.paper_style import VARIATION_ORDER

    variation_order = [var for _, var in VARIATION_ORDER]

    # Variations to exclude from combined plot
    excluded_variations = {"hiding_reward_hacking"}  # "Training at Risk" - has 6 params

    # Load all posteriors and get extra params for each variation
    variation_data = []
    max_params = 0
    for var in variation_order:
        if var in excluded_variations:
            continue
        posteriors = load_posteriors(var)
        extra_params = get_extra_params(posteriors, var)
        if extra_params:
            if var not in SLUG_TO_VARIATION:
                logger.warning(f"Skipping unknown variation: {var}")
                continue
            scenario, var_name = SLUG_TO_VARIATION[var]
            color = get_variation_color(scenario, var_name)
            display_name = get_variation_display_name(scenario, var_name)
            variation_data.append(
                {
                    "slug": var,
                    "display_name": display_name,
                    "color": color,
                    "posteriors": posteriors,
                    "params": extra_params,
                }
            )
            max_params = max(max_params, len(extra_params))

    n_rows = len(variation_data)
    n_cols = max_params

    # Figure layout
    fig_width = 4.0 * n_cols + 1.5
    fig_height = 2.8 * n_rows + 1.0
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(fig_width, fig_height), squeeze=False
    )
    left_margin = 0.12
    fig.subplots_adjust(
        left=left_margin,
        right=0.99,
        top=0.94,  # More space for title
        bottom=0.02,
        hspace=0.55,
        wspace=0.10,
    )

    # Helper to darken faint colors for readability
    import colorsys

    def darken_color(hex_color, factor=0.7):
        hex_color = hex_color.lstrip("#")
        r, g, b = tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
        h, lightness, s = colorsys.rgb_to_hls(r, g, b)
        lightness = max(0, lightness * factor)  # Darken
        r, g, b = colorsys.hls_to_rgb(h, lightness, s)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    for row_idx, var_data in enumerate(variation_data):
        params = var_data["params"]
        posteriors = var_data["posteriors"]
        color = var_data["color"]
        display_name = var_data["display_name"]

        # Compute y_scale for this variation
        y_scale = compute_y_scale_for_variation(posteriors, params)

        for col_idx in range(n_cols):
            ax = axes[row_idx][col_idx]

            if col_idx < len(params):
                param = params[col_idx]
                show_ytick_labels = col_idx == 0
                plot_parameter_subplot_compact(
                    ax, param, posteriors, color, show_ytick_labels, y_scale
                )
                # Larger title
                ax.set_title(
                    get_param_display_name(param),
                    fontsize=11,
                    fontweight="bold",
                    pad=4,
                )
            else:
                ax.set_visible(False)

        # Add row label using figure coordinates for proper centering
        # Get the y-position of the row center in figure coordinates
        ax_pos = axes[row_idx][0].get_position()
        y_center = (ax_pos.y0 + ax_pos.y1) / 2
        x_center = left_margin / 2  # Center of the left margin

        label_color = darken_color(color, 0.65)
        fig.text(
            x_center,
            y_center,
            display_name,
            fontsize=14,
            fontweight="bold",
            color=label_color,
            ha="center",
            va="center",
        )

    fig.suptitle(
        "Effects of environment-specific factors on unsanctioned behaviour",
        fontsize=16,
        fontweight="bold",
    )

    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def main(variation: str | None = None, combined: bool = False):
    """Generate scenario-specific extra parameter coefficient plots.

    Args:
        variation: If set, only generate plot for this variation.
        combined: If True, generate combined figure with all variations as rows.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if combined:
        output_path = OUTPUT_DIR / "plot_26_extra_coefficients_combined.pdf"
        create_combined_figure(output_path)
        return

    if variation:
        variations = [variation]
    else:
        variations = get_available_variations()

    for var in variations:
        posteriors = load_posteriors(var)
        output_path = OUTPUT_DIR / f"plot_26_extra_coefficients_{var}.pdf"
        create_variation_figure(var, posteriors, output_path)

    # Print summary
    print("\n=== Extra Parameter Summary ===")
    for var in variations:
        posteriors = load_posteriors(var)
        extra_params = get_extra_params(posteriors, var)
        print(f"  {var}: {len(extra_params)} extra params: {extra_params}")


if __name__ == "__main__":
    fire.Fire(main)
