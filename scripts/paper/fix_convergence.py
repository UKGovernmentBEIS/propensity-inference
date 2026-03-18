#!/usr/bin/env python3
"""Fix convergence issues by filtering to converged chains.

This script:
1. Finds posterior fits with convergence issues
2. Identifies which chains converged together (R-hat < threshold)
3. Creates new files with only converged chain samples
4. Backs up originals and replaces with fixed versions

Usage:
    uv run scripts/paper/fix_convergence.py --dry-run  # Preview what would be done
    uv run scripts/paper/fix_convergence.py            # Actually fix files
"""

import json
import shutil
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import fire
import numpy as np

# Threshold for considering chains as converged
RHAT_THRESHOLD = 1.05
# Threshold for "major" convergence issues that need fixing
MAJOR_RHAT_THRESHOLD = 1.3
# Minimum number of converged chains required
MIN_CONVERGED_CHAINS = 2
# Number of chains used in fitting (standard)
N_CHAINS = 4
# Tolerance for "best mode" check (fraction of log-likelihood range)
BEST_MODE_TOLERANCE_FRACTION = 0.01
# Minimum tolerance for "best mode" check (absolute log-likelihood units)
BEST_MODE_TOLERANCE_MIN = 10.0


@dataclass
class PerModelConvergence:
    """Convergence info for a single GLM type."""

    key: str
    converged_chains: list[int]
    rhat: float
    is_best_mode: bool
    chain_means: list[float]


@dataclass
class ChainAnalysis:
    """Results of analyzing chain convergence."""

    fit_path: Path
    npz_path: Path
    original_convergence_ok: bool
    original_issues: list[str]
    chain_means: dict[str, list[float]]  # key -> [chain1_mean, chain2_mean, ...]
    per_model_convergence: dict[str, PerModelConvergence]  # key -> convergence info
    n_samples_original: int
    can_fix: bool
    reason: str


def compute_rhat(chains: list[np.ndarray]) -> float:
    """Compute R-hat for a list of chain samples."""
    if len(chains) < 2:
        return 1.0

    n = len(chains[0])

    # Chain means and overall mean
    chain_means = np.array([c.mean() for c in chains])

    # Between-chain variance
    B = n * np.var(chain_means, ddof=1)

    # Within-chain variance
    W = np.mean([np.var(c, ddof=1) for c in chains])

    if W == 0:
        return 1.0 if B == 0 else float("inf")

    # Pooled variance estimate
    var_plus = ((n - 1) / n) * W + (1 / n) * B

    # R-hat
    rhat = np.sqrt(var_plus / W)
    return rhat


def find_converged_chains(
    samples: np.ndarray, n_chains: int = N_CHAINS
) -> tuple[list[int], float, bool]:
    """Find the largest subset of chains that converge together at the best mode.

    Args:
        samples: Flattened samples (concatenated chains), assumed to be log-likelihoods
        n_chains: Number of chains

    Returns:
        (list of converged chain indices, R-hat of those chains, is_best_mode)
    """
    draws_per_chain = len(samples) // n_chains
    chains = [
        samples[i * draws_per_chain : (i + 1) * draws_per_chain]
        for i in range(n_chains)
    ]
    chain_means = [c.mean() for c in chains]

    # Try all subsets of size >= MIN_CONVERGED_CHAINS, largest first
    best_subset = []
    best_rhat = float("inf")

    for size in range(n_chains, MIN_CONVERGED_CHAINS - 1, -1):
        for subset in combinations(range(n_chains), size):
            subset_chains = [chains[i] for i in subset]
            rhat = compute_rhat(subset_chains)
            if rhat < RHAT_THRESHOLD:
                # Found a converged subset
                if len(subset) > len(best_subset) or (
                    len(subset) == len(best_subset) and rhat < best_rhat
                ):
                    best_subset = list(subset)
                    best_rhat = rhat

        # If we found a good subset at this size, don't look for smaller ones
        if best_subset and len(best_subset) == size:
            break

    if not best_subset:
        return [], float("inf"), False

    # Check if converged chains are at the best mode (highest log-likelihood)
    converged_mean = np.mean([chain_means[i] for i in best_subset])
    best_chain_mean = max(chain_means)

    # The converged chains should be at or near the best log-likelihood
    # Allow some tolerance (within 1% of range, or 10 loglik units)
    loglik_range = max(chain_means) - min(chain_means)
    tolerance = max(
        BEST_MODE_TOLERANCE_FRACTION * loglik_range, BEST_MODE_TOLERANCE_MIN
    )

    is_best_mode = converged_mean >= (best_chain_mean - tolerance)

    return best_subset, best_rhat, is_best_mode


