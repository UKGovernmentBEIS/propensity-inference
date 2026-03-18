"""Custom hibayes extractors and processors for propensity scenario evaluation logs.

This module provides extractors that pull scenario-specific parameters from
the metadata stored in propensity evaluation logs, and custom processors.
"""

from typing import Any

import jax.numpy as jnp
from hibayes.load import Extractor, extractor
from hibayes.process._process import DataProcessor, process
from inspect_ai.log import EvalLog, EvalSample

from lib.compat.hibayes_patch import apply_hibayes_logsample_patch

# Patch hibayes LogSample for compatibility with inspect_ai >= 0.3.197
apply_hibayes_logsample_patch()



@extractor
def propensity_extractor() -> Extractor:
    """Extract propensity scenario parameters from sample metadata.

    Extracts ALL task_params stored by the propensity scenario framework,
    making this extractor work with any scenario. Also extracts scenario
    identifiers (scenario_name, suite_name, version).

    Returns:
        An Extractor function that extracts propensity metadata.
    """

    def extract(sample: EvalSample, eval_log: EvalLog) -> dict[str, Any]:
        """Extract propensity metadata from a sample."""
        result: dict[str, Any] = {}

        metadata = sample.metadata or {}

        # Extract scenario identifiers
        result["scenario_name"] = metadata.get("scenario_name", "unknown")
        result["suite_name"] = metadata.get("suite_name", "unknown")
        result["version"] = metadata.get("version", "unknown")

        # Also extract top-level scenario identifier if present
        if "scenario" in metadata:
            result["scenario"] = metadata["scenario"]

        # Extract ALL task_params dynamically - works with any scenario
        task_params = metadata.get("task_params", {})
        for key, value in task_params.items():
            # Skip time tuples and other complex types that don't work well as features
            if isinstance(value, (list, tuple)):
                continue
            # Skip very long strings (likely template content)
            if isinstance(value, str) and len(value) > 100:
                continue
            result[key] = value

        return result

    return extract


@extractor
def propensity_score_extractor() -> Extractor:
    """Extract and normalize propensity scores as misalignment indicator.

    Propensity scenarios use scores where:
    - 0 = aligned (did not exhibit misaligned behavior)
    - 1 = misaligned (exhibited misaligned behavior)

    Returns:
        An Extractor function that extracts normalized misalignment scores.
    """

    def extract(sample: EvalSample, eval_log: EvalLog) -> dict[str, Any]:
        """Extract misalignment score from a sample."""
        result: dict[str, Any] = {}

        if not sample.scores:
            raise ValueError(
                "Sample has no scores. Expected at least one score for misalignment extraction."
            )

        # Get the first (and typically only) score
        score_obj = next(iter(sample.scores.values()))
        score_value = score_obj.value

        # Normalize to float
        # NOTE: We fail loudly on unexpected score values to catch data issues early
        if score_value == "I" or score_value == "INCORRECT":
            result["misaligned"] = 0.0
        elif score_value == "C" or score_value == "CORRECT":
            result["misaligned"] = 1.0
        elif isinstance(score_value, (int, float)):
            result["misaligned"] = float(score_value)
        elif isinstance(score_value, str):
            try:
                result["misaligned"] = float(score_value)
            except ValueError:
                raise ValueError(
                    f"Cannot parse score value '{score_value}' as float. "
                    f"Expected numeric string, 'C', 'CORRECT', 'I', or 'INCORRECT'."
                )
        else:
            raise TypeError(
                f"Unexpected score type {type(score_value).__name__} with value {score_value!r}. "
                f"Expected int, float, or str."
            )

        # Also store the raw score name for reference
        result["scorer_name"] = next(iter(sample.scores.keys()))

        return result

    return extract


@extractor
def n_total_extractor() -> Extractor:
    """Add n_total=1 for each sample for Bernoulli trials.

    This is needed for the linear_group_binomial model when working with
    individual trials rather than aggregated binomial data.

    Returns:
        An Extractor function that adds n_total=1.
    """

    def extract(sample: EvalSample, eval_log: EvalLog) -> dict[str, Any]:
        """Add n_total=1 for Bernoulli trial."""
        return {"n_total": 1}

    return extract


@process
def add_n_total_feature() -> DataProcessor:
    """Add n_total feature to the state for Bernoulli trials.

    This processor adds n_total to the features dict, which is required by
    linear_group_binomial. If the processed_data already contains an 'n_total'
    column (e.g., for weighted samples), those values are used. Otherwise,
    n_total=1 is used for standard Bernoulli trials.
    """

    def process_fn(state: Any, display: Any = None) -> Any:
        n_samples = len(state.processed_data)

        # Check if n_total already exists in processed_data (for weighted samples)
        if "n_total" in state.processed_data.columns:
            n_total_array = jnp.array(state.processed_data["n_total"].values)
            source = "from data (weighted)"
        else:
            n_total_array = jnp.ones(n_samples, dtype=jnp.int32)
            source = "default (unweighted)"

        if state.features is None:
            state.features = {}
        state.features["n_total"] = n_total_array

        if display:
            display.logger.info(
                f"Added n_total feature {source} with shape {n_total_array.shape}"
            )

        return state

    return process_fn


@extractor
def full_task_params_extractor() -> Extractor:
    """Extract ALL task_params from sample metadata.

    This extractor is useful when you need access to all parameters,
    including derived ones like timestamps. Use with caution as this
    may create many columns in the resulting DataFrame.

    Returns:
        An Extractor function that extracts all task_params.
    """

    def extract(sample: EvalSample, eval_log: EvalLog) -> dict[str, Any]:
        """Extract all task_params from a sample."""
        metadata = sample.metadata or {}
        task_params = metadata.get("task_params", {})

        # Convert any non-serializable values to strings
        result = {}
        for key, value in task_params.items():
            if isinstance(value, (list, tuple)):
                # Convert time tuples to string representation
                result[key] = str(value)
            else:
                result[key] = value

        return result

    return extract
