"""Posterior extraction and summary computation for pooled regression fits."""

import logging
from typing import Any

import numpy as np

from lib.analysis.coefficients import parse_coefficient_name
from lib.analysis.effect_coding import normalize_effect_coded_coefficients
from lib.analysis.rq1_metrics import compute_rq1_with_eti
from lib.paper_style import NON_STRATEGIC_PARAMS, STRATEGIC_PARAMS

logger = logging.getLogger(__name__)


def extract_coefficient_posteriors(
    model_state: Any,
    normalize: bool = True,
) -> dict[str, np.ndarray]:
    """Extract posterior samples for all coefficients from a fitted model.

    Args:
        model_state: HiBayES model state with inference_data
        normalize: Whether to normalize effect-coded coefficients

    Returns:
        Dict mapping coefficient name -> array of posterior samples

    Raises:
        ValueError: If model has not been fitted
    """
    if not model_state.is_fitted:
        raise ValueError(
            "Cannot extract posteriors from unfitted model. Call model.fit() first."
        )

    idata = model_state.inference_data
    posterior = idata.posterior

    result: dict[str, np.ndarray] = {}

    for var_name in posterior.data_vars:
        var_data = posterior[var_name]

        if var_data.dims == ("chain", "draw"):
            samples = var_data.values.flatten()
            result[var_name] = samples
        elif len(var_data.dims) == 3:
            # [NOTE] 3D case: dims are (chain, draw, category) for effect-coded categorical
            # coefficients. We iterate through categories to create separate entries like
            # "threat[replacement]", "threat[restriction]", etc. The 2D case above handles
            # model-level parameters like intercepts that have a single value per draw.
            dim_name = [d for d in var_data.dims if d not in ("chain", "draw")][0]
            dim_coords = var_data.coords[dim_name].values
            for i, coord in enumerate(dim_coords):
                samples = var_data.values[:, :, i].flatten()
                param_name = f"{var_name}[{coord}]"
                result[param_name] = samples

    if normalize:
        result = normalize_effect_coded_coefficients(result, remove_dummy=True)

    return result


def _compute_param_sum(
    coefficients: dict[str, np.ndarray],
    param_set: list[str],
    param_set_name: str,
    implemented_params: list[str] | None = None,
) -> np.ndarray:
    """Compute sum of |coefficients| for a set of parameters.

    Args:
        coefficients: Dict of coefficient posteriors (from combined model)
        param_set: List of parameter names to include
        param_set_name: Name for logging (e.g., "strategic", "non-strategic")
        implemented_params: Only count these params (if None, count all in param_set)

    Returns:
        Array of sum samples
    """
    matching_coefs = []

    for coef_name, samples in coefficients.items():
        parsed = parse_coefficient_name(coef_name)
        if parsed is None:
            continue

        var_name, _category = parsed

        # Skip if not in the target parameter set
        if var_name not in param_set:
            continue

        # Skip if not implemented (if filter provided)
        # This works correctly with multiple variations - implemented_params
        # is computed across all scenarios in the pooled data, so any param
        # implemented in at least one scenario will be included.
        if implemented_params is not None and var_name not in implemented_params:
            continue

        matching_coefs.append(samples)

    if not matching_coefs:
        logger.warning(f"No {param_set_name} coefficients found!")
        return np.array([])

    result = np.zeros_like(matching_coefs[0])
    for coef_samples in matching_coefs:
        result += np.abs(coef_samples)

    return result


def compute_strategic_sum(
    coefficients: dict[str, np.ndarray],
    implemented_params: list[str] | None = None,
) -> np.ndarray:
    """Compute S = sum of |coefficients| for strategic parameters."""
    return _compute_param_sum(
        coefficients, STRATEGIC_PARAMS, "strategic", implemented_params
    )


def compute_non_strategic_sum(
    coefficients: dict[str, np.ndarray],
    implemented_params: list[str] | None = None,
) -> np.ndarray:
    """Compute NS = sum of |coefficients| for non-strategic parameters."""
    return _compute_param_sum(
        coefficients, NON_STRATEGIC_PARAMS, "non-strategic", implemented_params
    )


