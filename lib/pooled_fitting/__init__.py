"""Unified pooled regression fitting framework.

[NOTE] This __init__.py is intentionally non-empty to provide a clean public API.
Per CLAUDE.md, __init__.py should be empty unless there's good reason - here we
export the commonly-used functions to simplify imports for callers.
(Not sure if it's a good reason.)

This module provides a unified approach to fitting Bayesian regressions
across different pooling strategies:

- per-model: Pool across all variations for a single model
- per-variation: Pool across all models for a single variation
- per-quartile: Pool across all variations for models in a capability quartile
- single: Fit a single (model, variation) pair
- all-combined: Pool all 23 models × 11 variations into one giant regression

All modes use:
- Pair-specific intercepts α_{m,v} for each (model, variation) pair in the data
- √n weighting for variations within scenarios
- Zero-out for unimplemented parameters
- All 12 parameters (some may be uninformative if all-zero)

Usage:
    from lib.pooled_fitting import fit_pooled_regression, FitResult

    # Basic usage
    result = fit_pooled_regression(df=data, mcmc_mode="ultra")

    # With custom MCMC override (for testing)
    result = fit_pooled_regression(
        df=data,
        mcmc_override={"samples": 50, "warmup": 25, "chains": 1},
    )
"""

from lib.pooled_fitting.core import FitResult, fit_pooled_regression
from lib.pooled_fitting.data_prep import (
    ALL_VARIATIONS,
    add_pair_intercept_feature,
    create_combined_ai_type,
    harmonize_action_efficacy,
    load_all_samples,
)
from lib.pooled_fitting.quality import (
    load_quality_metadata,
    save_quality_metadata,
    should_fit,
    update_quality_metadata,
)
from lib.pooled_fitting.weighting import compute_sample_weights

__all__ = [
    "fit_pooled_regression",
    "FitResult",
    "load_all_samples",
    "harmonize_action_efficacy",
    "create_combined_ai_type",
    "add_pair_intercept_feature",
    "compute_sample_weights",
    "load_quality_metadata",
    "save_quality_metadata",
    "should_fit",
    "update_quality_metadata",
    "ALL_VARIATIONS",
]
