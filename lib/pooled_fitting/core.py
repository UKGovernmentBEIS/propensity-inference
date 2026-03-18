"""Core fitting function for pooled Bayesian regressions.

This module provides the main entry point for fitting pooled regressions
across different modes (per-model, per-variation, per-quartile, single, all-combined).
"""

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from hibayes.analysis import AnalysisConfig, model, process_data
from hibayes.ui import ModellingDisplay

import lib.pooled_fitting.custom_model  # noqa: F401 - registers custom model with HiBayES
from lib.analysis.effect_coding import inject_dummy_rows
from lib.analysis.models import (
    ModelFittingError,
    check_convergence,
    create_data_informed_models,
    get_model_by_tag,
)
from lib.analysis.rq1_metrics import compute_rq1_with_eti
from lib.analysis.types import FittedModels
from lib.paper_style import ALL_PARAMS
from lib.pooled_fitting.config import (
    apply_mcmc_override,
    build_analysis_config,
    get_categorical_features_from_config,
    get_category_order_from_config,
    get_reduced_mcmc_config,
)
from lib.pooled_fitting.data_prep import (
    PARAMETER_IMPLEMENTATION,
    add_pair_intercept_feature,
    create_combined_ai_type,
    create_harmonized_goal_value,
    fill_unimplemented_with_placeholder,
    get_pairs_in_data,
    harmonize_action_efficacy,
)
from lib.pooled_fitting.feature_zeroing import (
    get_params_with_signal,
    zero_unimplemented_features,
)
from lib.pooled_fitting.posteriors import build_posterior_data, compute_summary_stats
from lib.pooled_fitting.weighting import (
    apply_weights_for_hibayes,
    compute_sample_weights,
)

logger = logging.getLogger(__name__)


@dataclass
class FitResult:
    """Result of a pooled regression fit."""

    posteriors: dict[str, np.ndarray]
    summary: dict[str, Any]
    implemented_params: list[str]
    convergence_ok: bool
    convergence_issues: list[str]
    rq1_results: Any  # RQ1Results object


