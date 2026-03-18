#!/usr/bin/env python3
"""Compute 95% credible intervals for RQ2 and RQ3 differences.

RQ2: Is unsanctioned behaviour of more capable models more strongly explained
     by strategic factors?

     Computes S_q = sum of |c'_{q, P_i}| over strategic parameters for each quartile,
     then tests S_{q+1} - S_q for q in {1,2,3}.

RQ3: Which individual factors have models become more sensitive to?

     Computes |c'_{q+1, P_i}| - |c'_{q, P_i}| for each parameter and quartile transition.

Usage:
    uv run scripts/paper/compute_rq2_rq3_cis.py
"""

import logging
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Constants
POSTERIORS_DIR = Path("paper_cache/posteriors/pooled/per-quartile")
QUARTILES = ["q1", "q2", "q3", "q4"]

# Strategic vs non-strategic parameters
STRATEGIC_PARAMS = [
    "goal_present",
    "goal_conflict",
    "threat",
    "action_oversight",
    "action_efficacy_binary",
    "cot_privacy",
]

NON_STRATEGIC_PARAMS = [
    "independence",
    "anti_misalignment",
    "reasoning_instructions",
    "filler_richness",
    "cot_tag",
    "date_month_year",
]

ALL_PARAMS = STRATEGIC_PARAMS + NON_STRATEGIC_PARAMS


def load_quartile_posteriors(quartile: str) -> dict[str, np.ndarray] | None:
    """Load posteriors for a specific quartile."""
    path = POSTERIORS_DIR / f"{quartile}.npz"
    if not path.exists():
        logger.warning(f"Missing: {path}")
        return None
    data = np.load(path)
    return {k: data[k] for k in data.files}


def get_param_effect_keys(posteriors: dict[str, np.ndarray], param: str) -> list[str]:
    """Get all effect keys for a parameter from posteriors."""
    keys = []
    for key in posteriors.keys():
        if key.startswith(f"combined_{param}_effects[") and "constrained" not in key:
            keys.append(key)
    return sorted(keys)


def extract_normalized_coefficients(
    posteriors: dict[str, np.ndarray], param: str
) -> dict[str, np.ndarray]:
    """Extract coefficients for a parameter, normalized to sum to zero.

    Returns dict mapping category -> samples array (n_samples,).
    """
    keys = get_param_effect_keys(posteriors, param)
    if not keys:
        return {}

    # Stack all category samples: shape (n_categories, n_samples)
    samples_list = [posteriors[k] for k in keys]
    stacked = np.stack(samples_list, axis=0)

    # Normalize: subtract mean across categories for each sample
    # This makes coefficients sum to zero within each posterior sample
    mean_per_sample = stacked.mean(axis=0, keepdims=True)
    normalized = stacked - mean_per_sample

    # Extract category names and build result dict
    result = {}
    for i, key in enumerate(keys):
        cat = key.split("[")[1].rstrip("]")
        result[cat] = normalized[i]

    return result


def compute_S_q(
    posteriors: dict[str, np.ndarray],
    params: list[str],
) -> np.ndarray:
    """Compute S_q = sum of |c'_{q, P_i}| over given parameters.

    Returns array of shape (n_samples,) with S_q for each posterior sample.
    """
    n_samples = None
    total = None

    for param in params:
        coeffs = extract_normalized_coefficients(posteriors, param)
        if not coeffs:
            continue

        for cat, samples in coeffs.items():
            if n_samples is None:
                n_samples = len(samples)
                total = np.zeros(n_samples)
            total += np.abs(samples)

    if total is None:
        return np.array([0.0])
    return total


def compute_ci(samples: np.ndarray) -> tuple[float, float, float]:
    """Compute posterior mean and 95% CI."""
    mean = np.mean(samples)
    lower = np.percentile(samples, 2.5)
    upper = np.percentile(samples, 97.5)
    return mean, lower, upper


def format_ci(mean: float, lower: float, upper: float) -> str:
    """Format CI as string."""
    return f"{mean:.3f} [{lower:.3f}, {upper:.3f}]"


def ci_excludes_zero(lower: float, upper: float) -> bool:
    """Check if CI excludes zero (statistically significant)."""
    return lower > 0 or upper < 0


