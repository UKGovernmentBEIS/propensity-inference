"""Feature zeroing for unimplemented parameters.

When pooling across variations, some parameters are not implemented in some
scenarios. For samples from those scenarios, we zero out the effect-coded
feature columns for unimplemented parameters. This ensures those samples
don't influence the coefficient estimation for those parameters.

================================================================================
HOW THIS WORKS WITH DATA_PREP.PY
================================================================================

This module works together with fill_unimplemented_with_placeholder() in data_prep.py.
The two-step process is necessary because of how effect coding works:

**What is effect coding?**
Effect coding transforms a categorical variable with K categories into K-1 numeric
columns. For example, `threat` with categories ["replacement", "other", "none"] becomes:
  - threat[replacement]: 1 if replacement, -1 if none (reference), 0 otherwise
  - threat[other]: 1 if other, -1 if none (reference), 0 otherwise

The reference category (last alphabetically, or _DUMMY_ if present) gets -1 in all
columns. Coefficients are constrained to sum to zero.

**Why two steps?**

Step 1 - fill_unimplemented_with_placeholder() in data_prep.py:
    Effect coding requires valid categorical values for ALL rows - it crashes on NaN.
    For parameters not implemented in a scenario (e.g., alert scenario doesn't have
    goal_present), we fill NaN with an arbitrary valid category (e.g., "true").
    The choice doesn't matter because Step 2 will zero out the features anyway.

Step 2 - zero_unimplemented_features() HERE:
    After HiBayES runs effect coding and creates numeric feature columns like
    "threat[replacement]", we set those columns to 0.0 for samples where the
    parameter isn't implemented. Zero features contribute nothing to the linear
    predictor (0 * β = 0), so these samples don't influence coefficient estimates.

**Why _DUMMY_ categories?**
See lib/analysis/effect_coding.py for full explanation. In short: HiBayES effect
coding creates asymmetric variance for the derived (reference) coefficient. Adding
_DUMMY_ as the last category makes it the derived one, giving symmetric variance
to all real categories. The _DUMMY_ row is injected via inject_dummy_rows() with
n_total=0 so it doesn't affect the likelihood.

**model_variation is NEVER zeroed** - it's the pair-specific intercept, always present.

**Special handling for goal_value and goal_value_harmonized:**
    When goal_conflict=false AND goal_present=false, goal_value is meaningless
    and should be zeroed even if the scenario implements it.

Tests: See tests/pooled_fitting/test_placeholder_and_zeroing.py
"""

import logging
from typing import Any

import jax.numpy as jnp
import numpy as np
import pandas as pd

from lib.paper_style import ALL_PARAMS
from lib.pooled_fitting.data_prep import PARAMETER_IMPLEMENTATION

logger = logging.getLogger(__name__)


def build_goal_value_inapplicable_mask(df: pd.DataFrame) -> np.ndarray:
    """Build mask for rows where goal_value is inapplicable.

    goal_value is inapplicable when both goal_conflict=false AND goal_present=false.
    In these cases, there's no goal to have a value, so the feature should be zeroed.

    Args:
        df: DataFrame with goal_conflict and goal_present columns

    Returns:
        Boolean array where True means goal_value should be zeroed
    """
    mask = np.zeros(len(df), dtype=bool)

    if "goal_conflict" in df.columns and "goal_present" in df.columns:
        # goal_value is inapplicable when BOTH are false
        goal_conflict_false = df["goal_conflict"].astype(str).str.lower() == "false"
        goal_present_false = df["goal_present"].astype(str).str.lower() == "false"
        mask = goal_conflict_false & goal_present_false

        n_inapplicable = mask.sum()
        if n_inapplicable > 0:
            logger.info(
                f"goal_value inapplicable for {n_inapplicable}/{len(df)} samples "
                f"(goal_conflict=false AND goal_present=false)"
            )

    return mask


