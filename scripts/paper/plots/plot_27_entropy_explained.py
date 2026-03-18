#!/usr/bin/env python3
"""Plot 27: Fraction of entropy explained for all entropy targets.

Creates a combined plot showing C/I(X;Y) - the fraction of mutual information
(entropy) explained by the combined model - for each of the 8 entropy targets.

Usage:
    uv run scripts/paper/plots/plot_27_entropy_explained.py
    uv run scripts/paper/plots/plot_27_entropy_explained.py --output-dir paper_cache/figures
    uv run scripts/paper/plots/plot_27_entropy_explained.py --refresh  # Re-download from S3
"""

import json
import logging
import os
from pathlib import Path

import fire
import matplotlib.pyplot as plt
import numpy as np

from lib.analysis.entropy import binary_entropy
from lib.paper_style import get_model_display_name

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ENTROPY_CACHE_DIR = Path("paper_cache/entropy_samples")
SINGLE_EXTRAS_DIR = Path("paper_cache/posteriors/pooled/single_extras")
SINGLE_DIR = Path("paper_cache/posteriors/pooled/single")


def model_id_to_slug(model_id: str) -> str:
    """Convert model ID to filesystem-safe slug."""
    return model_id.replace("/", "_").replace(":", "_")


# 8 (model, scenario, variation) targets for entropy estimation
ENTROPY_TARGETS = [
    ("anthropic/claude-3-5-haiku-20241022", "agentic_misalignment_v2", "alert"),
    (
        "anthropic/claude-sonnet-4-5-20250929",
        "gpu_decision_email_assistant",
        "gpu_decision",
    ),
    (
        "openrouter/google/gemini-2.5-flash",
        "agentic_misalignment_v2",
        "leak-starsentinel",
    ),
    ("openrouter/google/gemini-2.5-pro", "agentic_misalignment_v2", "leak-doj"),
    ("openrouter/meta-llama/llama-3.3-70b-instruct", "sem_v2", "summarization"),
    ("openrouter/meta-llama/llama-4-scout", "sem_v2", "classification"),
    (
        "openrouter/openai/gpt-oss-120b",
        "hiding_reward_hacking",
        "hiding_reward_hacking",
    ),
    ("openai/o4-mini-2025-04-16", "email_spam_filter_v2", "email_spam_filter"),
]


def load_posterior_fit(
    model: str,
    variation: str,
    posteriors_dir: Path = SINGLE_EXTRAS_DIR,
) -> tuple[dict, dict]:
    """Load posterior NPZ and summary JSON for a (model, variation) pair.

    Args:
        model: Model ID (e.g., "anthropic/claude-3-5-haiku-20241022")
        variation: Variation name (e.g., "alert")
        posteriors_dir: Directory containing the posteriors (default: single_extras)

    Returns:
        Tuple of (posteriors dict, summary dict)
    """
    slug = model_id_to_slug(model)
    item_id = f"{slug}_{variation}"

    npz_path = posteriors_dir / f"{item_id}.npz"
    json_path = posteriors_dir / f"{item_id}.json"

    if not npz_path.exists():
        raise FileNotFoundError(f"Posterior not found: {npz_path}")

    posteriors = dict(np.load(npz_path))

    with open(json_path) as f:
        summary = json.load(f)

    return posteriors, summary


def load_entropy_from_cache(model: str, variation: str) -> dict:
    """Load entropy summary from local cache."""
    model_slug = model.replace("/", "_").replace(":", "_")
    cache_file = ENTROPY_CACHE_DIR / f"{model_slug}_{variation}.json"

    if not cache_file.exists():
        raise FileNotFoundError(
            f"No cached entropy for {model} / {variation}: {cache_file}\n"
            f"Run: uv run scripts/entropy/estimate_entropy.py run-samples ..."
        )

    with open(cache_file) as f:
        return json.load(f)