# Mapping from issue model type to npz key
MODEL_TYPE_TO_KEY = {
    "strategic_only": "strategic_logliks",
    "non_strategic_only": "non_strategic_logliks",
    "combined": "combined_logliks",
    "trivial": "trivial_logliks",
}


def analyze_fit(json_path: Path) -> ChainAnalysis | None:
    """Analyze a single fit for convergence issues.

    Each GLM type (strategic, non_strategic, combined, trivial) is an independent
    MCMC fit, so we analyze and filter each one independently.

    Returns:
        ChainAnalysis if the fit has convergence issues to analyze,
        None if the fit is already converged (nothing to do).

    Raises:
        FileNotFoundError: If the corresponding .npz file doesn't exist.
    """
    npz_path = json_path.with_suffix(".npz")

    if not npz_path.exists():
        raise FileNotFoundError(
            f"Missing npz file for {json_path}: expected {npz_path}"
        )

    with open(json_path) as f:
        metadata = json.load(f)

    convergence_ok = metadata.get("convergence_ok", True)
    convergence_issues = metadata.get("convergence_issues", [])

    # Skip if already converged - this is not an error, just nothing to do
    if convergence_ok:
        return None

    # Separate divergence-only issues from R-hat issues.
    # Divergences are per-transition (not per-chain) and a small number (e.g. 1)
    # is negligible. These are NOT fixable by chain filtering - they are marked
    # convergence_ok=true separately. See _is_benign_divergence_issue().
    divergence_only_issues = []
    rhat_issues = []
    for issue in convergence_issues:
        if "R-hat=" not in issue:
            if _is_benign_divergence_issue(issue):
                divergence_only_issues.append(issue)
            else:
                raise ValueError(f"Unrecognized convergence issue format: {issue!r}")
        else:
            rhat_issues.append(issue)

    # If ALL issues are benign divergences, return a special marker
    if divergence_only_issues and not rhat_issues:
        return ChainAnalysis(
            fit_path=json_path,
            npz_path=npz_path,
            original_convergence_ok=convergence_ok,
            original_issues=convergence_issues,
            chain_means={},
            per_model_convergence={},
            n_samples_original=0,
            can_fix=False,
            reason="DIVERGENCE_ONLY",
        )

    # Check if R-hat issues are major (R-hat > threshold)
    major_issues = []
    for issue in rhat_issues:
        rhat = _get_rhat(issue)  # Will raise if parsing fails
        if rhat > MAJOR_RHAT_THRESHOLD:
            major_issues.append(issue)

    if not major_issues:
        return ChainAnalysis(
            fit_path=json_path,
            npz_path=npz_path,
            original_convergence_ok=convergence_ok,
            original_issues=convergence_issues,
            chain_means={},
            per_model_convergence={},
            n_samples_original=0,
            can_fix=False,
            reason="Only minor convergence issues (R-hat < 1.5)",
        )

    # Load samples
    data = np.load(npz_path)

    # Determine which keys to check based on which models have issues
    keys_to_check = []
    for issue in major_issues:
        # Issue format: 'strategic_only: R-hat=3.040 > 1.01'
        model_type = issue.split(":")[0]
        if model_type not in MODEL_TYPE_TO_KEY:
            raise ValueError(f"Unknown model type {model_type!r} from issue: {issue!r}")
        key = MODEL_TYPE_TO_KEY[model_type]
        if key not in data:
            raise ValueError(
                f"Expected key {key!r} not found in npz for issue: {issue!r}"
            )
        if key not in keys_to_check:
            keys_to_check.append(key)

    # Get first key for sample count (keys_to_check is guaranteed non-empty here)
    first_key = keys_to_check[0]
    samples = data[first_key]
    n_samples = len(samples)
    draws_per_chain = n_samples // N_CHAINS

    # Get chain means for reporting
    chain_means = {}
    for key in data.keys():
        arr = data[key]
        if arr.shape == (n_samples,):
            means = [
                arr[i * draws_per_chain : (i + 1) * draws_per_chain].mean()
                for i in range(N_CHAINS)
            ]
            chain_means[key] = means

    # Analyze convergence for EACH problematic model type INDEPENDENTLY
    # (They are separate MCMC fits, so chain indices are unrelated across models)
    per_model_convergence = {}
    all_fixable = True
    unfixable_reasons = []

    for key in keys_to_check:
        key_samples = data[key]
        converged, rhat, is_best = find_converged_chains(key_samples)

        per_model_convergence[key] = PerModelConvergence(
            key=key,
            converged_chains=converged,
            rhat=rhat,
            is_best_mode=is_best,
            chain_means=chain_means.get(key, []),
        )

        if len(converged) < MIN_CONVERGED_CHAINS:
            all_fixable = False
            unfixable_reasons.append(f"{key}: only {len(converged)} chains converge")
        elif not is_best:
            all_fixable = False
            unfixable_reasons.append(f"{key}: converged chains not at best mode")

    if not all_fixable:
        return ChainAnalysis(
            fit_path=json_path,
            npz_path=npz_path,
            original_convergence_ok=convergence_ok,
            original_issues=convergence_issues,
            chain_means=chain_means,
            per_model_convergence=per_model_convergence,
            n_samples_original=n_samples,
            can_fix=False,
            reason="; ".join(unfixable_reasons),
        )

    # Build summary of what will be fixed
    fix_summary = ", ".join(
        f"{k}: keep {info.converged_chains}"
        for k, info in per_model_convergence.items()
    )

    return ChainAnalysis(
        fit_path=json_path,
        npz_path=npz_path,
        original_convergence_ok=convergence_ok,
        original_issues=convergence_issues,
        chain_means=chain_means,
        per_model_convergence=per_model_convergence,
        n_samples_original=n_samples,
        can_fix=True,
        reason=fix_summary,
    )


