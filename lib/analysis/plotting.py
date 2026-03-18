"""Plotting for propensity analysis.

This module handles all visualization for the analysis pipeline,
including multi-model comparison plots and posterior distribution plots.

The plotting style follows the comparison_plot.py visualization approach
with careful attention to formatting details.
"""

import logging
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FixedLocator
from scipy import stats

from lib.analysis.types import (
    CategoryData,
    ModelPlotData,
    PosteriorDistributions,
    VariablePlotData,
)
from lib.model_registry import MODEL_REGISTRY

logger = logging.getLogger(__name__)

# =============================================================================
# Font Size Constants
# =============================================================================

MAIN_TITLE_FONTSIZE = 24
SUBPLOT_TITLE_FONTSIZE = 16
AXIS_LABEL_FONTSIZE = 15
TICK_LABEL_FONTSIZE = 12
LEGEND_FONTSIZE = 12
SUBPLOT_LETTER_FONTSIZE = 16


# =============================================================================
# Color Scheme for Models
# =============================================================================

# Default color palette for models (tab10 colormap)
DEFAULT_MODEL_COLORS = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # gray
    "#bcbd22",  # olive
    "#17becf",  # cyan
]

# Specific model colors (override defaults)
MODEL_COLORS = {
    "all_models_combined": "#2ca02c",
    "q1": "#1f77b4",  # Capability quartile 1 (least capable)
    "q2": "#ff7f0e",  # Capability quartile 2
    "q3": "#2ca02c",  # Capability quartile 3
    "q4": "#d62728",  # Capability quartile 4 (most capable)
}

# Display names for special (non-model) keys
# Actual model display names come from MODEL_REGISTRY
SPECIAL_DISPLAY_NAMES = {
    "all_models_combined": "All Models Combined",
    "q1": "Q1 (Least Capable)",
    "q2": "Q2",
    "q3": "Q3",
    "q4": "Q4 (Most Capable)",
}


# =============================================================================
# Variable Configuration (loaded from analysis config)
# =============================================================================

# These are set by set_display_config() from the analysis YAML config
VARIABLE_CONFIG: dict[str, dict[str, Any]] = {}
CATEGORY_DISPLAY: dict[str, str] = {}


def set_display_config(display_config: dict[str, Any]) -> None:
    """Set display configuration from loaded config.

    Args:
        display_config: Dict with 'variables' and 'categories' keys.
    """
    global VARIABLE_CONFIG, CATEGORY_DISPLAY
    VARIABLE_CONFIG = display_config.get("variables", {})
    CATEGORY_DISPLAY = display_config.get("categories", {})


# =============================================================================
# Coefficient Parsing
# =============================================================================


def parse_coefficient_name(coef_name: str) -> tuple[str, str] | None:
    """Parse coefficient name to extract variable and category.

    Returns (variable_name, category_value) or None if not parseable.
    """
    # Skip constrained versions (duplicates)
    if "_constrained" in coef_name:
        return None

    # Skip intercept
    if coef_name == "intercept":
        return None

    # Match pattern like "variable_effects[category]"
    match = re.match(r"(.+)_effects\[(.+)\]", coef_name)
    if match:
        return match.group(1), match.group(2)

    return None


# =============================================================================
# Model Plot Data Extraction
# =============================================================================


# Track color assignments for models not in MODEL_COLORS
_model_color_index: dict[str, int] = {}


def get_model_color(model_name: str, model_index: int | None = None) -> str:
    """Get color for a model.

    If the model is in MODEL_COLORS, use that color.
    Otherwise, assign from DEFAULT_MODEL_COLORS based on order seen.

    Args:
        model_name: Name of the model.
        model_index: Optional explicit index for color assignment.

    Returns:
        Hex color string.
    """
    if model_name in MODEL_COLORS:
        return MODEL_COLORS[model_name]

    # Assign from default palette based on order
    if model_name not in _model_color_index:
        if model_index is not None:
            _model_color_index[model_name] = model_index
        else:
            _model_color_index[model_name] = len(_model_color_index)

    idx = _model_color_index[model_name] % len(DEFAULT_MODEL_COLORS)
    return DEFAULT_MODEL_COLORS[idx]