def zero_unimplemented_features(
    state: Any,
    original_df: pd.DataFrame,
    param_implementation: dict[str, list[str]] | None = None,
    extra_params: list[str] | None = None,
    extra_param_variations: dict[str, list[str]] | None = None,
) -> Any:
    """Zero out effect-coded feature columns for unimplemented parameters.

    For each sample, if the parameter is not implemented in that sample's
    scenario, all effect-coded columns for that parameter are set to 0.

    This ensures those samples don't influence the coefficient estimation
    for that parameter.

    Note: 'model_variation' is never zeroed - it's the intercept feature.

    Special handling:
    - goal_value is zeroed when goal_conflict=false AND goal_present=false
    - Extra params are zeroed based on variation (not scenario)

    Args:
        state: HiBayES state with features dict.
        original_df: Original DataFrame with 'scenario' and 'variation' columns.
        param_implementation: Dict mapping scenario -> list of implemented params.
            Defaults to PARAMETER_IMPLEMENTATION.
        extra_params: List of extra parameter names being used (beyond core 12).
        extra_param_variations: Dict mapping extra param -> list of variations
            that implement it. If None, extra params use scenario-based lookup.

    Returns:
        Modified state with zeroed features.
    """
    if param_implementation is None:
        param_implementation = PARAMETER_IMPLEMENTATION

    if extra_params is None:
        extra_params = []

    if state.features is None:
        logger.warning("No features in state to modify")
        return state

    # Get number of real samples (before dummy rows)
    n_real_samples = len(original_df)

    # Build scenario and variation arrays for real samples
    scenarios = original_df["scenario"].values
    variations = (
        original_df["variation"].values if "variation" in original_df.columns else None
    )

    # Validate all scenarios are known
    unique_scenarios = set(original_df["scenario"].unique())
    unknown_scenarios = unique_scenarios - set(param_implementation.keys())
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenarios in data: {unknown_scenarios}. "
            f"Add them to PARAMETER_IMPLEMENTATION in data_prep.py"
        )

    # Validate all extra params have variation mappings
    if extra_params and extra_param_variations:
        unknown_extra_params = set(extra_params) - set(extra_param_variations.keys())
        if unknown_extra_params:
            raise ValueError(
                f"Extra params without variation mappings: {unknown_extra_params}. "
                f"Add them to extra_param_variations."
            )

    # Build mask for each parameter: which samples should have this param zeroed
    # Shape: (n_real_samples,) boolean array - True means zero this param
    param_masks: dict[str, np.ndarray] = {}

    # Core parameters: use scenario-based implementation
    for param in ALL_PARAMS:
        mask = np.zeros(n_real_samples, dtype=bool)
        for i, scenario in enumerate(scenarios):
            implemented = set(param_implementation[scenario])
            if param not in implemented:
                mask[i] = True
        param_masks[param] = mask
        n_zeroed = mask.sum()
        if n_zeroed > 0:
            logger.info(
                f"Zeroing {param} for {n_zeroed}/{n_real_samples} samples "
                f"from non-implementing scenarios"
            )

    # Extra parameters: use variation-based implementation
    if extra_params and extra_param_variations and variations is not None:
        for param in extra_params:
            # Validation already done above, so direct access is safe
            implementing_variations = set(extra_param_variations[param])
            mask = np.zeros(n_real_samples, dtype=bool)
            for i, var in enumerate(variations):
                if var not in implementing_variations:
                    mask[i] = True
            param_masks[param] = mask
            n_zeroed = mask.sum()
            if n_zeroed > 0:
                logger.info(
                    f"Zeroing extra param {param} for {n_zeroed}/{n_real_samples} samples "
                    f"from non-implementing variations"
                )

    # Special handling for goal_value: zero when goal_conflict=false AND goal_present=false.
    # [NOTE] We zero the *feature columns* (the effect-coded values), not the raw data.
    # Effect coding transforms categorical values into numeric contrasts; zeroing those
    # columns makes these samples contribute nothing to the goal_value coefficient estimates.
    # We can't just set the raw value to "none" because effect coding has already happened.
    if "goal_value" in param_masks or "goal_value" in extra_params:
        goal_value_inapplicable = build_goal_value_inapplicable_mask(original_df)
        if "goal_value" in param_masks:
            # Combine with existing mask (OR)
            param_masks["goal_value"] = (
                param_masks["goal_value"] | goal_value_inapplicable
            )
        else:
            param_masks["goal_value"] = goal_value_inapplicable

    # Special handling for goal_value_harmonized (used with --goal flag):
    # 1. Zero for non-implementing scenarios (using PARAMETER_IMPLEMENTATION)
    # 2. Zero when goal_conflict=false AND goal_present=false (goal has no meaning)
    has_goal_value_harmonized = any(
        f.startswith("goal_value_harmonized[") for f in state.features
    )
    if has_goal_value_harmonized:
        # Scenario-based zeroing (same logic as core params)
        # Scenarios already validated at function entry, so direct access is safe
        scenario_mask = np.zeros(n_real_samples, dtype=bool)
        for i, scenario in enumerate(scenarios):
            implemented = set(param_implementation[scenario])
            if "goal_value_harmonized" not in implemented:
                scenario_mask[i] = True

        n_scenario_zeroed = scenario_mask.sum()
        if n_scenario_zeroed > 0:
            logger.info(
                f"Zeroing goal_value_harmonized for {n_scenario_zeroed}/{n_real_samples} samples "
                f"from non-implementing scenarios"
            )

        # Goal-inapplicable zeroing (goal_conflict=false AND goal_present=false)
        goal_value_inapplicable = build_goal_value_inapplicable_mask(original_df)

        # Combine masks (OR)
        param_masks["goal_value_harmonized"] = scenario_mask | goal_value_inapplicable

    # Now modify the features
    # Features are JAX arrays with shape (n_total_samples,) or (n_total_samples, n_categories)
    # The feature names follow patterns like "goal_present[true]", "threat[replacement]"

    n_features_zeroed = 0
    for feature_name, feature_array in list(state.features.items()):
        # Parse feature name to get parameter (e.g., "threat[replacement]" -> "threat")
        # Effect-coded features have format "param[category]"
        # Skip features that don't match this pattern (e.g., 'obs', 'n_total')
        if "[" not in feature_name or not feature_name.endswith("]"):
            continue  # Not an effect-coded feature, skip

        param_name = feature_name.split("[")[0]

        # Skip model_variation - it's the intercept, never zeroed
        if param_name == "model_variation":
            continue

        # Skip if not a parameter we track
        if param_name not in param_masks:
            continue

        mask = param_masks[param_name]
        if not mask.any():
            continue

        # Convert to numpy for modification
        arr = np.array(feature_array)

        # Only modify real samples (not dummy rows at the end)
        if len(arr.shape) == 1:
            arr[:n_real_samples][mask] = 0.0
        elif len(arr.shape) == 2:
            arr[:n_real_samples][mask, :] = 0.0

        # Convert back to JAX array
        state.features[feature_name] = jnp.array(arr)
        n_features_zeroed += 1

    logger.info(f"Zeroed features for {n_features_zeroed} feature columns")

    return state


def get_params_with_signal(
    original_df: pd.DataFrame,
    param_implementation: dict[str, list[str]] | None = None,
) -> list[str]:
    """Get list of parameters that have non-zero signal in the data.

    A parameter has signal if at least some samples come from scenarios
    that implement it. Used in core.py for summary stats.

    Args:
        original_df: DataFrame with 'scenario' column
        param_implementation: Dict mapping scenario -> list of implemented params

    Returns:
        List of parameter names that have non-zero signal
    """
    if param_implementation is None:
        param_implementation = PARAMETER_IMPLEMENTATION

    params_with_signal = []
    scenarios = original_df["scenario"].unique()

    # Validate all scenarios are known
    unknown_scenarios = set(scenarios) - set(param_implementation.keys())
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenarios in data: {unknown_scenarios}. "
            f"Add them to PARAMETER_IMPLEMENTATION in data_prep.py"
        )

    for param in ALL_PARAMS:
        has_signal = False
        for scenario in scenarios:
            implemented = set(param_implementation[scenario])
            if param in implemented:
                has_signal = True
                break
        if has_signal:
            params_with_signal.append(param)

    return params_with_signal