# Maximum number of divergent transitions per model type to consider benign.
# With 2000 samples x 4 chains = 8000 post-warmup transitions, 10 divergences
# is ~0.1% which is well below the standard 1% concern threshold.
MAX_BENIGN_DIVERGENCES = 10


def _is_benign_divergence_issue(issue_str: str) -> bool:
    """Check if a convergence issue is a benign divergence report.

    Matches strings like 'trivial: 1 divergences' or 'combined: 3 divergences'.
    These are per-transition issues (not per-chain), so chain filtering cannot
    help. A small number of divergences is negligible and these fits are marked
    convergence_ok=true without modifying the posterior samples.

    Raises:
        ValueError: If the divergence count exceeds MAX_BENIGN_DIVERGENCES.
    """
    if "divergences" not in issue_str or "R-hat=" in issue_str:
        return False

    # Parse the count and reject if too many
    try:
        n_div = int(issue_str.split(":")[1].strip().split()[0])
    except (IndexError, ValueError):
        raise ValueError(f"Failed to parse divergence count from: {issue_str!r}")

    if n_div > MAX_BENIGN_DIVERGENCES:
        raise ValueError(
            f"Too many divergences to ignore ({n_div} > {MAX_BENIGN_DIVERGENCES}): {issue_str!r}. "
            f"This fit needs investigation."
        )

    return True


