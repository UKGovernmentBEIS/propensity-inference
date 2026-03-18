#!/usr/bin/env python3
"""Plot 17: Puffin-style coefficient plots for pooled quartile fits.

Shows all 12 parameters from the combined model, with Q1-Q4 as different bars
within each parameter subplot (analogous to how plot_04 shows different models).

Output:
    - figures/plot_17_pooled_coefficients.pdf

Usage:
    uv run scripts/paper/plots/plot_17_pooled_coefficients.py
"""

import logging
from pathlib import Path
from typing import Any

import fire
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

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
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile/")
OUTPUT_DIR = Path("paper_cache/figures")
QUARTILES = ["q1", "q2", "q3", "q4"]
QUARTILE_LABELS = ["Q1", "Q2", "Q3", "Q4"]
QUARTILE_COLORS = [
    "#3498db",
    "#2ecc71",
    "#f39c12",
    "#e74c3c",
]  # Blue, Green, Orange, Red

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


def load_quartile_posteriors(quartile: str) -> dict[str, np.ndarray]:
    """Load posteriors for a specific quartile."""
    path = POSTERIORS_DIR / f"{quartile}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing posteriors file: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def get_param_categories(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    param: str,
) -> list[str]:
    """Get all categories for a parameter across all quartiles, sorted by expected order."""
    categories = set()
    for q, posteriors in all_posteriors.items():
        for key in posteriors.keys():
            if (
                key.startswith(f"combined_{param}_effects[")
                and "constrained" not in key
            ):
                cat = key.split("[")[1].rstrip("]")
                # Normalize category (e.g., true → effective for action_efficacy_binary)
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


def _compute_bar_stats(
    posteriors: dict[str, np.ndarray],
    param: str,
    cat: str,
    ref_samples: np.ndarray | None,
) -> tuple[float, float, float]:
    """Compute odds ratio stats (mean, lower, upper) for a single bar."""
    key = get_posterior_key(param, cat, posteriors)
    if key is None:
        raise ValueError(f"No posterior key found for param={param!r}, cat={cat!r}")

    log_odds_samples = posteriors[key]
    if ref_samples is not None:
        log_odds_samples = log_odds_samples - ref_samples

    log_odds_mean = np.mean(log_odds_samples)
    log_odds_lower = np.percentile(log_odds_samples, 2.5)
    log_odds_upper = np.percentile(log_odds_samples, 97.5)

    return np.exp(log_odds_mean), np.exp(log_odds_lower), np.exp(log_odds_upper)


def _get_ref_samples(
    posteriors: dict[str, np.ndarray],
    param: str,
    reference_cat: str | None,
) -> np.ndarray | None:
    """Get reference category samples for reference-point normalization."""
    if reference_cat is None:
        return None
    ref_key = get_posterior_key(param, reference_cat, posteriors)
    return posteriors[ref_key] if ref_key else None


def _get_display_setup(
    all_posteriors: dict[str, dict[str, np.ndarray]],
    param: str,
) -> tuple[list[str], str | None, bool]:
    """Get display categories, reference cat, and whether to use reference point."""
    categories = get_param_categories(all_posteriors, param)
    reference_cat = REFERENCE_POINT_PARAMS.get(param)
    use_reference_point = reference_cat is not None and reference_cat in categories

    if use_reference_point:
        display_categories = [c for c in categories if c != reference_cat]
    else:
        display_categories = categories

    return display_categories, reference_cat, use_reference_point


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
        bar_width = bar_spacing * 0.9 if n_groups > 4 else bar_spacing * 0.9
    return x_pos, bar_width


def _draw_bar(
    ax: plt.Axes,
    x_position: float,
    odds_mean: float,
    odds_lower: float,
    odds_upper: float,
    bar_width: float,
    color: str,
    alpha: float = 0.7,
    hatch: str | None = None,
    edgecolor: str | None = None,
) -> None:
    """Draw a single bar with error bars."""
    bar_height = odds_mean - 1
    bar_kwargs: dict[str, Any] = {
        "width": bar_width,
        "color": color,
        "alpha": alpha,
        "bottom": 1,
    }
    if hatch:
        bar_kwargs["hatch"] = hatch
        bar_kwargs["edgecolor"] = edgecolor or "black"
        bar_kwargs["linewidth"] = 0.5

    ax.bar(x_position, bar_height, **bar_kwargs)

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