def compute_summary_stats(
    posteriors: dict[str, np.ndarray],
    implemented_params: list[str],
) -> dict[str, Any]:
    """Compute summary statistics from posteriors.

    Args:
        posteriors: Dict of posterior arrays
        implemented_params: List of parameters that were implemented

    Returns:
        Dict of summary statistics
    """
    summary: dict[str, Any] = {}

    # S and NS distributions
    if "S_distribution" in posteriors:
        S = posteriors["S_distribution"]
        summary["S_mean"] = float(np.mean(S))
        summary["S_std"] = float(np.std(S))
        summary["S_eti_2.5%"] = float(np.percentile(S, 2.5))
        summary["S_eti_97.5%"] = float(np.percentile(S, 97.5))

    if "NS_distribution" in posteriors:
        NS = posteriors["NS_distribution"]
        summary["NS_mean"] = float(np.mean(NS))
        summary["NS_std"] = float(np.std(NS))
        summary["NS_eti_2.5%"] = float(np.percentile(NS, 2.5))
        summary["NS_eti_97.5%"] = float(np.percentile(NS, 97.5))

    # RQ1 metrics
    if "C_distribution" in posteriors:
        C = posteriors["C_distribution"]
        summary["C_mean"] = float(np.mean(C))
        summary["p_c_positive"] = float(np.mean(C > 0))

    # Count coefficients
    n_coefficients = sum(
        1 for k in posteriors.keys() if k.startswith("combined_") and "_effects[" in k
    )
    summary["n_coefficients"] = n_coefficients
    summary["implemented_params"] = implemented_params
    summary["n_implemented_params"] = len(implemented_params)

    # Trivial baseline (intercepts-only) stats
    trivial = posteriors["trivial_logliks"]
    summary["trivial_loglik_mean"] = float(np.mean(trivial))
    summary["trivial_loglik_std"] = float(np.std(trivial))

    return summary


def build_posterior_data(
    fitted_models: Any,
    implemented_params: list[str],
) -> dict[str, np.ndarray]:
    """Build the full posterior data dict for saving.

    [NOTE] This function orchestrates extraction of all posteriors needed for
    analysis: RQ1 metrics, coefficient posteriors from each model, and S/NS sums.
    Called from core.py after fitting completes.

    Args:
        fitted_models: FittedModels object with strategic, non_strategic, combined
        implemented_params: List of implemented parameter names

    Returns:
        Dict mapping name -> array for np.savez
    """
    # Compute RQ1 metrics
    rq1_results, rq1_posteriors = compute_rq1_with_eti(fitted_models)

    # Extract coefficients from each model
    strategic_coefficients = extract_coefficient_posteriors(fitted_models.strategic)
    non_strategic_coefficients = extract_coefficient_posteriors(
        fitted_models.non_strategic
    )
    combined_coefficients = extract_coefficient_posteriors(fitted_models.combined)

    # Compute S and NS from combined model
    S = compute_strategic_sum(combined_coefficients, implemented_params)
    NS = compute_non_strategic_sum(combined_coefficients, implemented_params)

    # Build posterior data dict
    posterior_data: dict[str, np.ndarray] = {
        # RQ1 distributions (improvements over trivial baseline)
        "A_distribution": rq1_posteriors.A_distribution,
        "B_distribution": rq1_posteriors.B_distribution,
        "C_distribution": rq1_posteriors.C_distribution,
        "RQ1_distribution": rq1_posteriors.RQ1_distribution,
        # Log-likelihoods
        "strategic_logliks": rq1_posteriors.strategic_logliks,
        "non_strategic_logliks": rq1_posteriors.non_strategic_logliks,
        "combined_logliks": rq1_posteriors.combined_logliks,
        "trivial_logliks": rq1_posteriors.trivial_logliks,
        # S and NS sums
        "S_distribution": S,
        "NS_distribution": NS,
    }

    # Add coefficients with prefixes
    for name, samples in strategic_coefficients.items():
        posterior_data[f"strategic_{name}"] = samples
    for name, samples in non_strategic_coefficients.items():
        posterior_data[f"non_strategic_{name}"] = samples
    for name, samples in combined_coefficients.items():
        posterior_data[f"combined_{name}"] = samples

    return posterior_data