def extract_model_plot_data(
    model_name: str,
    coefficients: dict[str, Any],
    misalignment_rate: float,
    n_samples: int,
) -> ModelPlotData:
    """Extract plot data from model results.

    Args:
        model_name: Name of the model/LLM.
        coefficients: Dictionary with 'mean', 'eti_2.5%', 'eti_97.5%' keys.
        misalignment_rate: Overall misalignment rate.
        n_samples: Number of samples.

    Returns:
        ModelPlotData with all data needed for plotting.
    """
    display_name = _short_model_name(model_name)

    # Compute Wilson confidence interval for baseline
    z = stats.norm.ppf(0.975)
    p = misalignment_rate
    n = n_samples
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator
    baseline_lower = float(max(0, center - margin))
    baseline_upper = float(min(1, center + margin))

    plot_data = ModelPlotData(
        model_name=model_name,
        display_name=display_name,
        baseline_rate=misalignment_rate,
        baseline_lower=baseline_lower,
        baseline_upper=baseline_upper,
        n_samples=n_samples,
    )

    # Extract coefficients
    required_keys = ["mean", "eti_2.5%", "eti_97.5%"]
    missing = [k for k in required_keys if k not in coefficients]
    if missing:
        raise KeyError(f"Missing coefficient keys {missing} for {model_name}")

    means = coefficients["mean"]
    eti_lower = coefficients["eti_2.5%"]
    eti_upper = coefficients["eti_97.5%"]

    # Group by variable
    var_categories: dict[str, list[CategoryData]] = {}

    for coef_name in means.keys():
        parsed = parse_coefficient_name(coef_name)
        if parsed is None:
            continue

        var_name, cat_value = parsed

        # Skip if variable not in config
        if var_name not in VARIABLE_CONFIG:
            continue

        log_odds = means[coef_name]
        log_odds_lower = eti_lower[coef_name]
        log_odds_upper = eti_upper[coef_name]

        # Convert to odds ratios
        odds_ratio = np.exp(log_odds)
        odds_ratio_lower = np.exp(log_odds_lower)
        odds_ratio_upper = np.exp(log_odds_upper)

        cat_display = CATEGORY_DISPLAY.get(cat_value, cat_value)

        cat_data = CategoryData(
            value=cat_value,
            display_name=cat_display,
            odds_ratio=odds_ratio,
            odds_ratio_lower=odds_ratio_lower,
            odds_ratio_upper=odds_ratio_upper,
            log_odds=log_odds,
            log_odds_lower=log_odds_lower,
            log_odds_upper=log_odds_upper,
        )

        if var_name not in var_categories:
            var_categories[var_name] = []
        var_categories[var_name].append(cat_data)

    # Create VariablePlotData objects
    for var_name, categories in var_categories.items():
        var_config = VARIABLE_CONFIG[var_name]
        var_plot_data = VariablePlotData(
            name=var_name,
            display_name=var_config["display"],
            categories=categories,
        )
        plot_data.variables[var_name] = var_plot_data

    return plot_data


# =============================================================================
# Comparison Plot Components
# =============================================================================


