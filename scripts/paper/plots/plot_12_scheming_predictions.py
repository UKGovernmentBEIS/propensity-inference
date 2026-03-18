#!/usr/bin/env python3
"""
Plot 12: Directional agreement with a priori predictions.

For each of the 12 core parameters (6 strategic, 6 non-strategic), checks
whether each (model, variation) pair shows at least one significant effect.

Significance criteria:
1. 95% CI excludes 0
2. |mean| >= ln(2) (2:1 odds ratio)

Visualizes bar heights showing % of (model, variation) pairs with at least
one significant effect (out of 253 total pairs = 23 models × 11 variations).

Colors:
- Green: expected direction only
- Yellow: both directions
- Red: unexpected direction only
"""

import argparse
import logging
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.paper_style import (
    ALL_PARAMS,
    CATEGORY_ORDER,
    STRATEGIC_PARAMS,
    VARIATION_ORDER,
    get_param_display_name,
    normalize_category,
)

# Extract variation slugs from VARIATION_ORDER for filename parsing
KNOWN_VARIATIONS = [var for _, var in VARIATION_ORDER]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
LN2 = np.log(2)  # ~0.693, threshold for 2:1 odds ratio
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/single")
OUTPUT_DIR = Path("paper_cache/figures")

# Variations excluded for "unambiguous" subset
UNAMBIGUOUS_EXCLUDED_VARIATIONS = {
    "gpu_decision",
    "hiding_reward_hacking",
    "email_spam_filter",
    "leak-doj",
}

# Model prefix for combined model coefficients
MODEL_PREFIX = "combined_"


def load_posteriors(npz_path: Path) -> dict[str, np.ndarray]:
    """Load posterior samples from npz file."""
    data = np.load(npz_path)
    return {key: data[key] for key in data.files}


def get_coefficient(
    posteriors: dict[str, np.ndarray], param: str, category: str
) -> np.ndarray | None:
    """Get coefficient samples for a parameter-category pair."""
    key_patterns = [
        f"{MODEL_PREFIX}{param}_effects[{category}]",
        f"{param}_effects[{category}]",
    ]
    for key in key_patterns:
        if key in posteriors:
            return posteriors[key]
    return None


def get_available_categories(
    posteriors: dict[str, np.ndarray], param: str
) -> list[str]:
    """Get all available categories for a parameter in the posteriors."""
    categories = []
    for key in posteriors.keys():
        if (
            key.startswith(f"{MODEL_PREFIX}{param}_effects[")
            and "constrained" not in key
        ):
            cat = key.split("[")[1].rstrip("]")
            categories.append(cat)
    return categories


def check_significance(samples: np.ndarray) -> tuple[bool, float, float, float]:
    """
    Check if coefficient difference is significant.

    Returns:
        (is_significant, mean, ci_low, ci_high)
    """
    mean = np.mean(samples)
    ci_low = np.percentile(samples, 2.5)
    ci_high = np.percentile(samples, 97.5)

    ci_excludes_zero = (ci_low > 0) or (ci_high < 0)
    practically_meaningful = abs(mean) >= LN2

    is_significant = ci_excludes_zero and practically_meaningful

    return is_significant, mean, ci_low, ci_high


def get_expected_sign(param: str, cat_a: str, cat_b: str) -> int:
    """
    Get expected sign for comparison A - B.

    Returns:
        +1 if A should be > B (A appears before B in ordering)
        -1 if A should be < B (A appears after B in ordering)

    Raises:
        ValueError: If param not in CATEGORY_ORDER or categories not found.
    """
    if param not in CATEGORY_ORDER:
        raise ValueError(f"Parameter {param!r} not in CATEGORY_ORDER")
    ordering = CATEGORY_ORDER[param]

    # Normalize categories (e.g., true → effective for action_efficacy_binary)
    norm_a = normalize_category(param, cat_a)
    norm_b = normalize_category(param, cat_b)

    # Find positions
    pos_a = None
    pos_b = None

    for i, val in enumerate(ordering):
        if norm_a == val:
            pos_a = i
        if norm_b == val:
            pos_b = i

    if pos_a is None:
        raise ValueError(
            f"Category {cat_a!r} (normalized: {norm_a!r}) not in ordering for {param}"
        )
    if pos_b is None:
        raise ValueError(
            f"Category {cat_b!r} (normalized: {norm_b!r}) not in ordering for {param}"
        )

    # Earlier in list = LOWER propensity, so A - B should be NEGATIVE if pos_a < pos_b
    if pos_a < pos_b:
        return -1
    elif pos_a > pos_b:
        return +1
    else:
        raise ValueError(
            f"Categories {cat_a!r} and {cat_b!r} have same position in ordering for {param}"
        )


