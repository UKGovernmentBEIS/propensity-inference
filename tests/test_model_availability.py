"""Test model availability across all models in model_configs.py.

This test validates that all models defined in the config are accessible
and can respond to basic prompts. Tests all models in parallel using eval_set.
Marked "slow" - requires opt-in via `make test-slow`.
"""

from typing import Any

import pytest
from frozendict import frozendict
from inspect_ai import Task, eval_set, task
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import ChatMessageUser
from inspect_ai.scorer import Score, Target, scorer
from inspect_ai.solver import generate

from lib.model_configs import MODEL_CONFIGS
from lib.runner.utilities import normalize_model_weights


def _load_and_normalize_model_config() -> tuple[frozendict[str, Any], ...]:
    """Load and normalize model configs with softmax.

    Returns:
        Tuple of frozen model dicts with normalized weights that sum to 1.0
    """
    return normalize_model_weights(MODEL_CONFIGS)


@scorer(metrics=[])
def hello_world_scorer():
    """Scorer that checks if 'hello world' appears in the response."""

    async def score(state, target: Target) -> Score:
        """Check if response contains 'hello world'."""
        if not state.output or not state.output.completion:
            return Score(
                value="C",
                answer="",
                explanation="No response from model",
            )

        response = state.output.completion.lower()

        if "hello world" in response:
            return Score(
                value="C",
                answer=response,
                explanation="Response contains 'hello world'",
            )
        else:
            return Score(
                value="I",
                answer=response,
                explanation=f"Response does not contain 'hello world': {response[:100]}",
            )

    return score


@task
def _create_hello_world_task() -> Task:
    """Create a simple task that asks the model to say 'hello world'."""
    dataset = [
        Sample(
            input=[ChatMessageUser(content="Please respond with exactly: hello world")],
            metadata={"test_type": "model_availability"},
        )
    ]

    return Task(
        name="hello_world_test",
        dataset=dataset,
        solver=[
            generate(),
        ],
        scorer=hello_world_scorer(),
    )


def _test_models_one_call(tmp_path, models):
    """Test a set of models with a single eval_set call.

    Args:
        tmp_path: Temporary directory for logs
        models: List of model config dicts with 'name' field

    Raises:
        AssertionError: If any models fail
    """
    print(f"\nTesting {len(models)} models in parallel using eval_set...")

    success, logs = eval_set(
        [_create_hello_world_task()],
        log_dir=str(tmp_path),
        display="plain",  # Show progress updates
        model=[model["name"] for model in models],
        fail_on_error=False,  # Continue even if some models fail
        retry_attempts=0,
        time_limit=30,  # 30 second timeout per model
    )

    # Collect results
    successful_models = []
    failed_models = []

    for log in logs:
        model_name = log.eval.model

        # Read the full log from disk to check for sample-level errors
        try:
            full_log = read_eval_log(log.location)

            # Check if there's a log-level error
            if log.status != "success":
                error_msg = log.error.message if log.error else "Unknown error"
                failed_models.append((model_name, log.status, error_msg))
                continue

            # Check for sample-level errors
            sample_error = None
            if full_log.samples and len(full_log.samples) > 0:
                sample = full_log.samples[0]
                if sample.error:
                    sample_error = sample.error.message

            if sample_error:
                # Sample had an error (e.g., 404, auth error, etc.)
                print(f"  Error: {sample_error[:200]}")
                failed_models.append((model_name, "api_error", sample_error))
            else:
                # Model succeeded
                successful_models.append(model_name)

        except Exception as e:
            # Error reading the log itself
            error_msg = f"Failed to read log: {str(e)}"
            failed_models.append((model_name, "log_error", error_msg))

    # Report results
    print(f"\n{'=' * 70}")
    print(f"Results: {len(successful_models)}/{len(models)} models succeeded")
    print(f"{'=' * 70}")

    if successful_models:
        print(f"\n✓ Successful models ({len(successful_models)}):")
        for model in successful_models:
            print(f"  - {model}")

    if failed_models:
        print(f"\n✗ Failed models ({len(failed_models)}):")
        for model, status, error in failed_models:
            print(f"  - {model}")
            print(f"    Status: {status}")
            print(f"    Error: {error[:100]}")

    # Assert all models succeeded
    assert len(failed_models) == 0, (
        f"{len(failed_models)} model(s) failed: "
        f"{', '.join(m for m, _, _ in failed_models)}"
    )

    assert len(models) == len(successful_models)
    assert success


@pytest.mark.skip_ci
def test_all_models_available(tmp_path):
    """Test that all models in config are available.

    Creates one task per model and tests all in parallel using eval_set.
    Fails if any model is unavailable.
    """
    models = _load_and_normalize_model_config()
    _test_models_one_call(tmp_path, models)


@pytest.mark.skip_ci
def test_deprecated_models_fail(tmp_path):
    """Test that known deprecated models correctly fail with API errors.

    This is the inverse of test_all_models_available - we expect these models
    to fail with 404 or similar errors.
    """
    # Known deprecated/unavailable models
    deprecated_models = [
        frozendict({"name": "anthropic/claude-3-5-sonnet-20240620"}),
    ]

    print("\nTesting that deprecated models fail as expected...")

    # This should raise an AssertionError because the models should fail
    with pytest.raises(AssertionError, match="model.*failed"):
        _test_models_one_call(tmp_path, deprecated_models)