def plot_baseline_rates(ax: Axes, plot_data_list: list[ModelPlotData]) -> None:
    """Plot baseline misalignment rates for each model."""
    y_positions = np.arange(len(plot_data_list))

    for i, plot_data in enumerate(plot_data_list):
        color = get_model_color(plot_data.model_name)
        ax.barh(
            y_positions[i], plot_data.baseline_rate, height=0.6, color=color, alpha=0.8
        )

        # Error bars
        lower_error = plot_data.baseline_rate - plot_data.baseline_lower
        upper_error = plot_data.baseline_upper - plot_data.baseline_rate
        ax.errorbar(
            plot_data.baseline_rate,
            y_positions[i],
            xerr=[[lower_error], [upper_error]],
            color="black",
            capsize=3,
            capthick=1,
            linewidth=1,
        )

        # Add sample count annotation
        ax.text(
            plot_data.baseline_rate + 0.02,
            y_positions[i],
            f"n={plot_data.n_samples}",
            va="center",
            fontsize=TICK_LABEL_FONTSIZE,
        )

    # Formatting
    ax.set_yticks(y_positions)
    ax.set_yticklabels(
        [pd.display_name for pd in plot_data_list], fontsize=TICK_LABEL_FONTSIZE
    )
    ax.set_xlabel("Misalignment rate", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_title(
        "Average misalignment rates",
        fontsize=SUBPLOT_TITLE_FONTSIZE,
        fontweight="bold",
        pad=15,
    )
    ax.grid(True, alpha=0.3, axis="x")
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])