def _get_rhat(issue_str: str) -> float:
    """Extract R-hat value from issue string like 'strategic_only: R-hat=3.040 > 1.01'.

    Raises:
        ValueError: If R-hat value cannot be parsed from the string.
    """
    if "R-hat=" not in issue_str:
        raise ValueError(f"No R-hat value found in issue string: {issue_str!r}")
    try:
        rhat_part = issue_str.split("R-hat=")[1].split()[0]
        return float(rhat_part)
    except (IndexError, ValueError) as e:
        raise ValueError(
            f"Failed to parse R-hat from issue string: {issue_str!r}"
        ) from e


def _get_glm_type_for_key(key: str) -> str:
    """Determine which GLM type an npz key belongs to.

    Returns:
        One of: 'strategic', 'non_strategic', 'combined', 'trivial', 'derived'.

    Raises:
        ValueError: If the key doesn't match any known GLM type.
    """
    if key.startswith("strategic_"):
        return "strategic"
    elif key.startswith("non_strategic_"):
        return "non_strategic"
    elif key.startswith("combined_"):
        return "combined"
    elif key.startswith("trivial_"):
        return "trivial"
    elif key in (
        "A_distribution",
        "B_distribution",
        "C_distribution",
        "RQ1_distribution",
        "S_distribution",
        "NS_distribution",
    ):
        # These are derived from multiple models or from combined coefficients.
        # S/NS are sum(|combined_*_effects|) so they depend on the combined model.
        return "derived"
    else:
        raise ValueError(f"Unknown npz key type: {key!r}")