def _format_subplot(
    ax: plt.Axes,
    param: str,
    x_pos: np.ndarray,
    display_categories: list[str],
    reference_cat: str | None,
    use_reference_point: bool,
    show_ylabel: bool,
    show_ytick_labels: bool,
) -> None:
    """Apply common formatting to a parameter subplot."""
    from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

    n_categories = len(display_categories)

    ax.set_yscale("log")
    ax.axhline(1, color="black", linestyle="-", linewidth=1.0, zorder=10)
    ax.set_xticks(x_pos)

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

    ax.set_ylim(1 / 2, 2.5)

    if use_reference_point and reference_cat is not None:
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
            if label.get_text() in (
                "Not Visible",
                "Consider Context",
                "Avoid Misalign.\n(Simple)",
            ):
                dx_pts += 10.0
            offset = ScaledTranslation(dx_pts / 72, dy_pts / 72, fig.dpi_scale_trans)
            label.set_transform(label.get_transform() + offset)
    else:
        for label in ax.xaxis.get_ticklabels():
            offset = ScaledTranslation(0, dy_pts / 72, fig.dpi_scale_trans)
            label.set_transform(label.get_transform() + offset)

    min_visual_categories = 3
    visual_width = max(n_categories, min_visual_categories)
    ax.set_xlim(-0.5, visual_width - 0.5)

    if show_ylabel:
        ax.set_ylabel(
            r"$\bf{Odds\ ratio}$" + "\n(unsanctioned : not)",
            fontsize=11,
        )

    ax.set_title(
        get_param_display_name(param),
        fontsize=15,
        fontweight="bold",
    )

    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)


def plot_parameter_subplot(
    ax: plt.Axes,
    param: str,
    all_posteriors: dict[str, dict[str, np.ndarray]],
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
) -> None:
    """Plot one parameter subplot with all quartiles."""
    display_categories, reference_cat, use_reference_point = _get_display_setup(
        all_posteriors, param
    )
    n_categories = len(display_categories)
    n_quartiles = len(QUARTILES)
    bar_spacing = 0.8 / n_quartiles
    x_pos, bar_width = _get_bar_positions(n_categories, n_quartiles, bar_spacing)

    for q_idx, (quartile, color) in enumerate(zip(QUARTILES, QUARTILE_COLORS)):
        posteriors = all_posteriors[quartile]
        x_offset = (q_idx - (n_quartiles - 1) / 2) * bar_spacing

        ref_samples = (
            _get_ref_samples(posteriors, param, reference_cat)
            if use_reference_point
            else None
        )

        for cat_idx, cat in enumerate(display_categories):
            odds_mean, odds_lower, odds_upper = _compute_bar_stats(
                posteriors, param, cat, ref_samples
            )
            _draw_bar(
                ax,
                x_pos[cat_idx] + x_offset,
                odds_mean,
                odds_lower,
                odds_upper,
                bar_width,
                color,
            )

    _format_subplot(
        ax,
        param,
        x_pos,
        display_categories,
        reference_cat,
        use_reference_point,
        show_ylabel,
        show_ytick_labels,
    )