def compute_entropy_stats(
    model: str,
    variation: str,
    scenario: str,
    posteriors_dir: Path = SINGLE_EXTRAS_DIR,
) -> dict:
    """Compute entropy statistics for a single target.

    Args:
        model: Model ID
        variation: Variation name
        scenario: Scenario name
        posteriors_dir: Directory containing the posteriors

    Raises:
        FileNotFoundError: If entropy cache or posteriors are missing
        ValueError: If data is invalid
    """
    cached = load_entropy_from_cache(model, variation)

    k_values = np.array(cached["k_values"])
    n_values = np.array(cached["n_values"])
    H_Y_given_X = cached["H_Y_given_X"]
    H_Y_given_X_ci = cached.get("H_Y_given_X_ci")  # May be None for old cache files
    total_samples = cached["total_samples"]
    total_successes = int(np.sum(k_values))

    # Load posterior fit from specified directory
    posteriors, summary = load_posterior_fit(model, variation, posteriors_dir)

    # Compute H(Y) from entropy sampling base rate (not full dataset)
    # This ensures consistency: H_Y and H_Y_given_X from same data
    entropy_base_rate = cached["base_rate"]
    H_Y = binary_entropy(entropy_base_rate)

    # Also get full dataset base rate for reference
    full_dataset_base_rate = summary.get(
        "misalignment_rate", total_successes / total_samples
    )

    # Compute I(X;Y)
    I_XY = H_Y - H_Y_given_X

    # Get C distribution and normalize
    n_data = summary.get("n_samples", total_samples)
    C_distribution = posteriors.get("C_distribution", np.array([]))

    if len(C_distribution) == 0:
        raise ValueError(f"Empty C_distribution for {model} / {variation}")

    # Generate I(X;Y) posterior samples to propagate entropy estimation uncertainty
    # Use same empirical Bayes approach as estimate_entropy.py
    # IMPORTANT: Compute both H(Y) and H(Y|X) from same sampled p values to ensure I(X;Y) >= 0
    # Set seed for reproducibility
    np.random.seed(42)

    n_draws = len(C_distribution)
    p_hat = k_values / n_values
    mean_p = np.mean(p_hat)
    var_p = np.var(p_hat)

    if var_p < 1e-8:
        alpha, beta_param = 1.0, 1.0
    else:
        s = mean_p * (1 - mean_p) / var_p - 1
        if s <= 0:
            alpha, beta_param = 1.0, 1.0
        else:
            alpha = max(0.1, min(mean_p * s, 100.0))
            beta_param = max(0.1, min((1 - mean_p) * s, 100.0))

    # Sample I(X;Y) distribution by computing both H(Y) and H(Y|X) from same p samples
    # This ensures I(X;Y) >= 0 (information-theoretic constraint)
    n_configs = len(k_values)
    I_XY_draws = np.zeros(n_draws)
    for draw in range(n_draws):
        p_samples = np.zeros(n_configs)
        config_entropies = np.zeros(n_configs)
        for i, (k, n) in enumerate(zip(k_values, n_values)):
            post_a = alpha + k
            post_b = beta_param + (n - k)
            p_samples[i] = np.random.beta(post_a, post_b)
            config_entropies[i] = binary_entropy(p_samples[i])

        # H(Y|X) = average of per-config entropies
        H_Y_given_X_draw = np.mean(config_entropies)

        # H(Y) = entropy of marginal (weighted average of p_i)
        marginal_p = np.sum(n_values * p_samples) / np.sum(n_values)
        H_Y_draw = binary_entropy(marginal_p)

        I_XY_draws[draw] = H_Y_draw - H_Y_given_X_draw

    # Normalize C by I(X;Y), propagating both uncertainties
    # Each C draw is paired with a corresponding I(X;Y) draw
    normalization_factors = n_data * I_XY_draws * np.log(2)

    # Handle cases where I(X;Y) might be negative or zero for some draws
    valid_mask = normalization_factors > 0
    if not np.any(valid_mask):
        raise ValueError(
            f"All normalization_factors non-positive for {model} / {variation}: "
            f"n_data={n_data}, I_XY={I_XY:.4f}, H_Y={H_Y:.4f}, H_Y_given_X={H_Y_given_X:.4f}"
        )

    # Compute C_normalized only for valid draws
    C_normalized_combined = np.full(n_draws, np.nan)
    C_normalized_combined[valid_mask] = (
        C_distribution[valid_mask] / normalization_factors[valid_mask]
    )

    # Also compute C_normalized with point estimate I(X;Y) for comparison
    normalization_factor_point = n_data * I_XY * np.log(2)
    if normalization_factor_point <= 0:
        raise ValueError(
            f"Non-positive normalization_factor for {model} / {variation}: "
            f"n_data={n_data}, I_XY={I_XY:.4f}, H_Y={H_Y:.4f}, H_Y_given_X={H_Y_given_X:.4f}"
        )
    C_normalized_point = C_distribution / normalization_factor_point

    # Use combined CI (propagating entropy uncertainty)
    valid_combined = C_normalized_combined[~np.isnan(C_normalized_combined)]

    return {
        "model": model,
        "variation": variation,
        "scenario": scenario,
        "H_Y": H_Y,
        "H_Y_given_X": H_Y_given_X,
        "H_Y_given_X_ci": H_Y_given_X_ci,
        "I_XY": I_XY,
        "C_normalized": C_normalized_point,  # Point estimate normalization
        "C_norm_mean": float(np.mean(C_normalized_point)),
        "C_norm_median": float(np.median(C_normalized_point)),
        "C_norm_ci": (
            float(np.percentile(C_normalized_point, 2.5)),
            float(np.percentile(C_normalized_point, 97.5)),
        ),
        # Combined CI propagating entropy uncertainty
        "C_norm_ci_combined": (
            float(np.percentile(valid_combined, 2.5)),
            float(np.percentile(valid_combined, 97.5)),
        )
        if len(valid_combined) > 0
        else (np.nan, np.nan),
        "n_entropy_configs": len(k_values),
        "n_entropy_samples": total_samples,
        "entropy_base_rate": entropy_base_rate,
        "full_dataset_base_rate": full_dataset_base_rate,
        "frac_valid_draws": float(np.sum(valid_mask) / n_draws),
    }