def fix_fit(analysis: ChainAnalysis, dry_run: bool = True) -> tuple[bool, str | None]:
    """Fix a fit by filtering to converged chains per GLM type.

    Each GLM type (strategic, non_strategic, combined, trivial) is filtered
    independently since they are separate MCMC fits.

    Returns:
        (success, error_message) - success is True if fix was applied
        (or would be applied in dry run), error_message is None on success.
    """
    if not analysis.can_fix:
        return False, analysis.reason

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Fixing {analysis.fit_path.name}")
    print(f"  Original issues: {analysis.original_issues}")
    for key, info in analysis.per_model_convergence.items():
        print(
            f"  {key}: keeping chains {info.converged_chains} (R-hat={info.rhat:.3f})"
        )

    if dry_run:
        return True, None

    try:
        # Load original data
        data = dict(np.load(analysis.npz_path))
        n_samples = analysis.n_samples_original
        draws_per_chain = n_samples // N_CHAINS

        # Map GLM type to loglik key for chain selection
        glm_to_loglik_key = {
            "strategic": "strategic_logliks",
            "non_strategic": "non_strategic_logliks",
            "combined": "combined_logliks",
            "trivial": "trivial_logliks",
        }

        # Build mapping of which chains to keep for each GLM type
        chains_to_keep: dict[str, list[int]] = {}
        for loglik_key, info in analysis.per_model_convergence.items():
            # Find the GLM type for this loglik key
            for glm_type, expected_key in glm_to_loglik_key.items():
                if expected_key == loglik_key:
                    chains_to_keep[glm_type] = info.converged_chains
                    break

        # For GLM types without issues, keep all chains
        for glm_type in ["strategic", "non_strategic", "combined", "trivial"]:
            if glm_type not in chains_to_keep:
                chains_to_keep[glm_type] = list(range(N_CHAINS))

        # Filter each model independently using its converged chains
        # (Models are fit independently, so chain indices have no cross-model semantics)
        filtered_data = {}
        samples_per_model: dict[str, int] = {}

        for key, arr in data.items():
            if arr.shape != (n_samples,):
                raise ValueError(
                    f"Unexpected array shape for {key!r}: {arr.shape}, expected ({n_samples},)"
                )

            glm_type = _get_glm_type_for_key(key)  # Raises if unknown

            # Skip derived quantities - we'll recompute them after resampling
            if glm_type == "derived":
                continue

            chains = chains_to_keep[glm_type]
            filtered = np.concatenate(
                [arr[i * draws_per_chain : (i + 1) * draws_per_chain] for i in chains]
            )
            filtered_data[key] = filtered
            samples_per_model[glm_type] = len(filtered)

        # Report per-model sample counts
        for glm_type in ["strategic", "non_strategic", "combined", "trivial"]:
            n_chains = len(chains_to_keep[glm_type])
            n_samples_model = samples_per_model[glm_type]
            print(f"  {glm_type}: {n_chains} chains -> {n_samples_model} samples")

        # Resample to common length if models have different sample counts
        unique_counts = set(samples_per_model.values())
        if len(unique_counts) > 1:
            min_samples = min(unique_counts)
            print(f"  Resampling to common length: {min_samples}")

            # Use deterministic resampling: take evenly-spaced samples
            # This ensures each sample is used 0 or 1 times (no weighting bias)
            rng = np.random.default_rng(seed=42)

            for key, arr in filtered_data.items():
                if len(arr) > min_samples:
                    # Random subsample without replacement (no sorting - avoid artificial correlation)
                    indices = rng.choice(len(arr), size=min_samples, replace=False)
                    filtered_data[key] = arr[indices]

        # Shuffle each array independently to break temporal autocorrelation structure.
        # This ensures random pairing when computing derived quantities (A, B, C, RQ1)
        # from independent model fits.
        rng_shuffle = np.random.default_rng(seed=43)  # Different seed for shuffle
        for key in filtered_data:
            rng_shuffle.shuffle(filtered_data[key])

        # Recompute derived quantities from filtered log-likelihoods
        required_logliks = [
            "strategic_logliks",
            "non_strategic_logliks",
            "combined_logliks",
            "trivial_logliks",
        ]
        missing = [k for k in required_logliks if k not in filtered_data]
        if missing:
            raise ValueError(f"Missing required log-likelihood keys: {missing}")

        strategic = filtered_data["strategic_logliks"]
        non_strategic = filtered_data["non_strategic_logliks"]
        combined = filtered_data["combined_logliks"]
        trivial = filtered_data["trivial_logliks"]

        filtered_data["A_distribution"] = strategic - trivial
        filtered_data["B_distribution"] = non_strategic - trivial
        filtered_data["C_distribution"] = combined - trivial

        # RQ1 = (A + C - B) / (2C), undefined when C = 0
        C = filtered_data["C_distribution"]
        A = filtered_data["A_distribution"]
        B = filtered_data["B_distribution"]
        RQ1 = np.zeros_like(C)
        valid_mask = C != 0
        RQ1[valid_mask] = (A[valid_mask] + C[valid_mask] - B[valid_mask]) / (
            2 * C[valid_mask]
        )
        RQ1[~valid_mask] = np.nan
        filtered_data["RQ1_distribution"] = RQ1

        # Recompute S and NS from filtered combined coefficients
        from lib.pooled_fitting.posteriors import (
            compute_non_strategic_sum,
            compute_strategic_sum,
        )

        combined_coefficients = {
            k: v
            for k, v in filtered_data.items()
            if k.startswith("combined_") and "_effects[" in k
        }
        if combined_coefficients:
            filtered_data["S_distribution"] = compute_strategic_sum(
                combined_coefficients
            )
            filtered_data["NS_distribution"] = compute_non_strategic_sum(
                combined_coefficients
            )

        print("  Recomputed derived quantities (A, B, C, RQ1, S, NS)")

        # Verify all sample arrays have the same length
        sample_lengths = {
            key: len(arr)
            for key, arr in filtered_data.items()
            if arr.ndim == 1 and len(arr) > 0
        }
        unique_lengths = set(sample_lengths.values())
        if len(unique_lengths) > 1:
            raise ValueError(
                f"Sample arrays have inconsistent lengths after resampling: {sample_lengths}. "
                "This is a bug in the resampling logic."
            )

        # Backup original files
        backup_json = analysis.fit_path.with_suffix(".json.bak")
        backup_npz = analysis.npz_path.with_suffix(".npz.bak")

        shutil.copy(analysis.fit_path, backup_json)
        shutil.copy(analysis.npz_path, backup_npz)
        print(f"  Backed up to {backup_json.name} and {backup_npz.name}")

        # Save filtered npz
        np.savez(analysis.npz_path, **filtered_data)

        # Update json metadata
        with open(analysis.fit_path) as f:
            metadata = json.load(f)

        metadata["convergence_ok"] = True
        metadata["convergence_issues"] = []
        metadata["chain_filtering_applied"] = True
        metadata["original_n_chains"] = N_CHAINS
        metadata["chains_kept_per_model"] = {
            k: info.converged_chains
            for k, info in analysis.per_model_convergence.items()
        }
        metadata["original_issues"] = analysis.original_issues

        # Verify all required distributions exist
        required_dists = [
            "S_distribution",
            "NS_distribution",
            "C_distribution",
            "RQ1_distribution",
        ]
        missing_dists = [k for k in required_dists if k not in filtered_data]
        if missing_dists:
            raise ValueError(
                f"Missing required distributions after filtering: {missing_dists}"
            )

        # Recompute summary stats from filtered samples
        s = filtered_data["S_distribution"]
        metadata["S_mean"] = float(s.mean())
        metadata["S_std"] = float(s.std())
        metadata["S_eti_2.5%"] = float(np.percentile(s, 2.5))
        metadata["S_eti_97.5%"] = float(np.percentile(s, 97.5))

        ns = filtered_data["NS_distribution"]
        metadata["NS_mean"] = float(ns.mean())
        metadata["NS_std"] = float(ns.std())
        metadata["NS_eti_2.5%"] = float(np.percentile(ns, 2.5))
        metadata["NS_eti_97.5%"] = float(np.percentile(ns, 97.5))

        c = filtered_data["C_distribution"]
        metadata["C_mean"] = float(c.mean())

        # Update RQ1 stats
        rq1 = filtered_data["RQ1_distribution"]
        if "rq1" not in metadata:
            metadata["rq1"] = {}
        metadata["rq1"]["rq1_metric"] = float(np.nanmean(rq1))
        metadata["rq1"]["rq1_eti"] = [
            float(np.nanpercentile(rq1, 2.5)),
            float(np.nanpercentile(rq1, 97.5)),
        ]
        metadata["rq1"]["n_posterior_draws"] = len(rq1)

        with open(analysis.fit_path, "w") as f:
            json.dump(metadata, f, indent=2)

        print("  Saved filtered files")
        return True, None

    except Exception as e:
        # Attempt to restore from backup if we created one
        backup_json = analysis.fit_path.with_suffix(".json.bak")
        backup_npz = analysis.npz_path.with_suffix(".npz.bak")
        if backup_json.exists():
            shutil.copy(backup_json, analysis.fit_path)
        if backup_npz.exists():
            shutil.copy(backup_npz, analysis.npz_path)
        return False, f"Failed to fix {analysis.fit_path.name}: {e}"


