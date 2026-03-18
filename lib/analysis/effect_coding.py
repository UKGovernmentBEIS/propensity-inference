"""Effect coding utilities for equal-variance coefficient estimation.

This module provides utilities to achieve equal variance across all levels
of categorical variables when using effect coding (sum-to-zero constraint).

The Problem:
    Standard effect coding samples N-1 "free" coefficients and computes the
    Nth as -sum(others). This makes the Nth coefficient have ~sqrt(N-1) times
    higher variance than the others.

The Solution:
    1. Add a dummy category "_DUMMY_" to each categorical variable
    2. Add a zero-weight data row (n_total=0) so the dummy is "present"
    3. HiBayES samples all N+1 coefficients freely
    4. The dummy absorbs the high-variance sum-to-zero constraint
    5. Post-hoc: normalize all N+1 coefficients to sum to 0, discard dummy

Usage:
    # Before fitting:
    df = inject_dummy_rows(df, categorical_features)

    # After fitting, when extracting coefficients:
    normalized = normalize_effect_coded_coefficients(raw_coefficients)
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Dummy category name - must match what's in the config category_order
DUMMY_CATEGORY = "_DUMMY_"


def inject_dummy_rows(
    df: pd.DataFrame,
    categorical_features: list[str],
    score_column: str = "meta_score",
    n_total_column: str = "n_total",
) -> pd.DataFrame:
    """Inject zero-weight dummy rows for effect coding.

    For each categorical feature, adds a row with the dummy category value.
    These rows have n_total=0, so they contribute nothing to the likelihood
    but ensure the dummy category is "present" in the data.

    Args:
        df: Input DataFrame with categorical features.
        categorical_features: List of categorical column names.
        score_column: Name of the score/outcome column.
        n_total_column: Name of the n_total column (will be created if missing).

    Returns:
        DataFrame with dummy rows appended.
    """
    df = df.copy()

    # Ensure n_total column exists
    if n_total_column not in df.columns:
        df[n_total_column] = 1

    # Create dummy rows - one for each categorical feature combination
    # We need a single row where ALL categorical features have the dummy value
    dummy_row: dict[str, Any] = {}

    # Copy structure from first row
    for col in df.columns:
        if col in categorical_features:
            dummy_row[col] = DUMMY_CATEGORY
        elif col == score_column:
            dummy_row[col] = 0  # Doesn't matter since n_total=0
        elif col == n_total_column:
            dummy_row[col] = 0  # Zero weight - contributes nothing to likelihood
        elif col == "score":
            dummy_row[col] = 0  # HiBayES expects 'score' column
        else:
            # For other columns, use a sensible default
            if df[col].dtype == "object" or df[col].dtype.name == "category":
                dummy_row[col] = df[col].iloc[0] if len(df) > 0 else ""
            else:
                dummy_row[col] = 0

    # Append dummy row
    dummy_df = pd.DataFrame([dummy_row])
    result = pd.concat([df, dummy_df], ignore_index=True)

    # Verify _DUMMY_ is now present in all categorical features
    for feature in categorical_features:
        if DUMMY_CATEGORY not in result[feature].values:
            raise AssertionError(
                f"inject_dummy_rows failed: {DUMMY_CATEGORY} not found in '{feature}' column. "
                f"Unique values: {result[feature].unique().tolist()}"
            )

    logger.info(
        f"Injected dummy row with {DUMMY_CATEGORY} for {len(categorical_features)} "
        f"categorical features. Total rows: {len(df)} -> {len(result)}"
    )

    return result


def normalize_effect_coded_coefficients(
    coefficients: dict[str, np.ndarray],
    remove_dummy: bool = True,
) -> dict[str, np.ndarray]:
    """Normalize effect-coded coefficients to sum to zero.

    For each variable, computes the mean across REAL categories (excluding
    dummy), then subtracts that mean from each real category so they sum to zero.

    The dummy category is discarded after normalization since its only purpose
    was to absorb the high-variance sum-to-zero constraint during sampling.

    Args:
        coefficients: Dict mapping coefficient names to posterior samples.
            Names should be in format "variable_effects[category]".
        remove_dummy: If True, remove dummy category coefficients.

    Returns:
        Dict with normalized coefficients where real categories sum to zero.
    """
    from lib.analysis.coefficients import parse_coefficient_name

    # Group coefficients by variable
    variables: dict[str, list[tuple[str, str, np.ndarray]]] = {}

    for name, samples in coefficients.items():
        parsed = parse_coefficient_name(name)
        if parsed is None:
            continue
        var_name, category = parsed
        if var_name not in variables:
            variables[var_name] = []
        variables[var_name].append((name, category, samples))

    # Normalize each variable
    result: dict[str, np.ndarray] = {}

    for var_name, category_data in variables.items():
        # Separate real categories from dummy
        real_data = [(n, c, s) for n, c, s in category_data if c != DUMMY_CATEGORY]

        if not real_data:
            # No real categories, skip
            continue

        # Skip normalization for model_variation - these are independent intercepts
        # with N(-3, 3²) priors, not deviations from a mean
        if var_name == "model_variation":
            for name, category, samples in real_data:
                result[name] = samples
            continue

        # Stack only real category samples: shape (n_real_categories, n_draws)
        real_samples = np.stack([samples for _, _, samples in real_data], axis=0)

        # Compute mean across real categories for each draw
        mean_per_draw = np.mean(real_samples, axis=0)  # shape (n_draws,)

        # Subtract mean to normalize (real categories now sum to zero)
        normalized = real_samples - mean_per_draw[np.newaxis, :]

        # Store results (only real categories)
        for i, (name, category, _) in enumerate(real_data):
            result[name] = normalized[i]

        # Optionally include dummy (not normalized, raw value)
        if not remove_dummy:
            for name, category, samples in category_data:
                if category == DUMMY_CATEGORY:
                    result[name] = samples

    # Copy non-effect coefficients (intercept, etc.) unchanged
    for name, samples in coefficients.items():
        parsed = parse_coefficient_name(name)
        if parsed is None:
            # Not an effect coefficient, copy as-is
            result[name] = samples

    return result


def get_categorical_features_from_config(config: dict[str, Any]) -> list[str]:
    """Extract categorical feature names from analysis config.

    Args:
        config: Full analysis configuration dictionary.

    Returns:
        List of categorical feature names.
    """
    data_process = config.get("data_process", {})
    processors = data_process.get("processors", [])

    for proc in processors:
        if isinstance(proc, dict) and "extract_features" in proc:
            return proc["extract_features"].get("categorical_features", [])

    return []


def add_dummy_to_category_order(category_order: list[str]) -> list[str]:
    """Add dummy category to the end of category order list.

    Args:
        category_order: Original category order.

    Returns:
        Category order with DUMMY_CATEGORY appended.
    """
    if DUMMY_CATEGORY not in category_order:
        return category_order + [DUMMY_CATEGORY]
    return category_order
