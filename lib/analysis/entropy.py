"""Entropy estimation and normalization for propensity analysis.

This module provides functions to:
1. Load entropy estimation samples from S3 structured storage
2. Estimate conditional entropy H(Y|X) using empirical Bayes
3. Compute mutual information I(X;Y) = H(Y) - H(Y|X)
4. Normalize A, B, C posterior distributions by I(X;Y)

The key insight is that I(X;Y) represents the maximum amount of variance
in the outcome Y that can be explained by the parameters X. Normalizing
by this value puts A, B, C on a [0, 1] scale where:
  - 0 = No improvement over null model
  - 1 = Explains all of I(X;Y) (maximum possible)
  - >1 = Exceeds estimated I(X;Y) bound (possible if H(Y|X) underestimated)
  - <0 = Worse than null model
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from lib.analysis.types import PosteriorDistributions


logger = logging.getLogger(__name__)


def binary_entropy(p: float) -> float:
    """Compute H(Bernoulli(p)) in bits.

    Args:
        p: Probability parameter in [0, 1].

    Returns:
        Entropy in bits.
    """
    if p < 1e-10 or p > 1 - 1e-10:
        return 0.0
    return -p * np.log2(p) - (1 - p) * np.log2(1 - p)


def empirical_bayes_estimator(
    k_values: np.ndarray,
    n_values: np.ndarray,
    n_mc: int = 1000,
) -> float:
    """Empirical Bayes entropy estimator.

    Fits a Beta prior from observed proportions using method of moments,
    then computes the posterior expected entropy for each configuration.

    Args:
        k_values: Success counts per configuration.
        n_values: Trial counts per configuration.
        n_mc: Number of Monte Carlo samples for posterior entropy.

    Returns:
        Estimated H(Y|X) in bits.
    """
    p_hat = k_values / n_values
    mean_p = np.mean(p_hat)
    var_p = np.var(p_hat)

    # Fit Beta prior via method of moments
    if var_p < 1e-8:
        alpha, beta = 1.0, 1.0
    else:
        s = mean_p * (1 - mean_p) / var_p - 1
        if s <= 0:
            alpha, beta = 1.0, 1.0
        else:
            alpha = max(0.1, min(mean_p * s, 100.0))
            beta = max(0.1, min((1 - mean_p) * s, 100.0))

    # Compute posterior expected entropy for each config
    entropies = []
    for k, n in zip(k_values, n_values):
        post_a, post_b = alpha + k, beta + (n - k)
        p_samples = np.random.beta(post_a, post_b, size=n_mc)
        entropies.append(np.mean([binary_entropy(p) for p in p_samples]))
    return float(np.mean(entropies))


def load_entropy_samples_from_s3(
    scenario: str,
    variation: str,
    model: str,
    version: str | None = None,
    bucket: str | None = None,
    max_workers: int = 32,
) -> tuple[np.ndarray, np.ndarray]:
    """Load entropy samples from S3 structured storage.

    Looks for eval files in:
        s3://<bucket>/<prefix>/evals/<scenario>/<variation>/<version>/<model>/entropy/

    Reads files in parallel for performance.

    Args:
        scenario: Scenario name (e.g., "agentic_misalignment_v2").
        variation: Variation name (e.g., "alert").
        model: Model API name (e.g., "openai/o4-mini-2025-04-16").
        version: Version string (e.g., "15.0.1"). If None, uses latest valid version.
        bucket: S3 bucket name (defaults to S3_BUCKET env var).
        max_workers: Number of parallel workers for S3 reads.

    Returns:
        Tuple of (k_values, n_values) arrays for entropy estimation.

    Raises:
        ValueError: If no entropy files found.
    """
    from collections import defaultdict

    from lib.eval_storage import get_bucket, list_evals, read_eval_logs_parallel

    bucket = bucket or get_bucket()

    # Query entropy files using high-level API
    paths = list_evals(
        scenario=scenario,
        variation=variation,
        model=model,
        min_version=version,  # If None, auto-fetches from version tracking
        bucket=bucket,
        subdir="entropy",  # Only get entropy samples
    )

    if not paths:
        raise ValueError(
            f"No entropy files found for {scenario}/{variation}/{model}. "
            f"Run entropy estimation first using scripts/estimate_entropy.py."
        )

    logger.info(f"Found {len(paths)} entropy eval files")

    # Read all logs in parallel
    s3_uris = [p.s3_uri(bucket) for p in paths]
    log_results = read_eval_logs_parallel(
        s3_uris,
        header_only=False,
        max_workers=max_workers,
    )

    # Aggregate by config hash
    by_config: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "k": 0})
    n_no_hash = 0
    n_no_score = 0

    for _uri, log in log_results:
        if log is None:
            continue

        # Extract scores from samples, using entropy_config_hash from sample metadata
        for sample in log.samples or []:
            sample_meta = sample.metadata or {}

            # Get config hash from sample metadata (set by estimate_entropy.py)
            config_hash = sample_meta.get("entropy_config_hash")
            if not config_hash:
                n_no_hash += 1
                continue

            # Extract score
            score = None
            if sample.scores:
                score_obj = next(iter(sample.scores.values()))
                score_val = score_obj.value
                if score_val in ("C", "CORRECT", 1, 1.0, "1"):
                    score = 1
                elif score_val in ("I", "INCORRECT", 0, 0.0, "0"):
                    score = 0

            if score is not None:
                by_config[config_hash]["n"] += 1
                by_config[config_hash]["k"] += score
            else:
                n_no_score += 1

    if n_no_hash > 0:
        logger.warning(f"  {n_no_hash} samples missing entropy_config_hash")
    if n_no_score > 0:
        logger.warning(f"  {n_no_score} samples missing valid score")

    if not by_config:
        raise ValueError("No valid entropy samples found in eval files")

    # Filter to configs with multiple samples
    valid_configs = {h: d for h, d in by_config.items() if d["n"] >= 2}

    if not valid_configs:
        raise ValueError(
            f"No configs with >= 2 samples found. Total configs: {len(by_config)}"
        )

    logger.info(
        f"Loaded {sum(d['n'] for d in valid_configs.values())} samples "
        f"across {len(valid_configs)} configs"
    )

    k_values = np.array([d["k"] for d in valid_configs.values()])
    n_values = np.array([d["n"] for d in valid_configs.values()])

    return k_values, n_values


def compute_entropy_normalization(
    scenario: str,
    variation: str,
    model: str,
    base_rate: float,
    n_samples: int,
    version: str | None = None,
    bucket: str | None = None,
) -> dict[str, float]:
    """Compute entropy normalization factors.

    Loads entropy samples from S3, estimates H(Y|X), and computes
    the mutual information I(X;Y) = H(Y) - H(Y|X).

    Args:
        scenario: Scenario name.
        variation: Variation name.
        model: Model API name.
        base_rate: Overall misalignment rate (p).
        n_samples: Number of samples in the analysis.
        version: Version string. If None, uses latest valid version.
        bucket: S3 bucket name (optional).

    Returns:
        Dict with entropy info:
            - H_Y: Marginal entropy H(Y) in bits
            - H_Y_given_X: Conditional entropy H(Y|X) in bits
            - I_XY: Mutual information I(X;Y) in bits
            - I_XY_nats_total: I(X;Y) * n * log(2) - normalization factor for total log-lik
    """
    # Load entropy samples
    k_values, n_values = load_entropy_samples_from_s3(
        scenario, variation, model, version, bucket
    )

    # Estimate H(Y|X) using empirical Bayes
    H_Y_given_X = empirical_bayes_estimator(k_values, n_values)
    logger.info(f"Estimated H(Y|X) = {H_Y_given_X:.4f} bits")

    # Compute H(Y) from base rate
    H_Y = binary_entropy(base_rate)
    logger.info(f"H(Y) from base rate {base_rate:.1%} = {H_Y:.4f} bits")

    # Compute I(X;Y)
    I_XY = H_Y - H_Y_given_X
    if I_XY < 0:
        logger.warning(
            f"Negative mutual information I(X;Y) = {I_XY:.4f}. "
            f"This may indicate overfitting in entropy estimation or "
            f"base rate mismatch."
        )

    # Normalization factor for total log-likelihood
    # A, B, C are in nats; I(X;Y) is in bits
    # To normalize: A / (n * I(X;Y) * log(2))
    I_XY_nats_total = n_samples * I_XY * np.log(2)

    logger.info(f"I(X;Y) = {I_XY:.4f} bits")
    logger.info(f"Normalization factor (n * I(X;Y) * log(2)) = {I_XY_nats_total:.2f}")

    return {
        "H_Y": H_Y,
        "H_Y_given_X": H_Y_given_X,
        "I_XY": I_XY,
        "I_XY_nats_total": I_XY_nats_total,
        "n_entropy_configs": len(k_values),
        "n_entropy_samples": int(np.sum(n_values)),
    }


def plot_normalized_distributions(
    posteriors: PosteriorDistributions,
    entropy_info: dict[str, float],
    output_path: Path,
    n_samples: int,
    model_name: str,
) -> None:
    """Create visualization of A, B, C distributions normalized by I(X;Y).

    Normalized values interpretation:
        - [0, 1]: Normal - explaining some but not all of the explainable variance
        - > 1: Overfitting - claiming to explain more than theoretically possible
        - < 0: Worse than null model

    Args:
        posteriors: PosteriorDistributions with A, B, C distributions.
        entropy_info: Dict from compute_entropy_normalization().
        output_path: Path to save the figure.
        n_samples: Number of data samples.
        model_name: Name of the model being analyzed.
    """
    # Import here to avoid matplotlib import at module load
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    I_norm = entropy_info["I_XY_nats_total"]

    if I_norm <= 0:
        logger.warning("Cannot normalize: I(X;Y) <= 0")
        return

    # Normalize distributions
    A_norm = posteriors.A_distribution / I_norm
    B_norm = posteriors.B_distribution / I_norm
    C_norm = posteriors.C_distribution / I_norm

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # A normalized
    ax = axes[0, 0]
    ax.hist(
        A_norm, bins=50, density=True, alpha=0.7, color="blue", edgecolor="darkblue"
    )
    ax.axvline(0, color="red", linestyle="--", linewidth=2, label="Null (0)")
    ax.axvline(
        1, color="green", linestyle="--", linewidth=2, label="Max explainable (1)"
    )
    ax.axvline(
        np.mean(A_norm),
        color="blue",
        linestyle="-",
        linewidth=2,
        label=f"Mean: {np.mean(A_norm):.3f}",
    )
    ax.set_xlabel("A / I(X;Y) normalized", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(
        f"A: Strategic (normalized)\nP(A'>0) = {np.mean(A_norm > 0):.1%}, "
        f"P(A'>1) = {np.mean(A_norm > 1):.1%}",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # B normalized
    ax = axes[0, 1]
    ax.hist(
        B_norm, bins=50, density=True, alpha=0.7, color="orange", edgecolor="darkorange"
    )
    ax.axvline(0, color="red", linestyle="--", linewidth=2, label="Null (0)")
    ax.axvline(
        1, color="green", linestyle="--", linewidth=2, label="Max explainable (1)"
    )
    ax.axvline(
        np.mean(B_norm),
        color="orange",
        linestyle="-",
        linewidth=2,
        label=f"Mean: {np.mean(B_norm):.3f}",
    )
    ax.set_xlabel("B / I(X;Y) normalized", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(
        f"B: Non-Strategic (normalized)\nP(B'>0) = {np.mean(B_norm > 0):.1%}, "
        f"P(B'>1) = {np.mean(B_norm > 1):.1%}",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # C normalized
    ax = axes[1, 0]
    ax.hist(
        C_norm, bins=50, density=True, alpha=0.7, color="purple", edgecolor="darkviolet"
    )
    ax.axvline(0, color="red", linestyle="--", linewidth=2, label="Null (0)")
    ax.axvline(
        1, color="green", linestyle="--", linewidth=2, label="Max explainable (1)"
    )
    ax.axvline(
        np.mean(C_norm),
        color="purple",
        linestyle="-",
        linewidth=2,
        label=f"Mean: {np.mean(C_norm):.3f}",
    )
    ax.set_xlabel("C / I(X;Y) normalized", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(
        f"C: Combined (normalized)\nP(C'>0) = {np.mean(C_norm > 0):.1%}, "
        f"P(C'>1) = {np.mean(C_norm > 1):.1%}",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Summary text panel
    ax = axes[1, 1]
    ax.axis("off")

    summary_text = f"""