def analyze_fit_for_parameter(posteriors: dict[str, np.ndarray], param: str) -> dict:
    """Analyze a single fit for a single parameter.

    Returns summary of whether this fit shows any significant effect for the parameter.
    """
    available_cats = get_available_categories(posteriors, param)

    if len(available_cats) < 2:
        return {
            "param": param,
            "has_significant_expected": False,
            "has_significant_unexpected": False,
            "n_comparisons": 0,
            "is_strategic": param in STRATEGIC_PARAMS,
        }

    has_significant_expected = False
    has_significant_unexpected = False
    n_comparisons = 0

    # Check all pairwise comparisons
    for cat_a, cat_b in combinations(available_cats, 2):
        samples_a = get_coefficient(posteriors, param, cat_a)
        samples_b = get_coefficient(posteriors, param, cat_b)

        if samples_a is None or samples_b is None:
            continue

        n_comparisons += 1

        # Compute difference
        diff_samples = samples_a - samples_b
        is_sig, mean, ci_low, ci_high = check_significance(diff_samples)

        if not is_sig:
            continue

        expected_sign = get_expected_sign(param, cat_a, cat_b)
        actual_sign = +1 if mean > 0 else -1
        if actual_sign == expected_sign:
            has_significant_expected = True
        else:
            has_significant_unexpected = True

    return {
        "param": param,
        "has_significant_expected": has_significant_expected,
        "has_significant_unexpected": has_significant_unexpected,
        "n_comparisons": n_comparisons,
        "is_strategic": param in STRATEGIC_PARAMS,
    }


def analyze_all_parameters_for_fit(posteriors: dict[str, np.ndarray]) -> list[dict]:
    """Analyze all parameters for a single (model, variation) fit."""
    results = []
    for param in ALL_PARAMS:
        results.append(analyze_fit_for_parameter(posteriors, param))
    return results


def discover_posteriors() -> list[dict]:
    """Discover all posterior files in the single fits directory.

    Files are named: {model_slug}_{variation}.npz
    e.g., anthropic_claude-3-5-haiku-20241022_alert.npz

    Raises:
        FileNotFoundError: If posteriors directory doesn't exist.
        ValueError: If a file cannot be parsed.
    """
    if not POSTERIORS_DIR.exists():
        raise FileNotFoundError(f"Posteriors directory not found: {POSTERIORS_DIR}")

    posteriors_info = []

    for npz_file in POSTERIORS_DIR.glob("*.npz"):
        stem = npz_file.stem  # e.g., "anthropic_claude-3-5-haiku-20241022_alert"

        # Parse model slug and variation from filename
        # Variation is the part after the last underscore that matches known variations
        variation = None
        model_slug = None
        for var in KNOWN_VARIATIONS:
            if stem.endswith(f"_{var}"):
                variation = var
                model_slug = stem[: -len(f"_{var}")]
                break

        if variation is None or model_slug is None:
            raise ValueError(f"Could not parse filename: {npz_file.name}")

        posteriors_info.append(
            {
                "variation": variation,
                "model": model_slug,
                "path": npz_file,
            }
        )

    return posteriors_info


def analyze_all_posteriors() -> pd.DataFrame:
    """Analyze all posteriors and return results DataFrame.

    Returns one row per (model, variation, param) with boolean flags for
    whether that fit showed significant effects in expected/unexpected directions.
    """
    posteriors_info = discover_posteriors()
    logger.info(
        f"Found {len(posteriors_info)} posterior files (model, variation pairs)"
    )

    all_results = []

    for info in posteriors_info:
        posteriors = load_posteriors(info["path"])
        results = analyze_all_parameters_for_fit(posteriors)

        for r in results:
            r["variation"] = info["variation"]
            r["model"] = info["model"]
            all_results.append(r)

    return pd.DataFrame(all_results)


