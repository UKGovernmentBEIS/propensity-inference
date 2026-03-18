"""Model fitting for propensity analysis.

This module handles fitting Bayesian models using HiBayES and
checking convergence diagnostics.
"""

import logging
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
from hibayes.analysis import AnalysisConfig, model, process_data
from hibayes.model import ModelsToRunConfig
from hibayes.registry import RegistryInfo, registry_get, registry_info
from hibayes.ui import ModellingDisplay

from lib.analysis.types import FittedModels

logger = logging.getLogger(__name__)

# Attribute name for registry params (matches hibayes)
REGISTRY_PARAMS = "__registry_params__"


class ModelFittingError(Exception):
    """Raised when model fitting fails."""

    pass


def create_data_informed_models(
    analysis_config: AnalysisConfig,
    base_rate: float,
) -> ModelsToRunConfig:
    """Create model configs with data-informed intercept initialization.

    For logistic regression models, the intercept should be initialized near
    logit(base_rate) for reliable MCMC convergence. This function updates
    the prior_intercept_loc to logit(base_rate) and sets init_strategy to
    'median' so chains start at the data-informed location.

    Args:
        analysis_config: Original HiBayES analysis configuration.
        base_rate: Base rate (mean of outcome variable) in the data.

    Returns:
        ModelsToRunConfig with updated model configurations.
    """
    # Compute logit of base rate
    # Clip to avoid log(0) or log(inf)
    p = np.clip(base_rate, 1e-6, 1 - 1e-6)
    logit_base_rate = float(np.log(p / (1 - p)))
    logger.info(
        f"Data-informed initialization: base_rate={base_rate:.3f}, "
        f"logit(base_rate)={logit_base_rate:.3f}"
    )

    new_enabled_models = []
    for model_func, model_config in analysis_config.models.enabled_models:
        # Get original model name and params
        try:
            model_info = registry_info(model_func)
            model_name = model_info.name
        except ValueError:
            # Fallback: try to get name from __name__ attribute
            model_name = getattr(model_func, "__name__", "unknown")

        # Get original params used to create the model
        original_params = getattr(model_func, REGISTRY_PARAMS, {})

        # Update prior_intercept_loc if the model uses it
        new_params = dict(original_params)
        if "prior_intercept_loc" in new_params:
            new_params["prior_intercept_loc"] = logit_base_rate
            logger.debug(
                f"Model '{model_config.tag}': setting prior_intercept_loc="
                f"{logit_base_rate:.3f}"
            )

        # Recreate model function with updated params
        model_builder = registry_get(RegistryInfo(type="model", name=model_name))
        new_model_func = model_builder(**new_params)

        # Update fit config to use median init (which will be at logit_base_rate)
        new_fit = model_config.fit.merged(init_strategy="median")
        new_model_config = replace(model_config, fit=new_fit)

        new_enabled_models.append((new_model_func, new_model_config))

    return ModelsToRunConfig(enabled_models=new_enabled_models)


def check_convergence(state: Any) -> tuple[bool, list[str]]:
    """Check convergence diagnostics for all fitted models.

    Checks:
    1. R-hat values (should be < 1.01)
    2. Number of divergent transitions (should be 0)

    Args:
        state: HiBayES AnalysisState with fitted models.

    Returns:
        Tuple of (all_ok, list_of_issues).
    """
    issues: list[str] = []
    all_ok = True

    for model_state in state.models:
        model_name = model_state.model_config.tag or model_state.model_name
        diagnostics = model_state.diagnostics or {}

        # Check R-hat
        if "summary" in diagnostics:
            summary = diagnostics["summary"]
            if hasattr(summary, "r_hat"):
                max_rhat = summary["r_hat"].max()
                if max_rhat > 1.01:
                    issues.append(f"{model_name}: R-hat={max_rhat:.3f} > 1.01")
                    all_ok = False

        # Check divergences
        if "divergences" in diagnostics:
            n_div = diagnostics["divergences"]
            if n_div > 0:
                issues.append(f"{model_name}: {n_div} divergences")
                all_ok = False

    return all_ok, issues


