"""RQ1 metric computation with proper Bayesian uncertainty.

This module computes the RQ1 metric (proportion of explained variance
attributable to strategic parameters) using posterior samples from
HiBayES models, providing full posterior distributions and ETIs.

RQ1 = (A + C - B) / (2C)

Where:
    A = Strategic model improvement over trivial baseline (intercepts-only)
    B = Non-strategic model improvement over trivial baseline
    C = Combined model improvement over trivial baseline

The trivial baseline has per-variation intercepts but no parameter effects,
ensuring we measure the contribution of parameters, not base rates.
"""

import logging

import numpy as np

from lib.analysis.models import get_loglik_distribution
from lib.analysis.types import FittedModels, PosteriorDistributions, RQ1Results
from lib.analysis.utils import compute_eti

logger = logging.getLogger(__name__)


def compute_improvement_distributions(
    fitted_models: FittedModels,
) -> PosteriorDistributions:
    """Compute posterior distributions of log-likelihood improvements.

    Args:
        fitted_models: FittedModels with strategic, non_strategic, combined, trivial.

    Returns:
        PosteriorDistributions with all raw and derived distributions.
    """
    # Get trivial baseline (intercepts-only) log-likelihood distribution
    if fitted_models.trivial is None:
        raise ValueError(
            "FittedModels.trivial is None - trivial baseline required for RQ1. "
            "Ensure the trivial model is fitted alongside strategic/non_strategic/combined."
        )
    trivial_logliks = get_loglik_distribution(fitted_models.trivial)
    logger.info(
        f"trivial (intercepts-only): mean loglik = {np.mean(trivial_logliks):.2f} "
        f"± {np.std(trivial_logliks):.2f}"
    )

    # Get log-likelihood distributions from each model
    strategic_logliks = get_loglik_distribution(fitted_models.strategic)
    non_strategic_logliks = get_loglik_distribution(fitted_models.non_strategic)
    combined_logliks = get_loglik_distribution(fitted_models.combined)

    logger.info(
        f"strategic_only: mean loglik = {np.mean(strategic_logliks):.2f} "
        f"± {np.std(strategic_logliks):.2f}"
    )
    logger.info(
        f"non_strategic_only: mean loglik = {np.mean(non_strategic_logliks):.2f} "
        f"± {np.std(non_strategic_logliks):.2f}"
    )
    logger.info(
        f"combined: mean loglik = {np.mean(combined_logliks):.2f} "
        f"± {np.std(combined_logliks):.2f}"
    )

    # Compute improvement distributions over trivial baseline (per-variation intercepts)
    # This measures the contribution of parameter effects, not base rates
    A_distribution = strategic_logliks - trivial_logliks
    B_distribution = non_strategic_logliks - trivial_logliks
    C_distribution = combined_logliks - trivial_logliks

    # Compute RQ1 distribution
    # RQ1 = (A + C - B) / (2C)
    # Only undefined when C = 0 (division by zero)
    RQ1_distribution = np.zeros_like(C_distribution)
    valid_mask = C_distribution != 0
    RQ1_distribution[valid_mask] = (
        A_distribution[valid_mask]
        + C_distribution[valid_mask]
        - B_distribution[valid_mask]
    ) / (2 * C_distribution[valid_mask])
    RQ1_distribution[~valid_mask] = np.nan

    n_invalid = np.sum(~valid_mask)
    if n_invalid > 0:
        logger.warning(
            f"{n_invalid}/{len(C_distribution)} posterior draws have C=0 "
            "(division by zero)"
        )

    return PosteriorDistributions(
        strategic_logliks=strategic_logliks,
        non_strategic_logliks=non_strategic_logliks,
        combined_logliks=combined_logliks,
        trivial_logliks=trivial_logliks,
        A_distribution=A_distribution,
        B_distribution=B_distribution,
        C_distribution=C_distribution,
        RQ1_distribution=RQ1_distribution,
    )