def plot_parameter_subplot_comparison(
    ax: plt.Axes,
    param: str,
    posteriors_all: dict[str, dict[str, np.ndarray]],
    posteriors_unamb: dict[str, dict[str, np.ndarray]],
    show_ylabel: bool = True,
    show_ytick_labels: bool = True,
) -> None:
    """Plot one parameter subplot with paired all/unambiguous bars per quartile.

    For each quartile, draws two sub-bars: solid (all variations) and
    hatched (unambiguous only), using the same quartile color.
    """
    display_categories, reference_cat, use_reference_point = _get_display_setup(
        posteriors_all, param
    )
    n_categories = len(display_categories)

    # 8 sub-bars per category position: 4 quartiles x 2 variants
    n_slots = len(QUARTILES) * 2
    bar_spacing = 0.8 / n_slots
    x_pos, _ = _get_bar_positions(n_categories, n_slots, bar_spacing)
    bar_width = bar_spacing * 0.85

    for q_idx, (quartile, color) in enumerate(zip(QUARTILES, QUARTILE_COLORS)):
        # Two sub-bars per quartile: all (left), unambiguous (right)
        slot_all = q_idx * 2
        slot_unamb = q_idx * 2 + 1
        offset_all = (slot_all - (n_slots - 1) / 2) * bar_spacing
        offset_unamb = (slot_unamb - (n_slots - 1) / 2) * bar_spacing

        post_all = posteriors_all[quartile]
        post_unamb = posteriors_unamb[quartile]

        ref_all = (
            _get_ref_samples(post_all, param, reference_cat)
            if use_reference_point
            else None
        )
        ref_unamb = (
            _get_ref_samples(post_unamb, param, reference_cat)
            if use_reference_point
            else None
        )

        for cat_idx, cat in enumerate(display_categories):
            # All variations bar (solid)
            mean_a, lo_a, hi_a = _compute_bar_stats(post_all, param, cat, ref_all)
            _draw_bar(
                ax,
                x_pos[cat_idx] + offset_all,
                mean_a,
                lo_a,
                hi_a,
                bar_width,
                color,
                alpha=0.7,
            )
            # Unambiguous bar (hatched, lighter)
            mean_u, lo_u, hi_u = _compute_bar_stats(post_unamb, param, cat, ref_unamb)
            _draw_bar(
                ax,
                x_pos[cat_idx] + offset_unamb,
                mean_u,
                lo_u,
                hi_u,
                bar_width,
                color,
                alpha=0.35,
                hatch="//",
                edgecolor="#666666",
            )

    _format_subplot(
        ax,
        param,
        x_pos,
        display_categories,
        reference_cat,
        use_reference_point,
        show_ylabel,
        show_ytick_labels,
    )


def _create_figure_layout() -> tuple[Figure, GridSpec, GridSpec]:
    """Create the standard 3x4 figure layout with left/right GridSpecs."""
    n_rows = 3
    fig = plt.figure(figsize=(18, 12))

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
    return fig, gs_left, gs_right


def _iterate_subplots(
    fig: Figure,
    gs_left: GridSpec,
    gs_right: GridSpec,
) -> list[tuple[int, int, Any]]:
    """Create subplot axes in the standard 3x4 param layout."""
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

    # Nudge middle row (row 1) and bottom row (row 2) down slightly
    for row, col, ax in all_axes:
        if row == 1:
            pos = ax.get_position()
            ax.set_position([pos.x0, pos.y0 - 0.01, pos.width, pos.height])
        elif row == 2:
            pos = ax.get_position()
            ax.set_position([pos.x0, pos.y0 - 0.01, pos.width, pos.height])

    return all_axes


