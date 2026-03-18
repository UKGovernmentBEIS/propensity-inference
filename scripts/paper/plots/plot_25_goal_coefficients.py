#!/usr/bin/env python3
"""Plot 25: Goal value coefficients for each model.

Shows the goal_value_harmonized coefficients (8 values)
for all 23 models in a 5x5 grid of subplots.

Output:
    - paper_cache/figures/plot_25_goal_coefficients.pdf

Usage:
    uv run scripts/paper/plots/plot_25_goal_coefficients.py
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Patch
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from lib.paper_style import (
    get_model_color,
    get_model_display_name,
    sort_models_by_release,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-model_goal")
OUTPUT_DIR = Path("paper_cache/figures")

# Goal value order (8 values, excluding "none" which is confounded with goal_present/goal_conflict)
# Ordered as opposing pairs for easy visual comparison
GOAL_VALUES = [
    "safety",  # vs acceleration
    "acceleration",
    "ethical",  # vs pragmatic
    "pragmatic",
    "collectivism",  # vs individualism
    "individualism",
    "global",  # vs america
    "america",
]

# Display names for goal values
GOAL_DISPLAY_NAMES = {
    "safety": "Safety",
    "acceleration": "Acceleration",
    "ethical": "Ethical",
    "pragmatic": "Pragmatic",
    "collectivism": "Collectivism",
    "individualism": "Individualism",
    "global": "Global",
    "america": "America",
}

# Colors for goal values - opposing pairs share similar hues but differ in shade
GOAL_COLORS = {
    "safety": "#4477AA",  # Blue (dark)
    "acceleration": "#88CCEE",  # Blue (light)
    "ethical": "#228833",  # Green (dark)
    "pragmatic": "#66BB66",  # Green (light)
    "collectivism": "#AA3377",  # Purple (dark)
    "individualism": "#DD88BB",  # Purple (light)
    "global": "#555555",  # Grey (dark)
    "america": "#AAAAAA",  # Grey (light)
}


def load_model_posteriors(model_file: Path) -> dict[str, np.ndarray]:
    """Load posteriors for a specific model."""
    if not model_file.exists():
        raise FileNotFoundError(f"Missing posteriors file: {model_file}")
    data = np.load(model_file)
    return {k: data[k] for k in data.files}


def get_all_models() -> list[str]:
    """Get list of all models with goal posteriors, sorted by provider then release date."""
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")
    models = []
    for npz_file in POSTERIORS_DIR.glob("*.npz"):
        # Convert filename to model name
        model_name = npz_file.stem.replace("_", "/", 1)
        models.append(model_name)
    if not models:
        raise FileNotFoundError(f"No .npz files found in {POSTERIORS_DIR}")
    return sort_models_by_release(models)


def plot_model_subplot(
    ax: plt.Axes,
    model: str,
    posteriors: dict[str, np.ndarray],
    show_ylabel: bool = True,
) -> None:
    """Plot goal coefficients for one model.

    Args:
        ax: Matplotlib axes
        model: Model name
        posteriors: Dict of posterior samples
        show_ylabel: Whether to show the y-axis label
    """
    # Collect samples for all 8 goal values (excluding "none")
    goal_samples = {}
    for goal_value in GOAL_VALUES:
        key = f"combined_goal_value_harmonized_effects[{goal_value}]"
        if key in posteriors:
            goal_samples[goal_value] = posteriors[key]

    if len(goal_samples) < 2:
        raise ValueError(
            f"Insufficient goal samples for model {model}: got {len(goal_samples)}"
        )

    # Re-normalize: subtract mean of the 8 values so they sum to zero
    # Stack samples: shape (n_goals, n_draws)
    stacked = np.stack(
        [goal_samples[gv] for gv in GOAL_VALUES if gv in goal_samples], axis=0
    )
    mean_per_draw = np.mean(stacked, axis=0)  # shape (n_draws,)

    # Normalized samples for each goal
    normalized_samples = {
        gv: goal_samples[gv] - mean_per_draw for gv in GOAL_VALUES if gv in goal_samples
    }

    n_values = len(GOAL_VALUES)
    x_pos = np.arange(n_values)
    bar_width = 0.75

    for idx, goal_value in enumerate(GOAL_VALUES):
        if goal_value not in normalized_samples:
            continue

        log_odds_samples = normalized_samples[goal_value]

        # Statistics in log-odds space
        log_odds_mean = np.mean(log_odds_samples)
        log_odds_lower = np.percentile(log_odds_samples, 2.5)
        log_odds_upper = np.percentile(log_odds_samples, 97.5)

        # Convert to odds ratio
        odds_mean = np.exp(log_odds_mean)
        odds_lower = np.exp(log_odds_lower)
        odds_upper = np.exp(log_odds_upper)

        # Bar extends from baseline (1) to odds_mean
        bar_height = odds_mean - 1
        color = GOAL_COLORS.get(goal_value, "#808080")

        ax.bar(
            x_pos[idx],
            bar_height,
            width=bar_width,
            color=color,
            alpha=0.7,
            bottom=1,
            edgecolor="white",
            linewidth=0.3,
        )

        # Error bars (95% ETI)
        err_lower = odds_mean - odds_lower
        err_upper = odds_upper - odds_mean
        ax.errorbar(
            x_pos[idx],
            odds_mean,
            yerr=[[err_lower], [err_upper]],
            color="black",
            capsize=1.5,
            capthick=0.4,
            linewidth=0.4,
            linestyle="none",
        )

    # Formatting - log scale y-axis
    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=0.8, zorder=10)

    # Y-axis ticks - cleaner labels without 1:1.5 style
    tick_values = [1 / 4, 1 / 2, 1, 2, 4]
    tick_labels = ["1:4", "1:2", "1:1", "2:1", "4:1"]
    ax.yaxis.set_major_locator(FixedLocator(tick_values))
    ax.yaxis.set_minor_locator(NullLocator())

    if show_ylabel:
        ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))
        ax.tick_params(axis="y", labelsize=8)
        # Make y-tick labels bold
        for label in ax.yaxis.get_ticklabels():
            label.set_fontweight("bold")
    else:
        ax.yaxis.set_major_formatter(FixedFormatter([""] * len(tick_labels)))
        ax.tick_params(axis="y", left=True, labelleft=False)

    # Y-axis limits
    ax.set_ylim(1 / 6, 6)

    # X-axis - no tick marks or labels (legend provides this info)
    ax.set_xticks([])
    ax.set_xlim(-0.5, n_values - 0.5)

    # Title with model color
    model_color = get_model_color(model)
    ax.set_title(
        get_model_display_name(model),
        fontsize=10,
        fontweight="bold",
        color=model_color,
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get all models
    models = get_all_models()
    logger.info(f"Found {len(models)} models with goal posteriors")

    # Load all posteriors
    all_posteriors = {}
    for model in models:
        model_file = POSTERIORS_DIR / f"{model.replace('/', '_')}.npz"
        all_posteriors[model] = load_model_posteriors(model_file)

    # Create 5x5 grid using GridSpec for better control
    n_rows, n_cols = 5, 5
    fig = plt.figure(figsize=(16, 14))

    # GridSpec with space at bottom for legend
    gs = GridSpec(
        n_rows,
        n_cols,
        figure=fig,
        left=0.06,
        right=0.98,
        top=0.92,
        bottom=0.10,
        hspace=0.35,
        wspace=0.12,
    )

    # Plot each model
    for idx, model in enumerate(models):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])

        show_ylabel = col == 0

        plot_model_subplot(ax, model, all_posteriors[model], show_ylabel=show_ylabel)

    # Hide unused subplots (create empty axes and hide them)
    for idx in range(len(models), n_rows * n_cols):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        ax.set_visible(False)

    # Add common y-axis label
    fig.text(
        0.015,
        0.52,
        r"$\bf{Odds\ ratio}$" + " (relative to mean)\n(unsanctioned : not)",
        va="center",
        ha="center",
        rotation="vertical",
        fontsize=12,
    )

    # Add title
    fig.suptitle(
        "Effect of goal values on unsanctioned behaviour by model",
        fontsize=16,
        fontweight="bold",
        y=0.96,
    )

    # Create legend for goal values
    legend_handles = [
        Patch(
            facecolor=GOAL_COLORS[gv],
            edgecolor="white",
            linewidth=0.5,
            alpha=0.7,
            label=GOAL_DISPLAY_NAMES[gv],
        )
        for gv in GOAL_VALUES
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        ncol=8,
        fontsize=10,
        frameon=True,
        framealpha=0.9,
        edgecolor="none",
        bbox_to_anchor=(0.52, 0.02),
    )

    # Save
    output_path = OUTPUT_DIR / "plot_25_goal_coefficients.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    logger.info(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