def get_model_by_tag(state: Any, tag: str) -> Any:
    """Get a model from the state by its tag.

    Args:
        state: HiBayES AnalysisState with fitted models.
        tag: Model tag to find.

    Returns:
        ModelState for the requested model.

    Raises:
        ValueError: If model with tag is not found.
    """
    for model_state in state.models:
        if model_state.model_config.tag == tag:
            return model_state

    available = [m.model_config.tag for m in state.models if m.model_config.tag]
    raise ValueError(f"Model '{tag}' not found. Available: {available}")


def fit_bayesian_models(
    df: pd.DataFrame,
    analysis_config: AnalysisConfig,
    display: ModellingDisplay | None = None,
    use_data_informed_init: bool = True,
) -> FittedModels:
    """Fit all Bayesian models using HiBayES.

    This fits three models defined in the config:
    - strategic_only: Only strategic parameters
    - non_strategic_only: Only non-strategic parameters
    - combined: All parameters

    Args:
        df: DataFrame with data for fitting.
        analysis_config: HiBayES analysis configuration.
        display: Optional display for progress output.
        use_data_informed_init: If True, set prior_intercept_loc to logit(base_rate)
            for reliable MCMC convergence. Defaults to True.

    Returns:
        FittedModels containing the state and individual model references.

    Raises:
        ModelFittingError: If model fitting fails.
    """
    # Create display if not provided
    if display is None:
        display = ModellingDisplay()

    # Create data-informed model configs if requested
    if use_data_informed_init:
        base_rate = float(df["score"].mean())
        models_config = create_data_informed_models(analysis_config, base_rate)
    else:
        models_config = analysis_config.models

    # Process data
    logger.info("Processing data for model fitting...")
    try:
        state = process_data(
            analysis_config.data_process,
            display,
            data=df,
        )
        # WORKAROUND: hibayes has a mutable default argument bug where all
        # AnalysisState instances share the same models list. Clear it to
        # ensure we don't accumulate models from previous runs.
        state._models = []
    except Exception as e:
        raise ModelFittingError(f"Data processing failed: {e}") from e

    # Fit models
    logger.info("Fitting Bayesian models...")
    try:
        state = model(
            state,
            models_config,
            analysis_config.checkers,
            analysis_config.platform,
            display,
        )
    except Exception as e:
        raise ModelFittingError(f"Model fitting failed: {e}") from e

    # Check convergence
    convergence_ok, convergence_issues = check_convergence(state)
    if not convergence_ok:
        for issue in convergence_issues:
            logger.warning(f"Convergence issue: {issue}")

    # Get individual model references
    try:
        strategic = get_model_by_tag(state, "strategic_only")
        non_strategic = get_model_by_tag(state, "non_strategic_only")
        combined = get_model_by_tag(state, "combined")
    except ValueError as e:
        raise ModelFittingError(str(e)) from e

    return FittedModels(
        state=state,
        strategic=strategic,
        non_strategic=non_strategic,
        combined=combined,
        trivial=None,
        convergence_ok=convergence_ok,
        convergence_issues=convergence_issues,
    )


def get_loglik_distribution(model_state: Any) -> np.ndarray:
    """Get distribution of total log-likelihoods from posterior samples.

    HiBayES stores per-observation log-likelihoods in inference_data.log_likelihood['obs']
    with shape (chains, draws, n_obs). We sum over observations and flatten across chains.

    Args:
        model_state: HiBayES ModelState with fitted inference_data.

    Returns:
        Array of total log-likelihoods, one per posterior draw.
    """
    ll = model_state.inference_data.log_likelihood[
        "obs"
    ].values  # (chains, draws, n_obs)
    return ll.sum(axis=-1).flatten()  # Sum over observations, flatten chains×draws
