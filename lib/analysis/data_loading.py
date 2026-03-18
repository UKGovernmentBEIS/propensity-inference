"""Data loading and validation for propensity analysis.

This module handles finding eval files, loading data via HiBayES,
and validating the data structure before analysis.
"""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pandas as pd
from hibayes.analysis import AnalysisConfig, load_data
from hibayes.ui import ModellingDisplay

from lib.analysis.model_capabilities import (
    assign_capability_quartile,
    get_model_rank,
)
from lib.analysis.types import DataValidationResult
from lib.compat.hibayes_patch import apply_hibayes_logsample_patch

logger = logging.getLogger(__name__)

# Patch hibayes LogSample for compatibility with inspect_ai >= 0.3.197
apply_hibayes_logsample_patch()

BundlingMode = Literal["none", "all", "quartile"]


class DataValidationError(Exception):
    """Raised when data validation fails."""

    def __init__(self, message: str, result: DataValidationResult):
        super().__init__(message)
        self.result = result


def find_eval_files(
    paths: Sequence[Path | str],
    *,
    model_filter: str | None = None,
    scenario_filter: str | None = None,
    variation_filter: str | None = None,
) -> list[str]:
    """Find all .eval files in the given paths (local or S3).

    Args:
        paths: List of paths to files or directories. Can be local paths or
            S3 paths (s3://bucket/prefix or just "s3" to use default bucket).
        model_filter: If provided, only include logs for this model.
            Must be the full API name (e.g., "openrouter/google/gemini-2.5-pro").
        scenario_filter: If provided, only include logs matching this scenario.
        variation_filter: If provided, only include logs matching this variation.

    Returns:
        List of paths to .eval files (local paths or S3 URIs).

    Raises:
        FileNotFoundError: If no eval files are found.
    """
    eval_files: list[str] = []

    for path in paths:
        path_str = str(path)

        # Check if this is an S3 path
        if path_str.startswith("s3://") or path_str == "s3":
            s3_files = _find_s3_eval_files(
                path_str,
                model_filter=model_filter,
                scenario_filter=scenario_filter,
                variation_filter=variation_filter,
            )
            eval_files.extend(s3_files)
        else:
            # Local path
            local_path = Path(path)
            if not local_path.exists():
                logger.warning(f"Path does not exist: {local_path}")
                continue

            if local_path.is_file():
                if local_path.suffix == ".eval":
                    eval_files.append(str(local_path))
                else:
                    logger.warning(f"Not an .eval file: {local_path}")
            elif local_path.is_dir():
                found = list(local_path.rglob("*.eval"))
                if not found:
                    logger.warning(f"No .eval files found in: {local_path}")
                eval_files.extend(str(f) for f in found)

    if not eval_files:
        raise FileNotFoundError("No .eval files found in provided paths")

    return eval_files


def _find_s3_eval_files(
    s3_path: str,
    *,
    model_filter: str | None = None,
    scenario_filter: str | None = None,
    variation_filter: str | None = None,
) -> list[str]:
    """Find .eval files in S3 using structured storage.

    Uses the high-level list_evals() API which handles:
    - Auto-fetching bucket from S3_BUCKET env var
    - Auto-fetching min_version from version tracking
    - Excluding entropy files by default

    Args:
        s3_path: S3 path or "s3" to use default bucket with structured storage.
        model_filter: If provided, only include logs for this model.
            Must be the full API name (e.g., "openrouter/google/gemini-2.5-pro").
        scenario_filter: Required. Scenario name for structured query.
        variation_filter: Required. Variation name for structured query.

    Returns:
        List of S3 URIs to .eval files.
    """
    from lib.eval_storage import get_bucket, list_evals

    # Validate required filters
    if not scenario_filter:
        raise ValueError(
            "scenario_filter is required when querying S3. "
            "Use --scenario-filter to specify which scenario to load."
        )
    if not variation_filter:
        raise ValueError(
            "variation_filter is required when querying S3. "
            "Use --variation-filter to specify which variation to load."
        )

    # Use high-level API (handles bucket, min_version, entropy filtering)
    bucket = get_bucket()
    paths = list_evals(
        scenario=scenario_filter,
        variation=variation_filter,
        model=model_filter,
    )

    logger.info(f"Found {len(paths)} eval files in structured storage")
    return [p.s3_uri(bucket) for p in paths]