def fit_pooled_regression(
    df: pd.DataFrame,
    mcmc_mode: str | None = None,
    mcmc_override: dict[str, int] | None = None,
    param_implementation: dict[str, list[str]] | None = None,
    use_extras: bool = False,
    extra_params: dict[str, list[str]] | None = None,
    extra_param_variations: dict[str, list[str]] | None = None,
    use_goal: bool = False,
) -> FitResult:
    """Fit a pooled Bayesian regression.

    This is the main entry point for fitting pooled regressions. It handles:
    1. Adding pair intercept features (model_variation)
    2. Computing √n sample weights
    3. Building dynamic config based on data
    4. Preparing data (harmonization, placeholders, dummy injection)
    5. Zeroing features for unimplemented parameters
    6. Fitting Bayesian models
    7. Extracting posteriors and computing summaries

    Args:
        df: DataFrame with 'meta_model', 'variation', 'scenario', 'meta_score',
            and parameter columns. Should already be filtered to desired subset.
        mcmc_mode: "ultra", "fast", or None for full quality (ignored if mcmc_override set)
        mcmc_override: Custom MCMC settings {"samples": N, "warmup": N, "chains": N}
            Takes precedence over mcmc_mode.
            [NOTE] Not really used, except sometimes by Claude when testing. It'd be better to remove it IMO.
        param_implementation: Override for parameter implementation mapping
        use_extras: Whether to include extra scenario-specific parameters
        extra_params: Dict mapping extra param name -> list of categories.
            Required if use_extras=True.
        extra_param_variations: Dict mapping extra param -> list of variations
            that implement it. Required if use_extras=True.
        use_goal: Whether to include goal_value_harmonized as a feature.
            When True, adds 9-level goal value (none + 8 goals) to the model.

    Returns:
        FitResult with posteriors, summary, and metadata
    """
    if param_implementation is None:
        param_implementation = PARAMETER_IMPLEMENTATION

    # Validate extras args
    if use_extras and (extra_params is None or extra_param_variations is None):
        raise ValueError(
            "use_extras=True requires extra_params and extra_param_variations"
        )

    # Validate required columns
    required_cols = ["meta_model", "variation", "scenario", "meta_score"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Keep original for reference
    original_df = df.copy()

    # Step 1: Harmonize action_efficacy_binary
    df = harmonize_action_efficacy(df)

    # Step 1b: Create combined ai_type from confounded params (for extras mode)
    if use_extras:
        df = create_combined_ai_type(df)
        original_df = create_combined_ai_type(original_df)

    # Step 1c: Create harmonized goal_value if requested (--goal flag)
    if use_goal:
        df = create_harmonized_goal_value(df)
        original_df = create_harmonized_goal_value(original_df)

    # Step 2: Add pair intercept feature
    df = add_pair_intercept_feature(df)
    pairs_in_data = get_pairs_in_data(df)

    # Step 3: Compute sample weights (√n rule)
    df = compute_sample_weights(df)

    # Step 4: Build config dynamically
    config_dict, analysis_config = build_analysis_config(
        pairs_in_data=pairs_in_data,
        extra_params=extra_params,
        use_extras=use_extras,
        use_goal=use_goal,
    )

    # Step 5: Apply MCMC settings (override takes precedence over mode)
    if mcmc_override is not None:
        config_dict = apply_mcmc_override(
            config_dict,
            samples=mcmc_override["samples"],
            warmup=mcmc_override["warmup"],
            chains=mcmc_override["chains"],
        )
        analysis_config = AnalysisConfig.from_dict(config_dict)
    elif mcmc_mode is not None:
        config_dict = get_reduced_mcmc_config(config_dict, mode=mcmc_mode)
        analysis_config = AnalysisConfig.from_dict(config_dict)

    # Step 6: Determine implemented parameters
    # [NOTE] get_params_with_signal checks which params have variance in the data.
    # This is used for summary stats. The 'threat' exclusion for extras mode is done
    # earlier in build_analysis_config (Step 4) via EXCLUDED_WHEN_EXTRAS.
    implemented_params = get_params_with_signal(df, param_implementation)
    logger.info(f"Parameters with signal: {len(implemented_params)}/{len(ALL_PARAMS)}")

    # Step 7: Determine all params to fill (core + extras)
    all_params_to_fill = list(ALL_PARAMS)
    if use_extras and extra_params:
        all_params_to_fill = all_params_to_fill + list(extra_params.keys())

    # Step 8: Fill unimplemented with placeholders
    # [NOTE] This works correctly for params implemented in some variations but not
    # others. Placeholders are filled per-scenario, then feature_zeroing zeros out
    # the feature columns at the sample level for unimplemented params.
    category_order = get_category_order_from_config(config_dict)
    df = fill_unimplemented_with_placeholder(
        df,
        all_params=all_params_to_fill,
        category_order=category_order,
        param_implementation=param_implementation,
    )

    # Step 9: Apply weights for HiBayES
    df = apply_weights_for_hibayes(df)

    # Step 10: Ensure model_raw column exists
    if "model_raw" not in df.columns and "meta_model" in df.columns:
        df["model_raw"] = df["meta_model"]

    # Step 11: Inject dummy rows for effect coding
    categorical_features = get_categorical_features_from_config(config_dict)
    df = inject_dummy_rows(df, categorical_features)

    # Step 12: Fit models with feature zeroing
    fitted_models = _fit_bayesian_models_with_zeroing(
        df=df,
        analysis_config=analysis_config,
        original_df=original_df,
        param_implementation=param_implementation,
        extra_params=list(extra_params.keys()) if extra_params else None,
        extra_param_variations=extra_param_variations,
    )

    # Step 13: Build posteriors (includes trivial_logliks for RQ1 baseline)
    posteriors = build_posterior_data(fitted_models, implemented_params)

    # Step 14: Compute summary
    summary = compute_summary_stats(posteriors, implemented_params)

    # Add RQ1 results to summary
    rq1_results, _ = compute_rq1_with_eti(fitted_models)
    summary["rq1"] = rq1_results.to_dict()

    return FitResult(
        posteriors=posteriors,
        summary=summary,
        implemented_params=implemented_params,
        convergence_ok=fitted_models.convergence_ok,
        convergence_issues=fitted_models.convergence_issues,
        rq1_results=rq1_results,
    )


def _fit_bayesian_models_with_zeroing(
    df: pd.DataFrame,
    analysis_config: AnalysisConfig,
    original_df: pd.DataFrame,
    param_implementation: dict[str, list[str]],
    extra_params: list[str] | None = None,
    extra_param_variations: dict[str, list[str]] | None = None,
) -> FittedModels:
    """Fit Bayesian models with zeroing of unimplemented parameter features.

    Internal function that:
    1. Processes data through HiBayES
    2. Zeros out feature columns for unimplemented parameters
    3. Fits the models

    Args:
        df: DataFrame prepared for HiBayES (with dummy rows).
        analysis_config: HiBayES analysis configuration.
        original_df: Original DataFrame (without dummy rows) with 'scenario' column.
        param_implementation: Dict mapping scenario -> list of implemented params.
        extra_params: List of extra parameter names (for zeroing).
        extra_param_variations: Dict mapping extra param -> variations that implement it.

    Returns:
        FittedModels with fitted model results.
    """
    # Create minimal display (disabled for parallel execution)
    # [NOTE] Private attribute access - fragile but works; HiBayES doesn't expose public API
    display = ModellingDisplay()
    display._live = None  # type: ignore[reportAttributeAccessIssue]

    # Data-informed initialization
    # [NOTE] This initialization works better for single (model, variation) fits than
    # for pooled fits with many pairs. For pooled fits, the global mean base_rate may
    # not match any individual pair's rate well. This is probably responsible for some
    # the MCMC convergence issues that the current code suffers from.
    base_rate = float(df["score"].mean())
    models_config = create_data_informed_models(analysis_config, base_rate)

    # Process data
    logger.info("Processing data for model fitting...")
    try:
        state = process_data(
            analysis_config.data_process,
            display,
            data=df,
        )
        state._models = []
    except Exception as e:
        raise ModelFittingError(f"Data processing failed: {e}") from e

    # Zero out unimplemented parameter features
    logger.info("Zeroing out features for unimplemented parameters...")
    state = zero_unimplemented_features(
        state,
        original_df,
        param_implementation,
        extra_params=extra_params,
        extra_param_variations=extra_param_variations,
    )

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

    # Get model references
    try:
        strategic = get_model_by_tag(state, "strategic_only")
        non_strategic = get_model_by_tag(state, "non_strategic_only")
        combined = get_model_by_tag(state, "combined")
        trivial = get_model_by_tag(state, "trivial")
    except ValueError as e:
        raise ModelFittingError(str(e)) from e

    return FittedModels(
        state=state,
        strategic=strategic,
        non_strategic=non_strategic,
        combined=combined,
        trivial=trivial,
        convergence_ok=convergence_ok,
        convergence_issues=convergence_issues,
    )