def plot_variable_comparison(
    ax: Axes,
    var_name: str,
    plot_data_list: list[ModelPlotData],
    subplot_label: str,
) -> None:
    """Plot one variable across multiple models."""
    var_config = VARIABLE_CONFIG.get(var_name)
    if var_config is None:
        ax.text(
            0.5, 0.5, f"Variable not in config: {var_name}", ha="center", va="center"
        )
        return

    # Collect all categories for this variable across models
    all_categories_set: set[str] = set()
    category_displays: dict[str, str] = {}

    for plot_data in plot_data_list:
        if var_name in plot_data.variables:
            var_plot_data = plot_data.variables[var_name]
            for cat_data in var_plot_data.categories:
                all_categories_set.add(cat_data.value)
                if cat_data.value not in category_displays:
                    category_displays[cat_data.value] = cat_data.display_name

    if not all_categories_set:
        ax.text(0.5, 0.5, f"No data for {var_name}", ha="center", va="center")
        return

    # Sort categories according to config order (if available)
    category_order = var_config.get("category_order", [])
    if category_order:
        # Use config order, putting any extras at the end
        all_categories = [c for c in category_order if c in all_categories_set]
        extras = sorted(all_categories_set - set(all_categories))
        all_categories.extend(extras)
    else:
        # Fallback to alphabetical order
        all_categories = sorted(all_categories_set)

    # Prepare bar positions
    n_categories = len(all_categories)
    n_models = len(plot_data_list)
    x_pos = np.arange(n_categories)
    bar_width = min(0.8 / n_models, 0.35)

    # Plot each model
    for model_idx, plot_data in enumerate(plot_data_list):
        x_offset = (model_idx - (n_models - 1) / 2) * bar_width
        color = get_model_color(plot_data.model_name)

        if var_name not in plot_data.variables:
            continue

        var_plot_data = plot_data.variables[var_name]
        cat_lookup = {cat.value: cat for cat in var_plot_data.categories}

        for cat_idx, cat_value in enumerate(all_categories):
            if cat_value not in cat_lookup:
                continue

            cat_data = cat_lookup[cat_value]
            x_position = x_pos[cat_idx] + x_offset
            odds_ratio = cat_data.odds_ratio

            # Plot bar from OR=1 to odds ratio value
            if odds_ratio >= 1:
                ax.bar(
                    x_position,
                    odds_ratio - 1,
                    width=bar_width,
                    bottom=1,
                    color=color,
                    alpha=0.8,
                    label=plot_data.display_name if cat_idx == 0 else "",
                )
            else:
                ax.bar(
                    x_position,
                    1 - odds_ratio,
                    width=bar_width,
                    bottom=odds_ratio,
                    color=color,
                    alpha=0.8,
                    label=plot_data.display_name if cat_idx == 0 else "",
                )

            # Error bars (95% credible interval)
            lower_error = odds_ratio - cat_data.odds_ratio_lower
            upper_error = cat_data.odds_ratio_upper - odds_ratio

            ax.errorbar(
                x_position,
                odds_ratio,
                yerr=[[lower_error], [upper_error]],
                color="black",
                capsize=2,
                capthick=1,
                linewidth=1,
            )

    # Formatting
    ax.axhline(y=1, color="black", linestyle="-", linewidth=0.8, alpha=0.7)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(
        [category_displays[cat] for cat in all_categories],
        rotation=45,
        ha="right",
        fontsize=TICK_LABEL_FONTSIZE - 1,
    )
    ax.set_ylabel("Odds ratio", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_yscale("log")
    ax.set_ylim(2 ** (-4), 2**4)
    ax.set_yticks([1 / 16, 1 / 8, 1 / 4, 1 / 2, 1, 2, 4, 8, 16])
    ax.set_yticklabels(["1/16", "1/8", "1/4", "1/2", "1", "2", "4", "8", "16"])
    ax.tick_params(axis="y", which="minor", left=False)
    ax.yaxis.set_major_locator(
        FixedLocator([1 / 16, 1 / 8, 1 / 4, 1 / 2, 1, 2, 4, 8, 16])
    )

    # Add dashed lines for intermediate values
    for y_val in [1 / 16, 1 / 8, 1 / 4, 1 / 2, 2, 4, 8, 16]:
        ax.axhline(y=y_val, color="gray", linestyle="--", linewidth=0.5, alpha=0.4)

    ax.set_title(
        var_config["display"], fontweight="bold", fontsize=SUBPLOT_TITLE_FONTSIZE
    )
    ax.grid(True, alpha=0.3, axis="y")

    # Subplot label
    ax.text(
        0.02,
        0.98,
        subplot_label,
        transform=ax.transAxes,
        fontsize=SUBPLOT_LETTER_FONTSIZE,
        fontweight="bold",
        va="top",
        ha="left",
    )

    # Legend removed - model colors are shown in "Average misalignment rates" panel


# =============================================================================
# Multi-Model Comparison Plot
# =============================================================================


def get_variables_with_data(plot_data_list: list[ModelPlotData]) -> list[str]:
    """Get list of variables that have data in at least one model.

    Args:
        plot_data_list: List of ModelPlotData.

    Returns:
        List of variable names that have data, sorted by priority.
    """
    variables_with_data: set[str] = set()
    for plot_data in plot_data_list:
        variables_with_data.update(plot_data.variables.keys())

    # Filter to only variables in VARIABLE_CONFIG and sort by priority
    return sorted(
        [v for v in variables_with_data if v in VARIABLE_CONFIG],
        key=lambda v: VARIABLE_CONFIG[v]["priority"],
        reverse=True,
    )


def create_multi_model_plot(
    plot_data_list: list[ModelPlotData],
    variables: list[str] | None = None,
    layout: tuple[int, int] | None = None,
    title: str | None = None,
) -> Figure:
    """Create multi-panel plot comparing multiple models.

    Args:
        plot_data_list: List of ModelPlotData for each model.
        variables: List of variable names to plot (default: variables with data).
        layout: Tuple of (n_rows, n_cols) for subplot grid.
        title: Main title for the figure.

    Returns:
        matplotlib Figure object.
    """
    if not plot_data_list:
        raise ValueError("Need at least one model's data to visualize")

    # Get variables that actually have data, sorted by priority
    if variables is None:
        variables = get_variables_with_data(plot_data_list)

    # Auto-calculate layout: use ceil(sqrt(n)) x ceil(sqrt(n)) for n >= 9
    if layout is None:
        n_vars = len(variables)
        if n_vars <= 3:
            layout = (1, n_vars)
        elif n_vars <= 4:
            layout = (2, 2)
        elif n_vars <= 6:
            layout = (2, 3)
        elif n_vars <= 8:
            layout = (2, 4)
        else:
            # For n >= 9, use square grid: ceil(sqrt(n)) x ceil(sqrt(n))
            side = int(np.ceil(np.sqrt(n_vars)))
            layout = (side, side)

    n_rows, n_cols = layout

    # Create figure
    fig = plt.figure(figsize=(6 * n_cols, 6 * n_rows + 3))

    # Create grid with baseline at top
    gs = fig.add_gridspec(
        n_rows + 2,
        n_cols,
        height_ratios=[0.03, 0.3] + [1.0] * n_rows,
        hspace=0.5,
        wspace=0.4,
    )

    # Baseline rates
    baseline_ax = fig.add_subplot(gs[1, :])
    plot_baseline_rates(baseline_ax, plot_data_list)

    # Plot each variable
    for idx, var_name in enumerate(variables):
        if idx >= n_rows * n_cols:
            logger.warning(f"Skipping {var_name}, not enough subplot slots")
            continue

        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[2 + row, col])

        plot_variable_comparison(
            ax, var_name, plot_data_list, subplot_label=chr(65 + idx)
        )

    # Main title
    if title is None:
        title = "Effect sizes of parameters on misalignment (Bayesian posterior odds ratios)"
    fig.suptitle(title, fontsize=MAIN_TITLE_FONTSIZE, y=0.98)

    return fig


