"""Coefficient extraction for propensity analysis.

This module handles extracting and parsing coefficient summaries
from fitted HiBayES models.
"""

import logging
import re
from typing import Any

import arviz as az
import numpy as np
import pandas as pd

from lib.analysis.types import FittedModels

logger = logging.getLogger(__name__)


class AnalysisError(Exception): ...


def extract_coefficient_summary(
    fitted_models: FittedModels,
    model_tag: str = "combined",
) -> pd.DataFrame | None:
    """Extract posterior summaries for all coefficients.

    Returns DataFrame with:
    - Parameter name
    - Posterior mean
    - Posterior SD
    - 95% ETI (equal-tailed interval: 2.5th-97.5th percentiles)
    - R-hat convergence diagnostic

    Args:
        fitted_models: FittedModels with fitted HiBayES models.
        model_tag: Tag of the model to extract from ('combined', 'strategic_only', etc.).

    Returns:
        DataFrame with coefficient summaries, or None if extraction fails.
    """
    # Get the model by tag
    if model_tag == "combined":
        model_state = fitted_models.combined
    elif model_tag == "strategic_only":
        model_state = fitted_models.strategic
    elif model_tag == "non_strategic_only":
        model_state = fitted_models.non_strategic
    else:
        raise AnalysisError(f"Unknown model tag: {model_tag}")

    if not model_state.is_fitted:
        AnalysisError(f"Model '{model_tag}' is not fitted")

    # Extract posterior samples and compute ETI manually
    idata = model_state.inference_data
    posterior = idata.posterior

    # Get all variable names in the posterior
    var_names = list(posterior.data_vars)

    rows = []
    for var_name in var_names:
        var_data = posterior[var_name]

        # Handle scalar vs array parameters
        if var_data.dims == ("chain", "draw"):
            # Scalar parameter
            samples = var_data.values.flatten()
            rows.append(_compute_summary_row(var_name, samples))
        elif len(var_data.dims) == 3:
            # Array parameter (chain, draw, dim)
            dim_name = [d for d in var_data.dims if d not in ("chain", "draw")][0]
            dim_coords = var_data.coords[dim_name].values
            for i, coord in enumerate(dim_coords):
                samples = var_data.values[:, :, i].flatten()
                param_name = f"{var_name}[{coord}]"
                rows.append(_compute_summary_row(param_name, samples))

    # Compute R-hat (Gelman-Rubin convergence diagnostic) using ArviZ.
    # R-hat measures how well MCMC chains have mixed:
    # - R-hat ≈ 1.0: Chains have converged (good)
    # - R-hat > 1.01: Chains may not have converged (problematic)
    rhat_dict: dict[str, float] = {}
    rhat_summary = az.rhat(idata)
    # az.rhat returns Dataset when given InferenceData
    if hasattr(rhat_summary, "data_vars"):
        for var_name in rhat_summary.data_vars:  # type: ignore[union-attr]
            var_data = rhat_summary[var_name]  # type: ignore[index]
            if var_data.dims == ():
                rhat_dict[var_name] = float(var_data.values)
            else:
                dim_name = var_data.dims[0]
                dim_coords = var_data.coords[dim_name].values
                for i, coord in enumerate(dim_coords):
                    param_name = f"{var_name}[{coord}]"
                    rhat_dict[param_name] = float(var_data.values[i])

    # Build DataFrame
    summary = pd.DataFrame(rows)
    summary.set_index("parameter", inplace=True)

    # Add r_hat column
    summary["r_hat"] = summary.index.map(lambda x: rhat_dict.get(x, np.nan))

    return summary


def _compute_summary_row(param_name: str, samples: np.ndarray) -> dict[str, Any]:
    """Compute summary statistics for a single parameter.

    Args:
        param_name: Name of the parameter.
        samples: Flattened array of posterior samples.

    Returns:
        Dictionary with summary statistics.
    """
    return {
        "parameter": param_name,
        "mean": float(np.mean(samples)),
        "sd": float(np.std(samples)),
        "eti_2.5%": float(np.percentile(samples, 2.5)),
        "eti_97.5%": float(np.percentile(samples, 97.5)),
    }


def parse_coefficient_name(coef_name: str) -> tuple[str, str] | None:
    """Parse coefficient name to extract variable and category.

    Coefficient names from HiBayES follow the pattern:
    - "variable_effects[category]" for effect-coded categorical variables
    - "intercept" for the intercept term

    Args:
        coef_name: Coefficient name from arviz summary.

    Returns:
        Tuple of (variable_name, category_value), or None if not parseable.
    """
    # Skip parameters with "_constrained" suffix.
    # HiBayES uses effect coding with a sum-to-zero constraint for categorical variables.
    # For a variable with K levels, it samples K-1 free coefficients (named "{var}_effects_constrained")
    # and derives the Kth as the negative sum. The full K coefficients are stored as "{var}_effects".
    # We use "{var}_effects" (all K coefficients) and skip "{var}_effects_constrained" (only K-1).
    # Example: For cot_privacy with 5 levels, "cot_privacy_effects" has 5 values,
    # "cot_privacy_effects_constrained" has 4 - we use the former.
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


def get_coefficient_by_variable(
    summary: pd.DataFrame,
) -> dict[str, dict[str, dict[str, float]]]:
    """Organize coefficients by variable and category.

    Args:
        summary: DataFrame from coefficient summary.

    Returns:
        Nested dict: {variable: {category: {mean, eti_2.5%, eti_97.5%, ...}}}
    """
    result: dict[str, dict[str, dict[str, float]]] = {}

    for coef_name in summary.index:
        parsed = parse_coefficient_name(coef_name)
        if parsed is None:
            continue

        var_name, cat_value = parsed

        if var_name not in result:
            result[var_name] = {}

        result[var_name][cat_value] = {
            "mean": float(summary.loc[coef_name, "mean"]),
            "sd": float(summary.loc[coef_name, "sd"]),
            "eti_2.5%": float(summary.loc[coef_name, "eti_2.5%"]),
            "eti_97.5%": float(summary.loc[coef_name, "eti_97.5%"]),
        }

        # Add r_hat if available
        if "r_hat" in summary.columns:
            result[var_name][cat_value]["r_hat"] = float(
                summary.loc[coef_name, "r_hat"]
            )

    return result


def compute_odds_ratios(
    summary: pd.DataFrame,
) -> pd.DataFrame:
    """Convert log-odds coefficients to odds ratios with ETIs.

    For a logistic regression, the coefficient is in log-odds space.
    Exponentiating gives the odds ratio.

    Args:
        summary: DataFrame from coefficient summary with log-odds coefficients.

    Returns:
        DataFrame with odds ratio columns added.
    """
    result = summary.copy()

    # Compute odds ratios
    result["odds_ratio"] = np.exp(result["mean"])
    result["odds_ratio_lower"] = np.exp(result["eti_2.5%"])
    result["odds_ratio_upper"] = np.exp(result["eti_97.5%"])

    return result