def validate_data(
    df: pd.DataFrame,
    required_params: list[str],
    *,
    min_samples: int = 50,
) -> DataValidationResult:
    """Validate data structure before analysis.

    Performs upfront validation to catch format issues before expensive
    model fitting.

    Checks:
    1. Required columns exist ('score', 'model' or 'model_raw')
    2. All required parameters are present
    3. Score values are valid (0/1 or convertible)
    4. Sufficient samples exist

    Args:
        df: DataFrame to validate.
        required_params: List of parameter names that must be present.
        min_samples: Minimum number of samples required.

    Returns:
        DataValidationResult with validation details.
    """
    warnings: list[str] = []
    missing_columns: list[str] = []
    missing_parameters: list[str] = []

    # Check for required columns
    required_columns = ["score"]
    for col in required_columns:
        if col not in df.columns:
            missing_columns.append(col)

    # Check for model column (either 'model' or 'model_raw')
    if "model_raw" not in df.columns and "model" not in df.columns:
        missing_columns.append("model or model_raw")

    # Check for required parameters
    for param in required_params:
        if param not in df.columns:
            missing_parameters.append(param)

    # Count NaN scores
    n_nan_scores = 0
    if "score" in df.columns:
        n_nan_scores = int(df["score"].isna().sum())
        if n_nan_scores > 0:
            warnings.append(
                f"{n_nan_scores} samples have NaN scores and will be dropped"
            )

    # Get LLMs found
    llm_col = "model_raw" if "model_raw" in df.columns else "model"
    llms_found = []
    if llm_col in df.columns:
        llms_found = df[llm_col].unique().tolist()

    # Check sample count
    n_samples = len(df)
    if n_samples < min_samples:
        warnings.append(f"Only {n_samples} samples found (minimum: {min_samples})")

    # Check score values.
    # Scores may be stored as strings ("0", "1") or numbers (0, 1, 0.0, 1.0)
    # depending on how the eval log was written. We accept all these formats
    # and convert to float during analysis.
    if "score" in df.columns:
        valid_scores = df["score"].dropna()
        unique_scores = set(valid_scores.unique())
        expected_scores = {0, 1, 0.0, 1.0, "0", "1"}
        unexpected = unique_scores - expected_scores
        if unexpected:
            warnings.append(f"Unexpected score values found: {unexpected}")

    # Determine if valid
    is_valid = len(missing_columns) == 0 and len(missing_parameters) == 0

    return DataValidationResult(
        is_valid=is_valid,
        n_samples=n_samples,
        n_nan_scores=n_nan_scores,
        llms_found=llms_found,
        missing_columns=missing_columns,
        missing_parameters=missing_parameters,
        warnings=warnings,
    )


def load_data_from_eval_files(
    eval_files: list[str],
    analysis_config: AnalysisConfig,
    display: ModellingDisplay | None = None,
) -> pd.DataFrame:
    """Load data from eval files using HiBayES.

    Args:
        eval_files: List of paths to .eval files (local or S3).
        analysis_config: HiBayES analysis configuration.
        display: Optional HiBayES display for progress.

    Returns:
        DataFrame with loaded data.
    """
    if display is None:
        display = ModellingDisplay()

    # Configure HiBayES to load the files
    analysis_config.data_loader.files_to_process = eval_files

    # Load via HiBayES
    initial_state = load_data(analysis_config.data_loader, display)
    return initial_state.data