def compute_rq1_with_eti(
    fitted_models: FittedModels,
) -> tuple[RQ1Results, PosteriorDistributions]:
    """Compute RQ1 metric with 95% equal-tailed credible intervals.

    This is the main entry point for RQ1 computation. It computes
    posterior distributions for all improvements and derives the
    RQ1 distribution with 95% ETI (2.5th-97.5th percentiles).

    Args:
        fitted_models: FittedModels with all three fitted models.

    Returns:
        Tuple of (RQ1Results with point estimates and ETIs, PosteriorDistributions).
    """
    # Compute all distributions
    posteriors = compute_improvement_distributions(fitted_models)

    # Compute point estimates (posterior means)
    strategic_improvement = float(np.nanmean(posteriors.A_distribution))
    non_strategic_improvement = float(np.nanmean(posteriors.B_distribution))
    combined_improvement = float(np.nanmean(posteriors.C_distribution))
    rq1_metric = float(np.nanmean(posteriors.RQ1_distribution))

    # Compute ETIs (95% equal-tailed credible intervals)
    strategic_eti = compute_eti(posteriors.A_distribution)
    non_strategic_eti = compute_eti(posteriors.B_distribution)
    combined_eti = compute_eti(posteriors.C_distribution)
    rq1_eti = compute_eti(posteriors.RQ1_distribution)

    # Compute probabilities
    p_strategic_positive = float(np.nanmean(posteriors.A_distribution > 0))
    p_non_strategic_positive = float(np.nanmean(posteriors.B_distribution > 0))
    p_combined_positive = float(np.nanmean(posteriors.C_distribution > 0))
    p_rq1_positive = float(np.nanmean(posteriors.RQ1_distribution > 0))

    # Check for warnings
    warnings: list[str] = []
    n_nan = np.sum(np.isnan(posteriors.RQ1_distribution))
    if n_nan > 0:
        pct_nan = n_nan / len(posteriors.RQ1_distribution) * 100
        warnings.append(f"{pct_nan:.1f}% of RQ1 posterior draws are NaN (C<=0)")

    if np.isnan(rq1_metric):
        warnings.append("RQ1 metric is NaN (all posterior draws have C<=0)")

    # Log summary
    logger.info(
        f"RQ1: {rq1_metric:.3f} [{rq1_eti[0]:.3f}, {rq1_eti[1]:.3f}], "
        f"P(RQ1>0) = {p_rq1_positive:.1%}"
    )
    logger.info(
        f"A (strategic): {strategic_improvement:.2f} [{strategic_eti[0]:.2f}, {strategic_eti[1]:.2f}], "
        f"P(A>0) = {p_strategic_positive:.1%}"
    )
    logger.info(
        f"B (non-strategic): {non_strategic_improvement:.2f} [{non_strategic_eti[0]:.2f}, {non_strategic_eti[1]:.2f}], "
        f"P(B>0) = {p_non_strategic_positive:.1%}"
    )
    logger.info(
        f"C (combined): {combined_improvement:.2f} [{combined_eti[0]:.2f}, {combined_eti[1]:.2f}], "
        f"P(C>0) = {p_combined_positive:.1%}"
    )

    results = RQ1Results(
        rq1_metric=rq1_metric if not np.isnan(rq1_metric) else None,
        strategic_improvement=strategic_improvement,
        non_strategic_improvement=non_strategic_improvement,
        combined_improvement=combined_improvement,
        trivial_loglik_mean=float(np.mean(posteriors.trivial_logliks)),
        rq1_eti_lower=rq1_eti[0],
        rq1_eti_upper=rq1_eti[1],
        strategic_eti_lower=strategic_eti[0],
        strategic_eti_upper=strategic_eti[1],
        non_strategic_eti_lower=non_strategic_eti[0],
        non_strategic_eti_upper=non_strategic_eti[1],
        combined_eti_lower=combined_eti[0],
        combined_eti_upper=combined_eti[1],
        p_strategic_positive=p_strategic_positive,
        p_non_strategic_positive=p_non_strategic_positive,
        p_combined_positive=p_combined_positive,
        p_rq1_positive=p_rq1_positive,
        n_posterior_draws=len(posteriors.A_distribution),
        warnings=warnings,
    )

    return results, posteriors
