"""Unified weighting for pooled regression fitting.

All pooled fits use the same √n weighting rule:
- Each variation gets base weight 1/√n where n is the number of variations in that scenario
- Within each (model, variation) pair, samples share the pair's weight equally

Note: This means scenarios with more variations get MORE total weight (sublinearly).
A 3-variation scenario gets total weight √3 ≈ 1.73, a 2-variation scenario gets √2 ≈ 1.41,
and single-variation scenarios get weight 1.0. This is intentional - more variations
means more diverse signal, which should have more influence on the pooled estimates.
"""

import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)

# Variation weights based on √n rule
# AM: 3 variations -> each gets 1/√3
# PP: 3 variations -> each gets 1/√3
# SEM: 2 variations -> each gets 1/√2
# Single-variation scenarios: each gets 1.0
VARIATION_BASE_WEIGHTS: dict[str, float] = {
    # Agentic Misalignment (3 variations)
    "alert": 1 / math.sqrt(3),
    "leak-starsentinel": 1 / math.sqrt(3),
    "leak-doj": 1 / math.sqrt(3),
    # Power Preservation (3 variations)
    "threat": 1 / math.sqrt(3),
    "enhancement": 1 / math.sqrt(3),
    "expansion": 1 / math.sqrt(3),
    # SEM (2 variations)
    "classification": 1 / math.sqrt(2),
    "summarization": 1 / math.sqrt(2),
    # Single-variation scenarios
    "email_spam_filter": 1.0,
    "gpu_decision": 1.0,
    "hiding_reward_hacking": 1.0,
}


def compute_sample_weights(df: pd.DataFrame) -> pd.DataFrame:
    """Compute sample weights using the unified √n rule.

    Each variation gets base weight 1/√(n_variations_in_scenario).
    Within each (model, variation) pair, the pair's weight is split equally
    among samples. This ensures:
    - Scenarios with more variations contribute more (sublinearly via √n)
    - Models contribute equally within each variation
    - Samples contribute equally within each (model, variation) pair

    Args:
        df: DataFrame with 'meta_model' and 'variation' columns

    Returns:
        DataFrame with 'sample_weight' column added
    """
    df = df.copy()

    # Get variations present in the data
    variations_in_data = df["variation"].unique()

    # Filter to variations we have weights for
    missing_vars = [v for v in variations_in_data if v not in VARIATION_BASE_WEIGHTS]
    if missing_vars:
        raise ValueError(f"Unknown variations without weights: {missing_vars}")

    # Count samples per (model, variation) pair
    pair_counts = df.groupby(["meta_model", "variation"]).size()

    # Count models per variation (for normalizing within variation)
    models_per_variation = df.groupby("variation")["meta_model"].nunique()

    # Compute total effective weight for normalization
    # This is sum of variation weights across all variations present in data
    total_effective_weight = sum(
        VARIATION_BASE_WEIGHTS[var] for var in variations_in_data
    )

    # Target: total sample weight equals n_samples (for numerical stability)
    n_samples = len(df)
    normalization_factor = n_samples / total_effective_weight

    # Compute per-sample weights
    def get_weight(row: pd.Series) -> float:
        var: str = str(row["variation"])
        mdl: str = str(row["meta_model"])

        # Base weight for this variation
        var_weight = VARIATION_BASE_WEIGHTS[var]

        # Number of models in this variation
        n_models = models_per_variation[var]

        # Number of samples in this (model, variation) pair
        n_samples_in_pair = pair_counts[(mdl, var)]

        # Per-sample weight:
        # (var_weight / n_models) gives weight per model within variation
        # Divide by n_samples_in_pair to split among samples
        # Multiply by normalization_factor to scale
        return float((var_weight / n_models / n_samples_in_pair) * normalization_factor)

    df["sample_weight"] = df.apply(get_weight, axis=1)

    # Verify weights sum to n_samples
    weight_sum = df["sample_weight"].sum()
    if abs(weight_sum - n_samples) > 1e-6:
        logger.warning(f"Weight sum {weight_sum} != n_samples {n_samples}")

    # Log summary
    logger.info(
        f"Computed weights: {len(pair_counts)} (model, variation) pairs, "
        f"{n_samples} samples, total_effective_weight={total_effective_weight:.2f}"
    )

    return df


def apply_weights_for_hibayes(df: pd.DataFrame) -> pd.DataFrame:
    """Apply sample weights via n_total and score columns for HiBayES.

    HiBayES expects:
    - n_total: weight of each observation
    - score: weighted outcome (weight * binary_outcome)

    Args:
        df: DataFrame with 'sample_weight' and 'meta_score' columns

    Returns:
        DataFrame with 'n_total' and 'score' columns set
    """
    df = df.copy()

    if "sample_weight" not in df.columns:
        raise ValueError(
            "DataFrame must have 'sample_weight' column. Call compute_sample_weights() first."
        )

    if "meta_score" not in df.columns:
        raise ValueError("DataFrame must have 'meta_score' column")

    df["n_total"] = df["sample_weight"]
    df["score"] = df["sample_weight"] * df["meta_score"]

    return df