def main():
    # Load all quartile posteriors
    all_posteriors = {}
    for q in QUARTILES:
        posteriors = load_quartile_posteriors(q)
        if posteriors is None:
            logger.error(f"Cannot proceed without {q} posteriors")
            return
        all_posteriors[q] = posteriors

    print("\n" + "=" * 70)
    print("RQ2: Strategic sensitivity by capability quartile")
    print("=" * 70)

    # Compute S_q for each quartile
    S_strategic = {}
    S_non_strategic = {}

    for q in QUARTILES:
        S_strategic[q] = compute_S_q(all_posteriors[q], STRATEGIC_PARAMS)
        S_non_strategic[q] = compute_S_q(all_posteriors[q], NON_STRATEGIC_PARAMS)

    # Report S_q values
    print("\nS_q (sum of |coefficients|) for strategic parameters:")
    for q in QUARTILES:
        mean, lower, upper = compute_ci(S_strategic[q])
        print(f"  {q.upper()}: {format_ci(mean, lower, upper)}")

    print("\nS_q for non-strategic parameters:")
    for q in QUARTILES:
        mean, lower, upper = compute_ci(S_non_strategic[q])
        print(f"  {q.upper()}: {format_ci(mean, lower, upper)}")

    # Compute and report differences S_{q+1} - S_q
    print("\n" + "-" * 70)
    print("Differences S_{q+1} - S_q (strategic):")
    print("-" * 70)

    for i in range(3):
        q_curr = QUARTILES[i]
        q_next = QUARTILES[i + 1]
        diff = S_strategic[q_next] - S_strategic[q_curr]
        mean, lower, upper = compute_ci(diff)
        sig = "*" if ci_excludes_zero(lower, upper) else ""
        print(
            f"  {q_next.upper()} - {q_curr.upper()}: {format_ci(mean, lower, upper)} {sig}"
        )

    # Overall Q4 - Q1
    diff_overall = S_strategic["q4"] - S_strategic["q1"]
    mean, lower, upper = compute_ci(diff_overall)
    sig = "*" if ci_excludes_zero(lower, upper) else ""
    print(f"  Q4 - Q1 (overall): {format_ci(mean, lower, upper)} {sig}")

    print("\nDifferences S_{q+1} - S_q (non-strategic):")
    for i in range(3):
        q_curr = QUARTILES[i]
        q_next = QUARTILES[i + 1]
        diff = S_non_strategic[q_next] - S_non_strategic[q_curr]
        mean, lower, upper = compute_ci(diff)
        sig = "*" if ci_excludes_zero(lower, upper) else ""
        print(
            f"  {q_next.upper()} - {q_curr.upper()}: {format_ci(mean, lower, upper)} {sig}"
        )

    diff_overall = S_non_strategic["q4"] - S_non_strategic["q1"]
    mean, lower, upper = compute_ci(diff_overall)
    sig = "*" if ci_excludes_zero(lower, upper) else ""
    print(f"  Q4 - Q1 (overall): {format_ci(mean, lower, upper)} {sig}")

    # Difference of differences (strategic - non-strategic trend)
    print("\n" + "-" * 70)
    print("Strategic minus Non-strategic S_q:")
    print("-" * 70)

    for q in QUARTILES:
        diff = S_strategic[q] - S_non_strategic[q]
        mean, lower, upper = compute_ci(diff)
        sig = "*" if ci_excludes_zero(lower, upper) else ""
        print(f"  {q.upper()}: {format_ci(mean, lower, upper)} {sig}")

    # Compute gap for each quartile
    gaps = {}
    for q in QUARTILES:
        gaps[q] = S_strategic[q] - S_non_strategic[q]

    # Is the gap changing between quartiles?
    print("\nGap changes between quartiles:")
    for i in range(3):
        q_curr = QUARTILES[i]
        q_next = QUARTILES[i + 1]
        gap_diff = gaps[q_next] - gaps[q_curr]
        mean, lower, upper = compute_ci(gap_diff)
        sig = "*" if ci_excludes_zero(lower, upper) else ""
        print(
            f"  {q_next.upper()} - {q_curr.upper()}: {format_ci(mean, lower, upper)} {sig}"
        )

    # Overall Q4 - Q1 gap change
    gap_change = gaps["q4"] - gaps["q1"]
    mean, lower, upper = compute_ci(gap_change)
    sig = "*" if ci_excludes_zero(lower, upper) else ""
    print(f"  Q4 - Q1 (overall): {format_ci(mean, lower, upper)} {sig}")

    print("\n" + "=" * 70)
    print("RQ3: Individual parameter sensitivity changes by quartile")
    print("=" * 70)
    print("\nFor each parameter, S_param = sum of |coefficients| across all categories")
    print("Testing whether S_param changes between quartiles.\n")

    # For each parameter, compute S_param_q = sum of |c'_{q, cat}| for all categories
    for param in ALL_PARAMS:
        is_strategic = param in STRATEGIC_PARAMS
        label = "(S)" if is_strategic else "(NS)"
        print(f"{param} {label}:")

        # Get coefficients for all quartiles
        coeffs_by_q = {}
        for q in QUARTILES:
            coeffs_by_q[q] = extract_normalized_coefficients(all_posteriors[q], param)

        if not coeffs_by_q["q1"]:
            print("  (no data)\n")
            continue

        # Get all categories
        categories = sorted(coeffs_by_q["q1"].keys())

        # Compute S_param_q = sum of |coeff| for each quartile
        S_param = {}
        for q in QUARTILES:
            n_samples = len(list(coeffs_by_q[q].values())[0])
            total = np.zeros(n_samples)
            for cat in categories:
                total += np.abs(coeffs_by_q[q].get(cat, np.zeros(n_samples)))
            S_param[q] = total

        # Report S_param for each quartile
        print("  S_param by quartile:")
        for q in QUARTILES:
            mean, lower, upper = compute_ci(S_param[q])
            print(f"    {q.upper()}: {format_ci(mean, lower, upper)}")

        # Report differences between quartiles
        print("  Changes:")
        for i in range(3):
            q_curr = QUARTILES[i]
            q_next = QUARTILES[i + 1]
            diff = S_param[q_next] - S_param[q_curr]
            mean, lower, upper = compute_ci(diff)
            sig = "*" if ci_excludes_zero(lower, upper) else ""
            print(
                f"    {q_next.upper()} - {q_curr.upper()}: {format_ci(mean, lower, upper)} {sig}"
            )

        # Overall Q4 - Q1
        diff_overall = S_param["q4"] - S_param["q1"]
        mean, lower, upper = compute_ci(diff_overall)
        sig = "*" if ci_excludes_zero(lower, upper) else ""
        print(f"    Q4 - Q1 (overall): {format_ci(mean, lower, upper)} {sig}")
        print()

    print("\n" + "=" * 70)
    print("Legend: * = 95% CI excludes zero (statistically significant)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