Entropy-Normalized Analysis
===========================

Model: {model_name}
Data samples: n = {n_samples}

Entropy Estimation:
  H(Y) = {entropy_info["H_Y"]:.4f} bits (from base rate)
  H(Y|X) = {entropy_info["H_Y_given_X"]:.4f} bits (irreducible)
  I(X;Y) = {entropy_info["I_XY"]:.4f} bits (max explainable)

  Entropy samples: {entropy_info["n_entropy_samples"]} across {entropy_info["n_entropy_configs"]} configs

Normalized Results (fraction of max explainable variance):
  A' (Strategic):     {np.mean(A_norm):.3f} [{np.percentile(A_norm, 2.5):.3f}, {np.percentile(A_norm, 97.5):.3f}]
  B' (Non-Strategic): {np.mean(B_norm):.3f} [{np.percentile(B_norm, 2.5):.3f}, {np.percentile(B_norm, 97.5):.3f}]
  C' (Combined):      {np.mean(C_norm):.3f} [{np.percentile(C_norm, 2.5):.3f}, {np.percentile(C_norm, 97.5):.3f}]

Interpretation:
  0 = No improvement over null model
  1 = Explains all of I(X;Y) (maximum possible)
  >1 = Overfitting (explains more than theoretically possible)
  <0 = Worse than null model
"""
    ax.text(
        0.05,
        0.95,
        summary_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        fontfamily="monospace",
    )

    fig.suptitle(
        "A, B, C Distributions Normalized by Intrinsic Entropy I(X;Y)",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    logger.info(f"Saved normalized distribution plot: {output_path}")