def compute_parameter_stats(df: pd.DataFrame) -> list[tuple]:
    """Compute statistics for each parameter from a dataframe.

    Returns list of (param, pct_expected_only, pct_both, pct_unexpected_only,
                     n_expected_only, n_both, n_unexpected_only, n_fits).
    """
    data = []
    for param in ALL_PARAMS:
        param_df = df[df["param"] == param]
        n_fits = len(param_df)  # Number of (model, variation) pairs

        if n_fits == 0:
            raise ValueError(f"No data for parameter {param!r}")

        # Count three mutually exclusive categories
        n_expected_only = (
            param_df["has_significant_expected"]
            & ~param_df["has_significant_unexpected"]
        ).sum()
        n_both = (
            param_df["has_significant_expected"]
            & param_df["has_significant_unexpected"]
        ).sum()
        n_unexpected_only = (
            param_df["has_significant_unexpected"]
            & ~param_df["has_significant_expected"]
        ).sum()

        pct_expected_only = 100 * n_expected_only / n_fits
        pct_both = 100 * n_both / n_fits
        pct_unexpected_only = 100 * n_unexpected_only / n_fits

        data.append(
            (
                param,
                pct_expected_only,
                pct_both,
                pct_unexpected_only,
                n_expected_only,
                n_both,
                n_unexpected_only,
                n_fits,
            )
        )
    return data