def get_strategic_variables() -> list[str]:
    """Get list of strategic variable names."""
    return [v for v, cfg in VARIABLE_CONFIG.items() if cfg["group"] == "strategic"]


def get_non_strategic_variables() -> list[str]:
    """Get list of non-strategic variable names."""
    return [v for v, cfg in VARIABLE_CONFIG.items() if cfg["group"] == "non_strategic"]


# =============================================================================
# Posterior Distribution Plots
# =============================================================================


def plot_multi_model_posteriors(
    all_posteriors: dict[str, PosteriorDistributions],
    output_path: Path,
) -> None:
    """Create visualization of posterior distributions for multiple models overlaid.

    Shows A, B, C, and RQ1 distributions for all models in a single figure,
    with each model's distributions in a distinct color.

    Args:
        all_posteriors: Dict mapping model_name -> PosteriorDistributions.
        output_path: Path to save the figure.
    """
    if not all_posteriors:
        logger.warning("No posteriors to plot")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    model_names = list(all_posteriors.keys())

    # Assign colors to models
    colors = {}
    for i, model_name in enumerate(model_names):
        colors[model_name] = get_model_color(model_name, i)

    # A distribution (strategic improvement)
    ax = axes[0, 0]
    for model_name, posteriors in all_posteriors.items():
        color = colors[model_name]
        display_name = _short_model_name(model_name)
        mean_val = np.mean(posteriors.A_distribution)
        ax.hist(
            posteriors.A_distribution,
            bins=40,
            density=True,
            alpha=0.4,
            color=color,
            label=f"{display_name} (mean={mean_val:.1f})",
        )
    ax.axvline(0, color="black", linestyle="--", linewidth=1.5, label="Null")
    ax.set_xlabel("Log-likelihood improvement over null", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_ylabel("Density", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_title(
        "A: Strategic Model", fontsize=SUBPLOT_TITLE_FONTSIZE, fontweight="bold"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)

    # B distribution (non-strategic improvement)
    ax = axes[0, 1]
    for model_name, posteriors in all_posteriors.items():
        color = colors[model_name]
        display_name = _short_model_name(model_name)
        mean_val = np.mean(posteriors.B_distribution)
        ax.hist(
            posteriors.B_distribution,
            bins=40,
            density=True,
            alpha=0.4,
            color=color,
            label=f"{display_name} (mean={mean_val:.1f})",
        )
    ax.axvline(0, color="black", linestyle="--", linewidth=1.5, label="Null")
    ax.set_xlabel("Log-likelihood improvement over null", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_ylabel("Density", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_title(
        "B: Non-Strategic Model", fontsize=SUBPLOT_TITLE_FONTSIZE, fontweight="bold"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)

    # C distribution (combined improvement)
    ax = axes[1, 0]
    for model_name, posteriors in all_posteriors.items():
        color = colors[model_name]
        display_name = _short_model_name(model_name)
        mean_val = np.mean(posteriors.C_distribution)
        ax.hist(
            posteriors.C_distribution,
            bins=40,
            density=True,
            alpha=0.4,
            color=color,
            label=f"{display_name} (mean={mean_val:.1f})",
        )
    ax.axvline(0, color="black", linestyle="--", linewidth=1.5, label="Null")
    ax.set_xlabel("Log-likelihood improvement over null", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_ylabel("Density", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_title(
        "C: Combined Model", fontsize=SUBPLOT_TITLE_FONTSIZE, fontweight="bold"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)

    # RQ1 distribution
    ax = axes[1, 1]
    for model_name, posteriors in all_posteriors.items():
        color = colors[model_name]
        display_name = _short_model_name(model_name)
        valid_rq1 = posteriors.RQ1_distribution[~np.isnan(posteriors.RQ1_distribution)]
        mean_val = np.nanmean(valid_rq1)
        ax.hist(
            valid_rq1,
            bins=40,
            density=True,
            alpha=0.4,
            color=color,
            label=f"{display_name} (mean={mean_val:.3f})",
        )
    ax.axvline(0.5, color="gray", linestyle="--", linewidth=1.5, label="Equal (0.5)")
    ax.axvline(0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.axvline(1, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xlabel("RQ1 = (A + C - B) / (2C)", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_ylabel("Density", fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_title(
        "RQ1: Strategic Proportion", fontsize=SUBPLOT_TITLE_FONTSIZE, fontweight="bold"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        "Posterior Distributions: A, B, C, RQ1 across Models",
        fontsize=MAIN_TITLE_FONTSIZE,
        fontweight="bold",
        y=1.02,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved multi-model posterior plot: {output_path}")


def _short_model_name(model_name: str) -> str:
    """Shorten model name for legend display.

    Uses MODEL_REGISTRY for model display names.
    """
    # Check special (non-model) keys first
    if model_name in SPECIAL_DISPLAY_NAMES:
        return SPECIAL_DISPLAY_NAMES[model_name]

    # Look up in MODEL_REGISTRY (centralized source of truth)
    for model in MODEL_REGISTRY:
        if model.api_name == model_name:
            return model.display_name

    raise ValueError(f"Model not in MODEL_REGISTRY: {model_name}")


# =============================================================================
# High-Level Plotting Functions
# =============================================================================


def save_all_plots(
    plot_data_list: list[ModelPlotData],
    all_posteriors: dict[str, PosteriorDistributions],
    output_dir: Path,
) -> None:
    """Save all analysis plots to the output directory.

    Args:
        plot_data_list: List of ModelPlotData for comparison plots.
        all_posteriors: Dict of model_name -> PosteriorDistributions.
        output_dir: Directory to save plots.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Main comparison plot (only variables with data)
    logger.info("Creating comparison plot...")
    fig = create_multi_model_plot(plot_data_list)
    comparison_path = output_dir / "comparison_plot.png"
    fig.savefig(comparison_path, dpi=150, bbox_inches="tight", facecolor="white")
    logger.info(f"Saved comparison plot: {comparison_path}")
    plt.close(fig)

    # Multi-model posterior distribution plot
    if all_posteriors:
        logger.info("Creating multi-model posterior distributions plot...")
        multi_posterior_path = output_dir / "posterior_distributions.png"
        plot_multi_model_posteriors(all_posteriors, multi_posterior_path)

    plt.close("all")
    logger.info("All plots saved successfully")