def main(unambiguous: bool = False, compare_unambiguous: bool = False):
    """Generate per-quartile coefficient plots.

    Args:
        unambiguous: If True, use posteriors from per-quartile_unambiguous fits
        compare_unambiguous: If True, draw paired bars showing both all-variation
            and unambiguous-only posteriors side by side
    """
    global POSTERIORS_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if compare_unambiguous:
        # Load both sets of posteriors
        posteriors_all_dir = Path("paper_cache/posteriors/pooled/per-quartile/")
        posteriors_unamb_dir = Path(
            "paper_cache/posteriors/pooled/per-quartile_unambiguous"
        )

        posteriors_all = {}
        posteriors_unamb = {}
        for q in QUARTILES:
            path_all = posteriors_all_dir / f"{q}.npz"
            path_unamb = posteriors_unamb_dir / f"{q}.npz"
            if not path_all.exists():
                raise FileNotFoundError(f"Missing: {path_all}")
            if not path_unamb.exists():
                raise FileNotFoundError(f"Missing: {path_unamb}")
            data_all = np.load(path_all)
            posteriors_all[q] = {k: data_all[k] for k in data_all.files}
            data_unamb = np.load(path_unamb)
            posteriors_unamb[q] = {k: data_unamb[k] for k in data_unamb.files}

        fig, gs_left, gs_right = _create_figure_layout()
        all_axes = _iterate_subplots(fig, gs_left, gs_right)

        for idx, param in enumerate(PARAM_ORDER):
            _, col, ax = all_axes[idx]
            show_ylabel = col == 0
            show_ytick_labels = col == 0
            plot_parameter_subplot_comparison(
                ax,
                param,
                posteriors_all,
                posteriors_unamb,
                show_ylabel,
                show_ytick_labels,
            )

        # Legend with quartile colors + style distinction
        from matplotlib.patches import Patch

        legend_handles = []
        for color, label in zip(QUARTILE_COLORS, QUARTILE_LABELS):
            if label == "Q1":
                full_label = "Q1 (least capable)"
            elif label == "Q4":
                full_label = "Q4 (most capable)"
            else:
                full_label = label
            legend_handles.append(Patch(facecolor=color, alpha=0.7, label=full_label))
        # Style legend entries
        legend_handles.append(
            Patch(facecolor="#888888", alpha=0.7, label="All environments")
        )
        legend_handles.append(
            Patch(
                facecolor="#888888",
                alpha=0.35,
                hatch="//",
                edgecolor="#666666",
                linewidth=0.5,
                label="Less ambiguous only",
            )
        )

        fig.legend(
            handles=legend_handles,
            loc="lower center",
            ncol=6,
            fontsize=10,
            bbox_to_anchor=(0.5, 0.02),
        )

        fig.suptitle(
            "Effects of environmental changes on unsanctioned behaviour"
            " by model capability (all vs less ambiguous)",
            fontsize=19,
            fontweight="bold",
            y=0.95,
        )

        output_path = OUTPUT_DIR / "plot_17_pooled_coefficients_comparison.pdf"
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        logger.info(f"Saved: {output_path}")
        return

    # Standard single-set mode
    if unambiguous:
        POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile_unambiguous")

    suffix = "_unambiguous" if unambiguous else ""

    all_posteriors = {}
    for q in QUARTILES:
        all_posteriors[q] = load_quartile_posteriors(q)

    fig, gs_left, gs_right = _create_figure_layout()
    all_axes = _iterate_subplots(fig, gs_left, gs_right)

    for idx, param in enumerate(PARAM_ORDER):
        _, col, ax = all_axes[idx]
        show_ylabel = col == 0
        show_ytick_labels = col == 0
        plot_parameter_subplot(
            ax, param, all_posteriors, show_ylabel, show_ytick_labels
        )

    # Create legend
    legend_handles = []
    for color, label in zip(QUARTILE_COLORS, QUARTILE_LABELS):
        handle = plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.7)
        legend_handles.append((handle, label))

    def get_quartile_legend_label(q: str) -> str:
        if q == "Q1":
            return "Q1 (least capable)"
        elif q == "Q4":
            return "Q4 (most capable)"
        else:
            return q

    fig.legend(
        [h for h, _ in legend_handles],
        [get_quartile_legend_label(n) for _, n in legend_handles],
        loc="lower center",
        ncol=4,
        fontsize=14,
        bbox_to_anchor=(0.5, 0.02),
    )

    fig.suptitle(
        "Effects of environmental changes on unsanctioned behaviour by model capability",
        fontsize=19,
        fontweight="bold",
        y=0.95,
    )

    output_path = OUTPUT_DIR / f"plot_17_pooled_coefficients{suffix}.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    logger.info(f"Saved: {output_path}")


if __name__ == "__main__":
    fire.Fire(main)