def load_and_validate_data(
    eval_files: list[str],
    analysis_config: AnalysisConfig,
    required_params: list[str],
    *,
    display: ModellingDisplay | None = None,
    min_samples: int = 50,
) -> tuple[pd.DataFrame, DataValidationResult]:
    """Load data via HiBayES and validate upfront.

    This is the main entry point for data loading. It combines loading
    and validation, raising an error for critical issues.

    Args:
        eval_files: List of paths to .eval files.
        analysis_config: HiBayES analysis configuration.
        required_params: List of parameter names that must be present.
        display: Optional HiBayES display for progress.
        min_samples: Minimum number of samples required.

    Returns:
        Tuple of (validated DataFrame, validation result).

    Raises:
        DataValidationError: If validation fails critically.
    """
    # Load data
    df = load_data_from_eval_files(eval_files, analysis_config, display)
    logger.info(f"Loaded {len(df)} samples from {len(eval_files)} eval files")

    # Validate
    result = validate_data(df, required_params, min_samples=min_samples)

    # Log warnings
    for warning in result.warnings:
        logger.warning(warning)

    # Raise on critical errors
    if not result.is_valid:
        errors = []
        if result.missing_columns:
            errors.append(f"Missing columns: {result.missing_columns}")
        if result.missing_parameters:
            errors.append(f"Missing parameters: {result.missing_parameters}")

        error_msg = "Data validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise DataValidationError(error_msg, result)

    return df, result


def prepare_data_for_analysis(
    df: pd.DataFrame,
    *,
    bundling: BundlingMode = "none",
    llm_filter: str | None = None,
) -> pd.DataFrame:
    """Prepare data for analysis by handling NaN scores and applying bundling.

    Args:
        df: Input DataFrame.
        bundling: How to bundle models:
            - "none": Keep all LLMs separate (default)
            - "all": Combine all LLMs into one group
            - "quartile": Group by capability quartile (q1, q2, q3, q4)
        llm_filter: If provided, filter to LLMs matching this substring.

    Returns:
        Prepared DataFrame.
    """
    # Make a copy to avoid modifying original
    df = df.copy()

    # Drop NaN scores
    n_nan = df["score"].isna().sum()
    if n_nan > 0:
        logger.warning(f"Dropping {n_nan} samples with NaN scores")
        df = df.dropna(subset=["score"])

    # Determine LLM column.
    # HiBayES base_extractor creates two columns:
    # - "model_raw": exact model name from eval log (e.g., "anthropic/claude-3-5-haiku-20241022")
    # - "model": with provider prefix stripped (e.g., "claude-3-5-haiku-20241022")
    # We prefer "model_raw" to preserve the full identifier including provider.
    llm_col = "model_raw" if "model_raw" in df.columns else "model"

    # Apply LLM filter first (before bundling)
    if llm_filter:
        original_count = len(df)
        mask = df[llm_col].str.contains(llm_filter, case=False)
        df = df.loc[mask]
        logger.info(
            f"Filtered to {len(df)} samples matching '{llm_filter}' (from {original_count})"
        )

    # Apply bundling
    if bundling == "all":
        original_llms = df[llm_col].unique().tolist()
        logger.info(f"Bundling {len(original_llms)} models into 'all_models_combined'")
        df[llm_col] = "all_models_combined"

    elif bundling == "quartile":
        original_llms = df[llm_col].unique().tolist()
        logger.info(f"Bundling {len(original_llms)} models into capability quartiles")

        # Log capability assignments
        for model in original_llms:
            rank = get_model_rank(model)
            quartile = assign_capability_quartile(model, original_llms)
            logger.info(f"  {model}: rank={rank} -> {quartile}")

        # Apply quartile assignment
        df[llm_col] = df[llm_col].apply(
            lambda m: assign_capability_quartile(m, original_llms)
        )

        # Log final distribution
        quartile_counts = df[llm_col].value_counts().sort_index()
        logger.info(f"Quartile distribution: {quartile_counts.to_dict()}")

    elif bundling == "none":
        logger.info(
            f"No bundling: {len(df[llm_col].unique())} models will be analyzed separately"
        )

    else:
        raise ValueError(f"Invalid bundling mode: {bundling}")

    return df
