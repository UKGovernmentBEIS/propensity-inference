"""Data loading and preparation for pooled regression fitting."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Sample cache directory
SAMPLES_DIR = Path(__file__).parent.parent.parent / "paper_cache" / "samples"

# All variations to process (11 total)
ALL_VARIATIONS = [
    ("agentic_misalignment_v2", "alert"),
    ("agentic_misalignment_v2", "leak-starsentinel"),
    ("agentic_misalignment_v2", "leak-doj"),
    ("email_spam_filter_v2", "email_spam_filter"),
    ("gpu_decision_email_assistant", "gpu_decision"),
    ("hiding_reward_hacking", "hiding_reward_hacking"),
    ("power_preservation", "threat"),
    ("power_preservation", "enhancement"),
    ("power_preservation", "expansion"),
    ("sem_v2", "classification"),
    ("sem_v2", "summarization"),
]

# Parameter implementation by scenario
# Defines which parameters are implemented (ablated) in which scenarios.
#
# A parameter is "implemented" if it has multiple values that vary across tasks.
# Parameters NOT listed here either:
#   - Have constant values (no ablation) -> features get zeroed via feature_zeroing.py
#   - Don't exist in the scenario -> NaN filled with placeholder, then zeroed
#
# goal_value_harmonized note:
#   Only scenarios that actually ABLATE goal values should list goal_value_harmonized.
#   Scenarios without goal_value ablation (hiding_reward_hacking, email_spam_filter_v2)
#   get "none" filled in by create_harmonized_goal_value(), but this contributes no
#   signal - their features are zeroed because goal_value_harmonized isn't listed here.
#
PARAMETER_IMPLEMENTATION = {
    "agentic_misalignment_v2": [
        "goal_present",
        "goal_conflict",
        "goal_value_harmonized",  # Ablates 8 goal values
        "threat",
        "cot_privacy",
        "action_oversight",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date_month_year",
    ],
    "hiding_reward_hacking": [
        # Missing: goal_present, goal_conflict, goal_value_harmonized, filler_richness
        # No goal ablation - all samples get goal_value="none"
        "threat",
        "cot_privacy",
        "action_oversight",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "date_month_year",
    ],
    "email_spam_filter_v2": [
        # Missing: goal_conflict, goal_value_harmonized, threat
        # No goal ablation - all samples get goal_value="none"
        "goal_present",
        "cot_privacy",
        "action_oversight",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date_month_year",
    ],
    "sem_v2": [
        # Missing: action_oversight
        "goal_present",
        "goal_conflict",
        "goal_value_harmonized",
        "threat",
        "cot_privacy",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date_month_year",
    ],
    "power_preservation": [
        # Note on threat: power_preservation has limited variation on threat.
        # - threat variation: 50% "replacement", 50% "other" (ablated)
        # - enhancement variation: 100% "other" (not ablated)
        # - expansion variation: 100% "other" (not ablated)
        # It's correct to include threat here because:
        # 1. When threat is ablated (threat variation), we get valid signal about
        #    the difference between "replacement" and "other". The intercept
        #    captures the mean, coefficients capture deviations.
        # 2. When threat is constant (enhancement/expansion), the model-variation
        #    intercept absorbs most of the effect. There is a small prior-mediated
        #    influence: the prior N(0,σ²) on threat coefficients pulls them toward
        #    zero while the intercept absorbs the rest. This is minor - the
        #    dominant signal comes from variations with actual ablation.
        # 3. The "none" coefficient is estimated entirely from other scenarios
        #    (agentic_misalignment, gpu_decision, etc.) which have full ablation.
        "goal_present",
        "goal_conflict",
        "goal_value_harmonized",
        "threat",
        "cot_privacy",
        "action_oversight",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date_month_year",
    ],
    "gpu_decision_email_assistant": [
        "goal_present",
        "goal_conflict",
        "goal_value_harmonized",
        "threat",
        "cot_privacy",
        "action_oversight",
        "action_efficacy_binary",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date_month_year",
    ],
}


def load_all_samples() -> pd.DataFrame:
    """Load and concatenate samples from all scenario-variations.

    Loads parquet files from paper_cache/samples/{scenario}/{variation}/.
    Download from S3 first: aws s3 sync s3://$S3_BUCKET/$PROPENSITY_S3_ROOT/paper_cache/samples/ paper_cache/samples/

    Returns:
        DataFrame with columns including 'scenario', 'variation', 'meta_model',
        'meta_score', and all parameter columns.
    """
    all_dfs = []

    for scenario, variation in ALL_VARIATIONS:
        var_dir = SAMPLES_DIR / scenario / variation
        if not var_dir.exists():
            raise FileNotFoundError(
                f"No sample cache for {scenario}/{variation}. "
                f"Download from S3: aws s3 sync s3://$S3_BUCKET/"
                f"$PROPENSITY_S3_ROOT/paper_cache/samples/ paper_cache/samples/"
            )

        parquet_files = list(var_dir.glob("samples_*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(f"No parquet files in {var_dir}")

        dfs = [pd.read_parquet(pf) for pf in parquet_files]
        df = pd.concat(dfs, ignore_index=True)
        df["scenario"] = scenario
        df["variation"] = variation
        all_dfs.append(df)
        logger.info(f"Loaded {len(df)} samples from {scenario}/{variation}")

    combined_df = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Total samples loaded: {len(combined_df)}")
    return combined_df


# Mapping from bidirectional goal values to the AI's original goal (unidirectional)
BIDIRECTIONAL_GOAL_MAP = {
    # power_preservation and sem_v2 use bidirectional format
    "america_global": "america",
    "global_america": "global",
    "safety_acceleration": "safety",
    "acceleration_safety": "acceleration",
    "ethical_pragmatic": "ethical",
    "pragmatic_ethical": "pragmatic",
    "individualism_collectivism": "individualism",
    "collectivism_individualism": "collectivism",
    # sem_v2 also has individual/collective variants
    "individual_collective": "individualism",
    "collective_individual": "collectivism",
}

# The 8 canonical goal values (plus "none" for when no goal applies)
CANONICAL_GOAL_VALUES = [
    "none",  # Reference category
    "america",
    "global",
    "safety",
    "acceleration",
    "ethical",
    "pragmatic",
    "individualism",
    "collectivism",
]


def create_harmonized_goal_value(df: pd.DataFrame) -> pd.DataFrame:
    """Create harmonized goal_value_harmonized column for GLM fitting.

    This function:
    1. Maps bidirectional goal values (e.g., america_global) to unidirectional (america)
    2. Sets goal_value to "none" when goal_present=false AND goal_conflict=false
    3. Maps NaN/null/empty goal values to "none"
    4. Ensures all values are in the canonical set

    Args:
        df: DataFrame with goal_value, goal_present, goal_conflict columns

    Returns:
        DataFrame with new goal_value_harmonized column
    """
    df = df.copy()

    if "goal_value" not in df.columns:
        logger.warning("goal_value column not found, creating with 'none'")
        df["goal_value_harmonized"] = "none"
        return df

    # Identify NaN values before converting to string.
    # NaN occurs for scenarios that don't ablate goal_value (email_spam_filter_v2,
    # hiding_reward_hacking). These get "none" here, but since goal_value_harmonized
    # is NOT listed in PARAMETER_IMPLEMENTATION for these scenarios, their features
    # will be zeroed by feature_zeroing.py. The "none" value is just a placeholder
    # to satisfy effect coding - it contributes no signal to coefficient estimation.
    nan_mask = df["goal_value"].isna()
    n_nan = nan_mask.sum()

    # Convert to string
    harmonized = df["goal_value"].astype(str).copy()

    # Map NaN values to "none"
    if n_nan > 0:
        harmonized[nan_mask] = "none"
        logger.info(f"Mapped {n_nan} NaN goal values to 'none'")

    # Map bidirectional to unidirectional
    for bidirectional, unidirectional in BIDIRECTIONAL_GOAL_MAP.items():
        mask = harmonized == bidirectional
        n_mapped = mask.sum()
        if n_mapped > 0:
            harmonized[mask] = unidirectional
            logger.info(
                f"Mapped {n_mapped} samples: {bidirectional} → {unidirectional}"
            )

    # Set to "none" when goal_present=false AND goal_conflict=false
    if "goal_present" in df.columns and "goal_conflict" in df.columns:
        goal_present_false = df["goal_present"].astype(str).str.lower() == "false"
        goal_conflict_false = df["goal_conflict"].astype(str).str.lower() == "false"
        both_false = goal_present_false & goal_conflict_false

        n_none = both_false.sum()
        if n_none > 0:
            harmonized[both_false] = "none"
            logger.info(
                f"Set {n_none} samples to 'none' (goal_present=false AND goal_conflict=false)"
            )

    # Validate all values are in canonical set
    unique_values = set(harmonized.unique())
    canonical_set = set(CANONICAL_GOAL_VALUES)
    invalid = unique_values - canonical_set

    if invalid:
        logger.warning(f"Found non-canonical goal values: {invalid}")
        # Map any remaining invalid values to "none" with warning
        for val in invalid:
            mask = harmonized == val
            n_invalid = mask.sum()
            if n_invalid > 0:
                harmonized[mask] = "none"
                logger.warning(f"Mapped {n_invalid} samples with '{val}' → 'none'")

    df["goal_value_harmonized"] = harmonized

    # Log distribution
    value_counts = df["goal_value_harmonized"].value_counts()
    logger.info(f"Goal value distribution:\n{value_counts.to_string()}")

    return df


def harmonize_action_efficacy(df: pd.DataFrame) -> pd.DataFrame:
    """Harmonize action_efficacy_binary values across scenarios.

    Agentic_misalignment_v2 uses 'true'/'false' while all other scenarios
    use 'effective'/'not_effective'. This maps AM's values to the standard.
    """
    df = df.copy()

    if "action_efficacy_binary" not in df.columns:
        return df

    # Map AM's values to standard
    am_mask = df["scenario"] == "agentic_misalignment_v2"
    n_am = am_mask.sum()

    if n_am > 0:
        original_values = df.loc[am_mask, "action_efficacy_binary"].unique()
        logger.info(
            f"Harmonizing {n_am} AM samples with values: {sorted(original_values)}"
        )

        df.loc[am_mask, "action_efficacy_binary"] = df.loc[
            am_mask, "action_efficacy_binary"
        ].map({"true": "effective", "false": "not_effective"})

        new_values = df.loc[am_mask, "action_efficacy_binary"].unique()
        logger.info(f"After harmonization: {sorted(new_values)}")

    return df


def create_combined_ai_type(df: pd.DataFrame) -> pd.DataFrame:
    """Combine exfil_model_type and punishment_type into single ai_type column.

    [NOTE] Used in core.py when use_extras=True. These two parameters are
    perfectly confounded in the alert variation (always have the same value),
    so we combine them into a single parameter to avoid collinearity.
    """
    df = df.copy()

    # Check if either column exists
    has_exfil = "exfil_model_type" in df.columns
    has_punishment = "punishment_type" in df.columns

    if not has_exfil and not has_punishment:
        return df

    # Create combined column - use exfil_model_type if available, else punishment_type
    if has_exfil:
        df["ai_type"] = df["exfil_model_type"]
    elif has_punishment:
        df["ai_type"] = df["punishment_type"]

    # Log the change
    if "ai_type" in df.columns:
        non_null = df["ai_type"].notna().sum()
        if non_null > 0:
            logger.info(
                f"Created ai_type column from exfil_model_type/punishment_type: {non_null} values"
            )

    return df


def add_pair_intercept_feature(df: pd.DataFrame) -> pd.DataFrame:
    """Add model_variation feature for pair-specific intercepts.

    Creates a new column combining meta_model and variation for use as
    a categorical intercept feature.
    """
    df = df.copy()
    df["model_variation"] = (
        df["meta_model"].astype(str) + "_" + df["variation"].astype(str)
    )
    return df


def get_pairs_in_data(df: pd.DataFrame) -> list[str]:
    """Get list of unique (model, variation) pair identifiers in the data."""
    if "model_variation" not in df.columns:
        df = add_pair_intercept_feature(df)
    return sorted(df["model_variation"].unique().tolist())


def fill_unimplemented_with_placeholder(
    df: pd.DataFrame,
    all_params: list[str],
    category_order: dict[str, list[str]],
    param_implementation: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Fill unimplemented parameter columns with placeholder values.

    This is Step 1 of a two-step process for handling unimplemented parameters.
    See lib/pooled_fitting/feature_zeroing.py docstring for full explanation.

    Step 1 (HERE): Effect coding requires valid categorical values for all rows -
        it crashes on NaN. For parameters not implemented in a scenario (e.g.,
        alert scenario doesn't have goal_present), fill NaN with an arbitrary
        valid category. The choice doesn't matter because Step 2 zeros the features.

    Step 2 (zero_unimplemented_features in feature_zeroing.py): After HiBayES runs
        effect coding and creates numeric feature columns like "threat[replacement]",
        set those columns to 0.0 for samples where the parameter isn't implemented.

    The placeholder is the first non-_DUMMY_ category from category_order.

    IMPORTANT: This only fills NaN for UNIMPLEMENTED parameters. If an implemented
    parameter has NaN values, that's a data bug and effect coding will fail
    (which is correct - we want to catch data bugs early).

    Tests: See tests/pooled_fitting/test_placeholder_and_zeroing.py

    Args:
        df: DataFrame with 'scenario' column
        all_params: List of all parameter names
        category_order: Dict mapping param -> list of categories
        param_implementation: Override for PARAMETER_IMPLEMENTATION

    Returns:
        DataFrame with placeholders filled
    """
    if param_implementation is None:
        param_implementation = PARAMETER_IMPLEMENTATION

    df = df.copy()

    # Validate all scenarios are known
    unique_scenarios = set(df["scenario"].unique())
    unknown_scenarios = unique_scenarios - set(param_implementation.keys())
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenarios in data: {unknown_scenarios}. "
            f"Add them to PARAMETER_IMPLEMENTATION."
        )

    for scenario in df["scenario"].unique():
        implemented = set(param_implementation[scenario])

        scenario_mask = df["scenario"] == scenario

        for param in all_params:
            if param not in implemented and param in df.columns:
                # Get the first non-DUMMY category as placeholder
                if param not in category_order:
                    raise ValueError(
                        f"Parameter '{param}' not in category_order. "
                        f"Available: {list(category_order.keys())}"
                    )
                categories = category_order[param]
                placeholder = None
                for cat in categories:
                    if cat != "_DUMMY_":
                        placeholder = cat
                        break

                if placeholder is None:
                    raise ValueError(
                        f"No valid (non-_DUMMY_) placeholder for '{param}'. "
                        f"Categories: {categories}"
                    )

                # Count and fill
                null_mask = scenario_mask & df[param].isna()
                n_filled = null_mask.sum()
                if n_filled > 0:
                    df.loc[null_mask, param] = placeholder
                    logger.debug(
                        f"Filled {n_filled} None values in {param} "
                        f"with '{placeholder}' for {scenario}"
                    )

    return df