def main(dry_run: bool = True, posterior_dir: str = "paper_cache/posteriors/pooled"):
    """Find and fix convergence issues in posterior fits.

    Args:
        dry_run: If True, only show what would be done without making changes
        posterior_dir: Directory containing posterior fits
    """
    posterior_path = Path(posterior_dir)

    if not posterior_path.exists():
        print(
            f"Error: Posterior directory does not exist: {posterior_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not posterior_path.is_dir():
        print(f"Error: Path is not a directory: {posterior_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {posterior_path} for convergence issues...")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLYING FIXES'}")
    print(f"R-hat threshold: {RHAT_THRESHOLD}")
    print(f"Major issue threshold: {MAJOR_RHAT_THRESHOLD}")
    print(f"Min converged chains: {MIN_CONVERGED_CHAINS}")
    print()

    # Find all json files (excluding fit_quality.json)
    json_files = sorted(posterior_path.rglob("*.json"))
    json_files = [f for f in json_files if f.name != "fit_quality.json"]

    if not json_files:
        print(f"No posterior JSON files found in {posterior_path}")
        sys.exit(0)

    analyses = []
    errors = []
    for json_path in json_files:
        try:
            analysis = analyze_fit(json_path)
            if analysis is not None:
                analyses.append(analysis)
        except FileNotFoundError as e:
            errors.append(f"{json_path.name}: {e}")
        except (json.JSONDecodeError, ValueError) as e:
            errors.append(f"{json_path.name}: {e}")

    if errors:
        print(
            f"Errors encountered while analyzing {len(errors)} files:", file=sys.stderr
        )
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print()

    # Separate divergence-only fits from R-hat-based analyses
    divergence_only = [a for a in analyses if a.reason == "DIVERGENCE_ONLY"]
    rhat_analyses = [a for a in analyses if a.reason != "DIVERGENCE_ONLY"]

    # Report findings
    fixable = [a for a in rhat_analyses if a.can_fix]
    unfixable = [a for a in rhat_analyses if not a.can_fix and a.original_issues]

    print(f"Found {len(analyses)} fits with convergence issues")
    print(f"  R-hat fixable (chain filtering): {len(fixable)}")
    print(f"  R-hat unfixable: {len(unfixable)}")
    print(f"  Divergence-only (will mark OK): {len(divergence_only)}")

    # Handle divergence-only fits: mark as convergence_ok=true
    # These have a small number of divergent HMC transitions (typically 1),
    # which is negligible and does not warrant chain filtering.
    if divergence_only:
        print()
        print("=" * 70)
        print("DIVERGENCE-ONLY FITS: MARKING AS convergence_ok=true")
        print("=" * 70)
        print(
            "These fits have a small number of divergent HMC transitions\n"
            "(per-transition, NOT per-chain). Chain filtering cannot help;\n"
            "the samples are fine. Marking convergence_ok=true without\n"
            "modifying posterior samples."
        )
        print()

        div_fixed = 0
        for a in divergence_only:
            total_divs = sum(
                int(issue.split(":")[1].strip().split()[0])
                for issue in a.original_issues
            )
            print(
                f"  {a.fit_path.name}: {a.original_issues} ({total_divs} total divergences)"
            )

            if not dry_run:
                with open(a.fit_path) as f:
                    metadata = json.load(f)
                metadata["convergence_ok"] = True
                metadata["divergences_accepted"] = a.original_issues
                with open(a.fit_path, "w") as f:
                    json.dump(metadata, f, indent=2)
            div_fixed += 1

        print()
        print(
            f"{'Would mark' if dry_run else 'Marked'} {div_fixed} divergence-only fits as convergence_ok=true"
        )
        print("=" * 70)

    if unfixable:
        print("\n=== Cannot fix (minor issues or insufficient converged chains) ===")
        for a in unfixable:
            print(f"  {a.fit_path.name}: {a.reason}")

    if fixable:
        print("\n=== Can fix ===")
        for a in fixable:
            # Show chain analysis
            print(f"\n{a.fit_path.name}:")
            print(f"  Issues: {a.original_issues}")
            for key, info in a.per_model_convergence.items():
                means_str = (
                    [f"{m:.1f}" for m in info.chain_means]
                    if info.chain_means
                    else "N/A"
                )
                print(
                    f"  {key}: chains {info.converged_chains} (R-hat={info.rhat:.3f}), means={means_str}"
                )

    # Apply fixes
    if fixable:
        print("\n" + "=" * 60)
        fixed_count = 0
        fix_errors = []
        for analysis in fixable:
            success, error = fix_fit(analysis, dry_run=dry_run)
            if success:
                fixed_count += 1
            elif error:
                fix_errors.append(error)

        print(f"\n{'Would fix' if dry_run else 'Fixed'} {fixed_count} files")

        if fix_errors:
            print(f"\nErrors during fixing ({len(fix_errors)}):", file=sys.stderr)
            for err in fix_errors:
                print(f"  {err}", file=sys.stderr)

        if dry_run:
            print("\nRun without --dry-run to apply fixes:")
            print("  uv run scripts/paper/fix_convergence.py")


if __name__ == "__main__":
    fire.Fire(main)