def plot(
    output_dir: str = "paper_cache/figures",
    show_plot: bool = False,
    compare: bool = False,
) -> None:
    """Create entropy explained plot for all targets.

    Uses locally cached entropy summaries from paper_cache/entropy_samples/.
    Run estimate_entropy.py first to populate the cache.

    Args:
        output_dir: Directory for output plots.
        show_plot: Whether to display the plot interactively.
        compare: If True, show side-by-side comparison of extras vs non-extras GLMs.
    """
    from lib.paper_style import (
        FIG_WIDTH_DOUBLE,
        FONTSIZE_AXIS_LABEL,
        FONTSIZE_TICK,
        FONTSIZE_TITLE,
        get_model_color,
        get_variation_display_name,
        setup_style,
    )

    setup_style()

    # Sync entropy cache from S3 if not present locally
    if not ENTROPY_CACHE_DIR.exists() or not list(ENTROPY_CACHE_DIR.glob("*.json")):
        import subprocess

        _bucket = os.environ.get("S3_BUCKET", "")
        _root = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
        s3_src = f"s3://{_bucket}/{_root}/paper_cache/entropy_samples/"
        logger.info(f"Entropy cache not found locally, syncing from S3: {s3_src}")
        ENTROPY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["aws", "s3", "sync", s3_src, str(ENTROPY_CACHE_DIR)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                f"Failed to sync entropy cache from S3: {result.stderr}\n"
                f"Run estimate_entropy.py to populate the cache, or sync manually.\n"
                f"Skipping plot_27."
            )
            return
        logger.info(f"Synced entropy cache to {ENTROPY_CACHE_DIR}")

    logger.info(f"Processing {len(ENTROPY_TARGETS)} entropy targets...")

    # Compute stats for each target (extras GLM)
    results_extras = []
    for model, scenario, variation in ENTROPY_TARGETS:
        logger.info(f"  {model} / {variation} (extras)...")
        stats = compute_entropy_stats(
            model=model,
            variation=variation,
            scenario=scenario,
            posteriors_dir=SINGLE_EXTRAS_DIR,
        )
        results_extras.append(stats)

    logger.info(
        f"\nGot extras results for {len(results_extras)}/{len(ENTROPY_TARGETS)} targets"
    )

    # If comparing, also compute stats for non-extras GLM
    results_standard = []
    if compare:
        for model, scenario, variation in ENTROPY_TARGETS:
            logger.info(f"  {model} / {variation} (standard)...")
            stats = compute_entropy_stats(
                model=model,
                variation=variation,
                scenario=scenario,
                posteriors_dir=SINGLE_DIR,
            )
            results_standard.append(stats)
        logger.info(
            f"Got standard results for {len(results_standard)}/{len(ENTROPY_TARGETS)} targets"
        )

    # Sort by extras C_norm_mean descending (highest first)
    results_extras.sort(key=lambda x: x["C_norm_mean"], reverse=True)

    # Create lookup for standard results
    standard_lookup = {}
    if compare:
        for r in results_standard:
            key = (r["model"], r["variation"])
            standard_lookup[key] = r

    # Create figure
    n_results = len(results_extras)
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_DOUBLE, 4.5))

    x_positions = np.arange(n_results)
    colors = [get_model_color(r["model"]) for r in results_extras]

    if compare:
        # Paired bar chart (like plot 21 baseline comparison)
        bar_width = 0.35

        # Get extras data
        extras_means = [r["C_norm_mean"] for r in results_extras]
        extras_ci_lows = [r["C_norm_ci_combined"][0] for r in results_extras]
        extras_ci_highs = [r["C_norm_ci_combined"][1] for r in results_extras]

        # Get standard data (matching by model/variation)
        standard_means = []
        standard_ci_lows = []
        standard_ci_highs = []
        for r in results_extras:
            key = (r["model"], r["variation"])
            if key in standard_lookup:
                std_r = standard_lookup[key]
                standard_means.append(std_r["C_norm_mean"])
                standard_ci_lows.append(std_r["C_norm_ci_combined"][0])
                standard_ci_highs.append(std_r["C_norm_ci_combined"][1])
            else:
                standard_means.append(np.nan)
                standard_ci_lows.append(np.nan)
                standard_ci_highs.append(np.nan)

        # Plot extras bars (left) - solid
        ax.bar(
            x_positions - bar_width / 2,
            extras_means,
            bar_width,
            color=colors,
            alpha=0.8,
            edgecolor="black",
            linewidth=0.5,
            label="With extras",
        )

        # Error bars for extras
        yerr_lower = [max(0, m - ci_l) for m, ci_l in zip(extras_means, extras_ci_lows)]
        yerr_upper = [ci_h - m for m, ci_h in zip(extras_means, extras_ci_highs)]
        ax.errorbar(
            x_positions - bar_width / 2,
            extras_means,
            yerr=[yerr_lower, yerr_upper],
            fmt="none",
            color="black",
            capsize=2,
            linewidth=0.8,
        )

        # Plot standard bars (right) - hatched
        ax.bar(
            x_positions + bar_width / 2,
            standard_means,
            bar_width,
            color=colors,
            alpha=0.4,
            edgecolor="black",
            linewidth=0.5,
            hatch="//",
            label="Standard (12 params)",
        )

        # Error bars for standard
        yerr_lower_std = [
            max(0, m - ci_l) if not np.isnan(m) else 0
            for m, ci_l in zip(standard_means, standard_ci_lows)
        ]
        yerr_upper_std = [
            ci_h - m if not np.isnan(m) else 0
            for m, ci_h in zip(standard_means, standard_ci_highs)
        ]
        ax.errorbar(
            x_positions + bar_width / 2,
            standard_means,
            yerr=[yerr_lower_std, yerr_upper_std],
            fmt="none",
            color="black",
            capsize=2,
            linewidth=0.8,
        )

        # Legend
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(
                facecolor="gray",
                alpha=0.8,
                edgecolor="black",
                linewidth=0.5,
                label="With extras",
            ),
            Patch(
                facecolor="gray",
                alpha=0.4,
                edgecolor="black",
                linewidth=0.5,
                hatch="//",
                label="Standard (12 params)",
            ),
        ]
        ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

        title = "Fraction of entropy explained: extras vs. standard GLM"

    else:
        # Single bar chart (original behavior)
        means = [r["C_norm_mean"] for r in results_extras]
        ci_lows = [r["C_norm_ci_combined"][0] for r in results_extras]
        ci_highs = [r["C_norm_ci_combined"][1] for r in results_extras]

        # Plot bars
        ax.bar(
            x_positions,
            means,
            color=colors,
            alpha=0.7,
            edgecolor="black",
            linewidth=0.5,
        )

        # Error bars (95% CI)
        yerr_lower = [max(0, m - ci_l) for m, ci_l in zip(means, ci_lows)]
        yerr_upper = [ci_h - m for m, ci_h in zip(means, ci_highs)]
        ax.errorbar(
            x_positions,
            means,
            yerr=[yerr_lower, yerr_upper],
            fmt="none",
            color="black",
            capsize=3,
            linewidth=1,
        )

        title = "Fraction of mutual information explained by GLM"

    # Reference lines
    ax.axhline(0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

    # Labels
    labels = [
        f"{get_model_display_name(r['model'])}\n({get_variation_display_name(r['scenario'], r['variation'])})"
        for r in results_extras
    ]
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=FONTSIZE_TICK - 1)

    ax.set_ylabel("Fraction of entropy explained", fontsize=FONTSIZE_AXIS_LABEL)
    ax.set_title(title, fontsize=FONTSIZE_TITLE, fontweight="bold")

    # Y-axis as percentages, starting from 0
    ax.set_ylim(0, 1.3)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0, 1.25])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%", "125%"])

    plt.tight_layout()

    # Save
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if compare:
        plot_path_pdf = output_path / "plot_27_entropy_explained_comparison.pdf"
        plot_path_png = output_path / "plot_27_entropy_explained_comparison.png"
    else:
        plot_path_pdf = output_path / "plot_27_entropy_explained.pdf"
        plot_path_png = output_path / "plot_27_entropy_explained.png"

    plt.savefig(plot_path_pdf, dpi=300, bbox_inches="tight", facecolor="white")
    plt.savefig(plot_path_png, dpi=300, bbox_inches="tight", facecolor="white")
    logger.info(f"Saved: {plot_path_pdf}")
    logger.info(f"Saved: {plot_path_png}")

    # Print summary table
    print("\n" + "=" * 100)
    if compare:
        print("Fraction of Mutual Information Explained: Extras vs. Standard GLM")
        print("=" * 100)
        print(
            f"{'Model':<22} {'Variation':<18} {'Extras':<10} {'Standard':<10} {'Diff':<10} {'% Gain'}"
        )
        print("-" * 100)
        for r in results_extras:
            model_short = get_model_display_name(r["model"])
            key = (r["model"], r["variation"])
            extras_mean = r["C_norm_mean"]
            if key in standard_lookup:
                std_mean = standard_lookup[key]["C_norm_mean"]
                diff = extras_mean - std_mean
                pct_gain = (diff / std_mean * 100) if std_mean > 0 else 0
                print(
                    f"{model_short:<22} {r['variation']:<18} "
                    f"{extras_mean:<10.1%} {std_mean:<10.1%} "
                    f"{diff:>+8.1%}   {pct_gain:>+6.1f}%"
                )
            else:
                print(
                    f"{model_short:<22} {r['variation']:<18} {extras_mean:<10.1%} {'N/A':<10}"
                )
        print("=" * 100)

        # Summary statistics
        extras_means = [r["C_norm_mean"] for r in results_extras]
        standard_means_valid = [
            standard_lookup[(r["model"], r["variation"])]["C_norm_mean"]
            for r in results_extras
            if (r["model"], r["variation"]) in standard_lookup
        ]
        print(f"\nExtras mean:   {np.mean(extras_means):.1%}")
        print(f"Standard mean: {np.mean(standard_means_valid):.1%}")
        print(
            f"Difference:    {np.mean(extras_means) - np.mean(standard_means_valid):+.1%}"
        )

    else:
        print("Fraction of Mutual Information Explained by GLM")
        print("=" * 100)
        print(
            f"{'Model':<22} {'Variation':<22} {'Mean':<8} {'95% CI':<20} {'n configs'}"
        )
        print("-" * 100)
        for r in results_extras:
            model_short = get_model_display_name(r["model"])
            ci_combined = r.get("C_norm_ci_combined", (np.nan, np.nan))
            if np.isnan(ci_combined[0]):
                ci_str = "N/A"
            else:
                ci_str = f"[{ci_combined[0]:.1%}, {ci_combined[1]:.1%}]"
            n_cfg = r.get("n_entropy_configs", "?")
            print(
                f"{model_short:<22} {r['variation']:<22} {r['C_norm_mean']:<8.1%} {ci_str:<20} {n_cfg}"
            )
        print("=" * 100)

        # Summary statistics
        means = [r["C_norm_mean"] for r in results_extras]
        print(f"\nMean across targets: {np.mean(means):.1%}")
        print(f"Median: {np.median(means):.1%}")
        print(f"Range: [{min(means):.1%}, {max(means):.1%}]")

    if show_plot:
        plt.show()
    else:
        plt.close()


if __name__ == "__main__":
    fire.Fire(plot)