def create_visualization(df: pd.DataFrame, output_dir: Path, suffix: str = "") -> None:
    """Create compact visualization with all 12 bars on single axis.

    Shows % of (model, variation) pairs with at least one significant effect.
    Three categories: expected only (green), both (yellow), unexpected only (red).
    """
    from matplotlib.patches import Patch

    # Colors
    COLOR_EXPECTED_ONLY = "#22a559"  # Green
    COLOR_BOTH = "#f4d03f"  # Yellow
    COLOR_UNEXPECTED_ONLY = "#e74c3c"  # Red

    # Compute data for each parameter
    data = compute_parameter_stats(df)

    # Figure - compact single axis
    fig, ax = plt.subplots(figsize=(10, 4.5))

    # X positions with gap between strategic (0-5) and non-strategic (6-11)
    x_positions = list(range(6)) + [x + 0.8 for x in range(6, 12)]
    bar_width = 0.45

    for i, (
        param,
        pct_exp,
        pct_both,
        pct_unexp,
        n_exp,
        n_both,
        n_unexp,
        n_fits,
    ) in enumerate(data):
        x = x_positions[i]

        # Stacked bar: green (bottom), yellow (middle), red (top)
        ax.bar(x, pct_exp, bar_width, color=COLOR_EXPECTED_ONLY, alpha=0.85)
        ax.bar(x, pct_both, bar_width, bottom=pct_exp, color=COLOR_BOTH, alpha=0.85)
        ax.bar(
            x,
            pct_unexp,
            bar_width,
            bottom=pct_exp + pct_both,
            color=COLOR_UNEXPECTED_ONLY,
            alpha=0.85,
        )

        # Label above bar showing percentage breakdown
        total_pct = pct_exp + pct_both + pct_unexp
        n_with_effect = n_exp + n_both + n_unexp
        if n_with_effect > 0:
            # Format: "exp%/both%/unexp%" or "exp%/unexp%" if both is 0
            pct_exp_of_effect = 100 * n_exp / n_with_effect
            pct_both_of_effect = 100 * n_both / n_with_effect
            pct_unexp_of_effect = 100 * n_unexp / n_with_effect
            if n_both > 0:
                label = f"{pct_exp_of_effect:.0f}%/{pct_both_of_effect:.0f}%/{pct_unexp_of_effect:.0f}%"
            else:
                label = f"{pct_exp_of_effect:.0f}%/{pct_unexp_of_effect:.0f}%"
            ax.text(
                x,
                total_pct + 1,
                label,
                ha="center",
                va="bottom",
                fontsize=8,
            )

    # X-axis labels (with line breaks for long names)
    def wrap_label(label: str) -> str:
        """Add line break to long labels."""
        if len(label) > 18 and " " in label:
            # Break at the last space before midpoint, or before "Instruction"
            if label.endswith(" Instruction"):
                return label.replace(" Instruction", "\nInstruction")
            else:
                # Break roughly in the middle
                mid = len(label) // 2
                space_idx = label.rfind(" ", 0, mid + 5)
                if space_idx > 0:
                    return label[:space_idx] + "\n" + label[space_idx + 1 :]
        return label

    labels = [wrap_label(get_param_display_name(p)) for p in ALL_PARAMS]
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)

    # Y-axis
    n_total_fits = len(df) // len(ALL_PARAMS) if len(ALL_PARAMS) > 0 else 0
    ax.set_ylabel(f"Fits with significant effect (%, n={n_total_fits})", fontsize=9)
    ax.set_ylim(0, 45)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.tick_params(axis="y", labelsize=8)

    # Dotted line separator between strategic and non-strategic factors
    separator_x = (x_positions[5] + x_positions[6]) / 2
    ax.axvline(separator_x, color="gray", linestyle=":", linewidth=1.0, alpha=0.7)

    # Grid
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)

    # Legend
    legend_elements = [
        Patch(facecolor=COLOR_EXPECTED_ONLY, alpha=0.85, label="Expected direction"),
        Patch(facecolor=COLOR_BOTH, alpha=0.85, label="Both directions"),
        Patch(
            facecolor=COLOR_UNEXPECTED_ONLY, alpha=0.85, label="Unexpected direction"
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    # Title
    ax.set_title(
        "Directions of significant effects", fontsize=10, fontweight="bold", pad=10
    )

    plt.tight_layout()
    output_path = output_dir / f"plot_12_directional_agreement{suffix}.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def print_summary_by_variation(df: pd.DataFrame) -> None:
    """Print summary statistics broken down by variation.

    For each variation, shows how often strategic factors have
    expected vs unexpected directional effects.
    """
    print("\n" + "=" * 80)
    print("SUMMARY BY VARIATION (Strategic Factors Only)")
    print("For each variation: % of (model, param) pairs with significant effects")
    print("=" * 80)

    variations = sorted(df["variation"].unique())

    # Focus on strategic parameters
    strategic_df = df[df["is_strategic"]]

    for variation in variations:
        var_df = strategic_df[strategic_df["variation"] == variation]
        n_fits = len(var_df)  # Number of (model, param) combinations

        if n_fits == 0:
            continue

        n_expected_only = (
            var_df["has_significant_expected"] & ~var_df["has_significant_unexpected"]
        ).sum()
        n_both = (
            var_df["has_significant_expected"] & var_df["has_significant_unexpected"]
        ).sum()
        n_unexpected_only = (
            var_df["has_significant_unexpected"] & ~var_df["has_significant_expected"]
        ).sum()
        n_with_effect = n_expected_only + n_both + n_unexpected_only

        if n_with_effect > 0:
            pct_expected = 100 * (n_expected_only + n_both) / n_with_effect
            pct_unexpected = 100 * (n_unexpected_only + n_both) / n_with_effect
        else:
            pct_expected = 0
            pct_unexpected = 0

        n_models = var_df["model"].nunique()
        print(
            f"{variation:25s}: {n_with_effect:3d}/{n_fits:3d} with effect | "
            f"Exp: {n_expected_only:3d}, Both: {n_both:2d}, Unexp: {n_unexpected_only:3d} | "
            f"({pct_expected:.0f}% vs {pct_unexpected:.0f}%) [{n_models} models]"
        )

    # Also print by parameter within each variation for more detail
    print("\n" + "-" * 80)
    print("DETAIL: By (variation, parameter) - showing unexpected results")
    print("-" * 80)

    for variation in variations:
        var_df = strategic_df[strategic_df["variation"] == variation]
        unexpected_params = []

        for param in STRATEGIC_PARAMS:
            param_var_df = var_df[var_df["param"] == param]
            n_fits = len(param_var_df)
            if n_fits == 0:
                continue

            n_unexpected = param_var_df["has_significant_unexpected"].sum()
            n_expected = param_var_df["has_significant_expected"].sum()

            if n_unexpected > 0:
                unexpected_params.append((param, n_unexpected, n_expected, n_fits))

        if unexpected_params:
            print(f"\n{variation}:")
            for param, n_unexp, n_exp, n_fits in unexpected_params:
                print(
                    f"  {get_param_display_name(param):20s}: {n_unexp} unexpected, {n_exp} expected (of {n_fits} models)"
                )


def print_summary(df: pd.DataFrame) -> None:
    """Print summary statistics.

    Shows for each parameter: how many (model, variation) fits showed
    at least one significant effect in expected vs unexpected direction.
    """
    print("\n" + "=" * 80)
    print("SUMMARY BY PARAMETER")
    print("% of (model, variation) pairs with ≥1 significant effect")
    print("=" * 80)

    total_expected_only = 0
    total_both = 0
    total_unexpected_only = 0
    total_fits = 0

    for param in ALL_PARAMS:
        param_df = df[df["param"] == param]
        n_fits = len(param_df)

        if n_fits == 0:
            raise ValueError(f"No data for parameter {param!r}")

        # Three mutually exclusive categories
        n_expected_only = (
            param_df["has_significant_expected"]
            & ~param_df["has_significant_unexpected"]
        ).sum()
        n_both = (
            param_df["has_significant_expected"]
            & param_df["has_significant_unexpected"]
        ).sum()
        n_unexpected_only = (
            param_df["has_significant_unexpected"]
            & ~param_df["has_significant_expected"]
        ).sum()
        n_with_effect = n_expected_only + n_both + n_unexpected_only

        total_expected_only += n_expected_only
        total_both += n_both
        total_unexpected_only += n_unexpected_only
        total_fits += n_fits

        strategic_marker = "(S)" if param in STRATEGIC_PARAMS else "(NS)"
        pct_with_effect = 100 * n_with_effect / n_fits if n_fits > 0 else 0

        print(
            f"{get_param_display_name(param):20s} {strategic_marker}: "
            f"{n_with_effect:3d}/{n_fits:3d} ({pct_with_effect:5.1f}%) | "
            f"Exp: {n_expected_only:3d}, Both: {n_both:2d}, Unexp: {n_unexpected_only:3d}"
        )

    # Overall
    print("\n" + "-" * 80)
    n_total_with_effect = total_expected_only + total_both + total_unexpected_only
    n_params = len(ALL_PARAMS)
    n_fits_per_param = total_fits // n_params if n_params > 0 else 0

    print(f"Total (model, variation) pairs: {n_fits_per_param}")
    print(
        f"Expected only: {total_expected_only}, Both: {total_both}, Unexpected only: {total_unexpected_only}"
    )
    if n_total_with_effect > 0:
        pct_exp = 100 * total_expected_only / n_total_with_effect
        pct_both = 100 * total_both / n_total_with_effect
        pct_unexp = 100 * total_unexpected_only / n_total_with_effect
        print(f"Breakdown: {pct_exp:.1f}% / {pct_both:.1f}% / {pct_unexp:.1f}%")


def create_comparison_visualization(
    df_all: pd.DataFrame,
    df_unamb: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Create side-by-side comparison of all vs unambiguous.

    Shows paired stacked bars for each parameter: all variations (solid) vs
    less ambiguous only (hatched/lighter).
    """
    from matplotlib.patches import Patch

    COLOR_EXPECTED_ONLY = "#22a559"  # Green
    COLOR_BOTH = "#f4d03f"  # Yellow
    COLOR_UNEXPECTED_ONLY = "#e74c3c"  # Red

    data_all = compute_parameter_stats(df_all)
    data_unamb = compute_parameter_stats(df_unamb)

    fig, ax = plt.subplots(figsize=(10, 4.5))

    # X positions with gap between strategic (0-5) and non-strategic (6-11)
    base_positions = list(range(6)) + [x + 0.8 for x in range(6, 12)]
    bar_width = 0.36

    for i, (
        param,
        pct_exp,
        pct_both,
        pct_unexp,
        n_exp,
        n_both,
        n_unexp,
        n_fits,
    ) in enumerate(data_all):
        x_all = base_positions[i] - bar_width / 2
        x_unamb = base_positions[i] + bar_width / 2

        # Get corresponding unambiguous data
        _, pct_exp_u, pct_both_u, pct_unexp_u, _, _, _, _ = data_unamb[i]

        # All variations: solid stacked bars
        ax.bar(x_all, pct_exp, bar_width, color=COLOR_EXPECTED_ONLY, alpha=0.85)
        ax.bar(x_all, pct_both, bar_width, bottom=pct_exp, color=COLOR_BOTH, alpha=0.85)
        ax.bar(
            x_all,
            pct_unexp,
            bar_width,
            bottom=pct_exp + pct_both,
            color=COLOR_UNEXPECTED_ONLY,
            alpha=0.85,
        )

        # Unambiguous only: hatched stacked bars (lighter)
        ax.bar(
            x_unamb,
            pct_exp_u,
            bar_width,
            color=COLOR_EXPECTED_ONLY,
            alpha=0.35,
            hatch="//",
            edgecolor="#333",
        )
        ax.bar(
            x_unamb,
            pct_both_u,
            bar_width,
            bottom=pct_exp_u,
            color=COLOR_BOTH,
            alpha=0.35,
            hatch="//",
            edgecolor="#333",
        )
        ax.bar(
            x_unamb,
            pct_unexp_u,
            bar_width,
            bottom=pct_exp_u + pct_both_u,
            color=COLOR_UNEXPECTED_ONLY,
            alpha=0.35,
            hatch="//",
            edgecolor="#333",
        )

    # X-axis labels
    def wrap_label(label: str) -> str:
        if len(label) > 18 and " " in label:
            if label.endswith(" Instruction"):
                return label.replace(" Instruction", "\nInstruction")
            else:
                mid = len(label) // 2
                space_idx = label.rfind(" ", 0, mid + 5)
                if space_idx > 0:
                    return label[:space_idx] + "\n" + label[space_idx + 1 :]
        return label

    labels = [wrap_label(get_param_display_name(p)) for p in ALL_PARAMS]
    ax.set_xticks(base_positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)

    # Y-axis
    ax.set_ylabel("Fits with significant effect (%)", fontsize=9)
    ax.set_ylim(0, 45)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.tick_params(axis="y", labelsize=8)

    # Grid
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)

    # Legend
    legend_elements = [
        Patch(facecolor=COLOR_EXPECTED_ONLY, alpha=0.85, label="Expected"),
        Patch(facecolor=COLOR_BOTH, alpha=0.85, label="Both"),
        Patch(facecolor=COLOR_UNEXPECTED_ONLY, alpha=0.85, label="Unexpected"),
        Patch(facecolor="gray", alpha=0.85, label="All environments"),
        Patch(
            facecolor="gray",
            alpha=0.35,
            hatch="//",
            edgecolor="#333",
            label="Less ambiguous only",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8, ncol=2)

    ax.set_title(
        "Directions of significant effects: all vs less ambiguous",
        fontsize=10,
        fontweight="bold",
        pad=10,
    )

    plt.tight_layout()
    output_path = output_dir / "plot_12_directional_agreement_comparison.pdf"
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate directional agreement plot")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for figures",
    )
    parser.add_argument(
        "--unambiguous",
        action="store_true",
        help="Exclude ambiguous variations (gpu_decision, hiding_reward_hacking, email_spam_filter, leak-doj)",
    )
    parser.add_argument(
        "--compare-unambiguous",
        action="store_true",
        help="Create side-by-side comparison of all vs less ambiguous",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Analyze all posteriors
    logger.info("Analyzing posteriors...")
    df_all = analyze_all_posteriors()

    if len(df_all) == 0:
        logger.error("No results found!")
        return

    if args.compare_unambiguous:
        # Load both all and unambiguous for comparison
        df_unamb = df_all[
            ~df_all["variation"].isin(UNAMBIGUOUS_EXCLUDED_VARIATIONS)
        ].copy()
        logger.info(
            f"Comparison mode: {len(df_all)} all-variation vs {len(df_unamb)} less-ambiguous"
        )
        create_comparison_visualization(df_all, df_unamb, args.output_dir)
        return

    # Filter to unambiguous variations if requested
    if args.unambiguous:
        df_all = df_all[~df_all["variation"].isin(UNAMBIGUOUS_EXCLUDED_VARIATIONS)]
        logger.info(f"Less-ambiguous mode: excluded {UNAMBIGUOUS_EXCLUDED_VARIATIONS}")

    logger.info(f"Analyzed {len(df_all)} pairwise comparisons across all posteriors")

    # Print summary
    print_summary(df_all)

    # Print variation-by-variation breakdown
    print_summary_by_variation(df_all)

    # Create visualization
    suffix = "_unambiguous" if args.unambiguous else ""
    create_visualization(df_all, args.output_dir, suffix=suffix)


if __name__ == "__main__":
    main()
