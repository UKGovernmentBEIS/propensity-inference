"""Generic command-line interface for running scenario evaluations.

This CLI provides a unified entry point for running any scenario in the scenarios/
package. It supports running single or multiple scenarios with reproducible sampling
and parallel execution via eval_set.

Model sampling uses variance-reduced allocation across all models defined in the
model config. By default, uses MODEL_CONFIGS from lib/model_configs.py. Override
with --model-config to specify a custom JSON config file.

Usage:
    # Run sample from single scenario (uses default model config)
    uv run run_scenarios sample --scenario gpu_decision_email_assistant --num_samples 100 --seed 42

    # Run sample with custom model config
    uv run run_scenarios sample --scenario sem_v2 --num_samples 100 --model-config my_models.json --seed 42

    # Run sample from multiple scenarios with seed
    uv run run_scenarios sample --scenarios "gpu_decision_email_assistant hospital_hvac" --num_samples 100 --seed 42
"""

import hashlib
import json
import logging
import os
import random
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import fire
import pandas as pd
from inspect_ai import Task, eval_set, task_with
from inspect_ai.log import EvalLog
from inspect_ai.scorer import Scorer
from inspect_ai.util import DisplayType
from termcolor import colored

from lib import ScenarioDefinition
from lib.eval_storage import update_evals_listing
from lib.experiment_tracking import (
    _get_github_webview_url,
    _get_latest_commit_message,
    auto_push_working_changes,
    show_progress_bar_for_eval_set,
    start_background_s3_uploader,
)
from lib.model_registry import get_model_by_api_name
from lib.parameter_space import ParameterSpace
from lib.qa.verifier_agent import VerifierAgentType
from lib.qa.verifier_agent import verifier_agent as verifier_agent_solver
from lib.runner.utilities import (
    load_model_configs_from_json,
    setup_multi_model_mode,
)
from lib.scorers.scorer_registry import SCORER_REGISTRY
from lib.token_estimates import TOKEN_ESTIMATES
from lib.version_tracking import get_current_version
from scenarios.scenario_registry import SCENARIO_FACTORIES

logger = logging.getLogger(__name__)

# Cost estimation configuration
COST_ESTIMATION_SAMPLE_SIZE = 30


def _update_listing_on_cleanup(bucket: str | None, no_upload: bool) -> None:
    """Update listing.json during cleanup.

    Called in finally blocks to ensure listing.json is updated even if
    the evaluation is interrupted.

    Args:
        bucket: S3 bucket name, or None if not configured
        no_upload: If True, skip the listing update
    """
    if no_upload or not bucket:
        return

    print("\n\nUpdating listing.json...")
    try:
        entries_added = update_evals_listing(bucket)
        if entries_added > 0:
            print(f"✓ Added {entries_added} entries to listing.json")
        else:
            print("✓ Listing.json already up to date")
    except Exception as e:
        print(f"⚠️  Failed to update listing.json: {e}")


def _estimate_sample_cost(model_api_name: str, scenario_name: str) -> float | None:
    """Estimate cost in USD for one sample.

    Args:
        model_api_name: Full API name (e.g., "anthropic/claude-3-5-haiku-20241022")
        scenario_name: Scenario name for token estimate lookup

    Returns:
        Estimated cost per sample in USD, or None if pricing unavailable
    """
    model = get_model_by_api_name(model_api_name)
    if model is None or model.input_cost is None or model.output_cost is None:
        return None

    input_tokens, output_tokens = TOKEN_ESTIMATES.get(scenario_name, (50_000, 10_000))
    input_cost = (input_tokens / 1_000_000) * model.input_cost
    output_cost = (output_tokens / 1_000_000) * model.output_cost
    return input_cost + output_cost


def _print_cost_summary(
    existing_counts: dict[str, dict[str, int]],
    targets: dict[str, dict[str, int]],
) -> None:
    """Print cost estimation summary for sample_to_target.

    Args:
        existing_counts: Dict of model -> scenario/variation -> existing count
        targets: Dict of model -> scenario/variation -> target count
    """
    total_spent = 0.0
    total_remaining = 0.0
    missing_pricing = []
    # Track per-model costs
    model_costs: dict[str, dict[str, float]] = {}

    for model, model_targets in targets.items():
        model_existing = existing_counts.get(model, {})
        model_spent = 0.0
        model_remaining = 0.0

        for scenario_variation, target_count in model_targets.items():
            scenario_name = scenario_variation.split("/")[0]
            existing = model_existing.get(scenario_variation, 0)
            delta = max(0, target_count - existing)

            cost_per_sample = _estimate_sample_cost(model, scenario_name)
            if cost_per_sample is None:
                missing_pricing.append(model)
                continue

            model_spent += existing * cost_per_sample
            model_remaining += delta * cost_per_sample

        total_spent += model_spent
        total_remaining += model_remaining
        model_costs[model] = {"spent": model_spent, "remaining": model_remaining}

    print(f"\n{'=' * 60}")
    print("Cost Estimation (based on token estimates)")
    print(f"{'=' * 60}")
    print(f"  Estimated spent so far:  ${total_spent:,.2f}")
    print(f"  Estimated remaining:     ${total_remaining:,.2f}")
    print(f"  Estimated total:         ${total_spent + total_remaining:,.2f}")
    if missing_pricing:
        unique_missing = sorted(set(missing_pricing))
        print(f"  ⚠️  Missing pricing for: {', '.join(unique_missing)}")

    # Print per-model breakdown, sorted by remaining cost (most expensive last)
    print(f"\n  {'Model':<45} {'Spent':>10} {'Remaining':>10}")
    print(f"  {'-' * 45} {'-' * 10} {'-' * 10}")
    sorted_models = sorted(
        model_costs.keys(), key=lambda m: model_costs[m]["remaining"]
    )
    for model in sorted_models:
        costs = model_costs[model]
        short_name = model.split("/")[-1][:44]
        print(f"  {short_name:<45} ${costs['spent']:>8.2f} ${costs['remaining']:>8.2f}")
    print(f"{'=' * 60}\n")



def _capture_run_context() -> dict[str, Any]:
    """Capture run context including git information and CLI command.

    Returns:
        Dict with:
            - git_hash: Current git commit hash (or "unknown")
            - git_dirty: Boolean indicating uncommitted changes
            - git_branch: Current git branch name (or "unknown")
            - cli_command: Full CLI command string
            - timestamp: ISO timestamp when run started
    """
    context: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "cli_command": " ".join(sys.argv),
        "git_hash": "unknown",
        "git_dirty": False,
        "git_branch": "unknown",
    }

    repo_root = Path(__file__).parent.parent

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        context["git_hash"] = result.stdout.strip()

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        context["git_dirty"] = bool(result.stdout.strip())

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        context["git_branch"] = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Not a git repo or git not available — use defaults

    return context


def _capture_cli_args(local_vars: dict[str, Any]) -> dict[str, Any]:
    """Capture CLI arguments from function locals.

    Args:
        local_vars: locals() dict from calling function

    Returns:
        Dict of CLI argument names and values
    """
    # Filter out non-argument variables (self, internal vars, run_context to avoid circular refs)
    # model_assignments is O(n) and would cause O(n^2) if copied to each task's metadata (where n = num_samples)
    return {
        k: v
        for k, v in local_vars.items()
        if not k.startswith("_")
        and k
        not in (
            "self",
            "task_generator",
            "run_context",
            "cli_args",
            "model_assignments",
        )
    }


def _enrich_task_metadata_inplace(
    task: Task,
    run_context: dict[str, Any],
    params: dict[str, Any],
    scenario_name: str,
    variation_name: str,
    suite_name: str,
    space: ParameterSpace,
    user_name: str,
    sample_index: int,
) -> Task:
    """Enrich Task metadata with run configuration and parameters.

    Also appends a unique hash suffix to the task name to ensure uniqueness
    when multiple tasks are generated from the same scenario.
    Operates in place and returns the modified task.

    Args:
        task: Inspect Task object to enrich
        run_context: Run context dict from _capture_run_context()
        params: Full parameter dict used to generate this task
        scenario_name: Name of the scenario
        variation_name: Name of the variation (e.g., "alert", "classification")
        suite_name: Name of the suite within the variation (e.g., "punishment", "default")
        space: The full parameter space used to generate the task.
        user_name: Name of the user running the evaluation
        sample_index: Unique index for this sample (ensures uniqueness even with duplicate params)

    Returns:
        The modified Task object
    """
    # Generate unique hash suffix from params AND sample_index to ensure task name uniqueness
    # Include sample_index because Big Sampling can select the same params multiple times (c.f. Birthday paradox)
    # Use sha3_256 for good distribution and take first 16 hex characters
    hash_input = json.dumps(
        {"params": params, "idx": sample_index}, sort_keys=True, default=str
    )
    hash_digest = hashlib.sha3_256(hash_input.encode()).hexdigest()
    hash_suffix = hash_digest[:16]

    # Prepare additional metadata
    additional_metadata = {
        "run_config": run_context,
        "task_params": params,
        "scenario_name": scenario_name,
        "variation_name": variation_name,
        "suite_name": suite_name,
        "version": get_current_version(),
        "full_space": space.to_dict(),
        "user_name": user_name,
    }

    # Enrich each sample's metadata
    for sample in task.dataset:
        if sample.metadata is None:
            sample.metadata = {}
        sample.metadata.update(additional_metadata)

    # Enrich the task metadata too
    if not task.metadata:
        task.metadata = {}
    for k in additional_metadata.keys():
        # double check that we aren't overwriting any keys
        assert k not in task.metadata
    task.metadata.update(additional_metadata)

    return task_with(
        task=task,
        dataset=task.dataset,
        name=f"{task.name}_{hash_suffix}",  # Append hash suffix to name
    )


def _create_timestamped_log_dir(base_path: str = "./logs") -> Path:
    """Create and return a timestamped log directory for this evaluation run.

    Args:
        base_path: Base directory for logs (default: "./logs")

    Returns:
        Path to the timestamped log directory (e.g., "./logs/2025-10-22T10-30-45")
    """
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_dir = Path(base_path) / timestamp
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _save_run_config(log_dir: Path, config: dict[str, Any]) -> None:
    """Save run configuration to JSON file in log directory.

    Args:
        log_dir: Directory to save the config file
        config: Dictionary containing all CLI arguments and configuration
    """
    config_path = log_dir / "run_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, default=str)


def _load_scenario(scenario_name: str) -> ScenarioDefinition:
    """Load a scenario using the central registry.

    Args:
        scenario_name: Name of the scenario (e.g., "gpu_decision_email_assistant")

    Returns:
        ScenarioDefinition object

    Raises:
        ValueError: If scenario name is not in registry
    """
    if scenario_name not in SCENARIO_FACTORIES:
        available = sorted(SCENARIO_FACTORIES.keys())
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. Available scenarios: {', '.join(available)}"
        )

    return SCENARIO_FACTORIES[scenario_name]()


def _preload_scenarios(
    scenario_names: list[str],
) -> tuple[
    list[tuple[str, ScenarioDefinition]],
    list[tuple[str, Exception]],
]:
    """Preload and validate all scenarios before running evaluation.

    Args:
        scenario_names: List of scenario names to load

    Returns:
        Tuple of (loaded_scenarios, errors)
        - loaded_scenarios: List of (name, scenario_def) tuples
        - errors: List of (name, exception) tuples for scenarios that failed to load
    """
    loaded_scenarios = []
    errors = []

    for scenario_name in scenario_names:
        try:
            scenario_def = _load_scenario(scenario_name)
            loaded_scenarios.append((scenario_name, scenario_def))
        except Exception as e:
            errors.append((scenario_name, e))

    return loaded_scenarios, errors


def _get_suites_from_scenario(
    scenario_def: ScenarioDefinition,
    variation_name: str | None = None,
) -> dict[str, Any] | None:
    """Get suites from a scenario's variations.

    Args:
        scenario_def: ScenarioDefinition with variations
        variation_name: If provided, get suites from this specific variation

    Returns:
        Dict of suite_name -> space_func, or None if not found

    Raises:
        ValueError: If scenario has no variations defined
    """
    if scenario_def.variations is None:
        raise ValueError(
            "Scenario must define variations (legacy SUITES not supported)"
        )

    if variation_name is not None:
        # Get suites from specific variation
        variation = scenario_def.variations.get(variation_name)
        if variation is None:
            return None
        # Return with variation prefix for consistent naming
        return {
            f"{variation_name}/{suite_name}": suite_func
            for suite_name, suite_func in variation.suites.items()
        }
    else:
        # No variation specified - flatten all suites across variations
        all_suites = {}
        for var_name, variation in scenario_def.variations.items():
            for suite_name, suite_func in variation.suites.items():
                all_suites[f"{var_name}/{suite_name}"] = suite_func
        return all_suites


def _get_suite_weights_from_scenario(
    scenario_def: ScenarioDefinition,
    variation_name: str | None = None,
) -> dict[str, float]:
    """Get suite weights from a scenario's variations.

    Keys are always prefixed with variation name to match _get_suites_from_scenario.

    Args:
        scenario_def: ScenarioDefinition with variations
        variation_name: If provided, get weights from this specific variation

    Returns:
        Dict of "variation_name/suite_name" -> weight

    Raises:
        ValueError: If scenario has no variations, or if variation not found
    """
    if scenario_def.variations is None:
        raise ValueError(
            "Scenario must define variations (legacy SUITES not supported)"
        )

    if variation_name is not None:
        # Get weights from specific variation
        variation = scenario_def.variations.get(variation_name)
        if variation is None:
            raise ValueError(
                f"Variation '{variation_name}' not found. "
                f"Available: {list(scenario_def.variations.keys())}"
            )
        # Return with variation prefix for consistent naming (matches _get_suites_from_scenario)
        return {
            f"{variation_name}/{suite_name}": weight
            for suite_name, weight in variation.suite_weights.items()
        }
    else:
        # Flatten all weights across variations
        all_weights = {}
        for var_name, variation in scenario_def.variations.items():
            for suite_name, weight in variation.suite_weights.items():
                all_weights[f"{var_name}/{suite_name}"] = weight
        return all_weights


def _generate_sample_tasks(
    scenario_name: str,
    seed: int,
    scenario_def: ScenarioDefinition,
    num_samples: int,
    run_context: dict[str, Any],
    variation_name: str | None = None,
) -> list[Task]:
    """Generate sample tasks for a scenario using weighted sampling.

    Distributes samples across suites according to suite_weights if defined,
    otherwise distributes evenly. Within each suite, samples are drawn using
    weighted sampling to respect parameter weights.

    Args:
        scenario_name: Name of the scenario
        seed: Random seed for reproducibility
        scenario_def: ScenarioDefinition with params_to_task and variations
        num_samples: Number of random samples to generate (distributed across all suites)
        run_context: Run context dict to add to task metadata (required for traceability)
        variation_name: If provided, only sample from this variation

    Returns:
        List of Task objects

    Raises:
        ValueError: If run_context is not provided
    """
    if run_context is None:
        raise ValueError("run_context is required for task metadata traceability")
    suites = _get_suites_from_scenario(scenario_def, variation_name)
    if not suites:
        if variation_name:
            print(
                f"  Warning: Variation '{variation_name}' not found in '{scenario_name}'. Skipping."
            )
        else:
            print(f"  Warning: Scenario '{scenario_name}' has no suites. Skipping.")
        return []

    # Get suite weights (always present - Variation validates this at construction)
    suite_weights = _get_suite_weights_from_scenario(scenario_def, variation_name)

    # Get all suites
    suite_items = list(suites.items())

    # Create RNG for consistent random decisions
    rng = random.Random(seed)

    # Calculate samples per suite using variance-reduced allocation
    # All Variations must have suite_weights (enforced by Variation class)
    suite_names = [name for name, _ in suite_items]
    weights = []
    for name in suite_names:
        if name not in suite_weights:
            raise ValueError(
                f"Suite '{name}' has no weight defined. "
                f"Available weights: {list(suite_weights.keys())}"
            )
        weights.append(suite_weights[name])

    total_weight = sum(weights)

    # Calculate base allocation (floor) for each suite
    samples_per_suite = []
    for w in weights:
        proportion = w / total_weight
        samples_per_suite.append(int(num_samples * proportion))

    # Distribute remaining samples using fractional parts
    remaining = num_samples - sum(samples_per_suite)
    if remaining > 0:
        # Calculate fractional parts for tie-breaking
        fractional_parts = []
        for i, w in enumerate(weights):
            proportion = w / total_weight
            fractional = (num_samples * proportion) - samples_per_suite[i]
            fractional_parts.append((fractional, i))
        # Sort by fractional part descending, allocate remaining to highest
        fractional_parts.sort(reverse=True)
        for _, idx in fractional_parts[:remaining]:
            samples_per_suite[idx] += 1

    all_tasks = []

    for suite_idx, (suite_key, space_func) in enumerate(suite_items):
        # suite_key is always "variation/suite" format (e.g., "alert/punishment")
        variation_name, suite_name = suite_key.split("/", 1)

        space = space_func()

        # Get samples for this suite from pre-calculated allocation
        samples_for_this_suite = samples_per_suite[suite_idx]

        if samples_for_this_suite == 0:
            continue

        space_size = space.size()
        if space_size > 1e15:
            # Format very large numbers in scientific notation
            print(f"  {scenario_name}/{suite_key}: {space_size:.2e} combinations")
        else:
            print(f"  {scenario_name}/{suite_key}: {space_size:,} combinations")

        # Always use weighted sampling (respects parameter weights if defined)
        print(f"    Sampling {samples_for_this_suite} tasks (weighted)")

        # Generate a unique seed for this suite
        suite_seed = rng.randint(0, (1 << 64) - 1)
        iterator = space.sample_weighted(n=samples_for_this_suite, seed=suite_seed)

        for params in iterator:
            task = scenario_def.params_to_task(params)
            # Enrich task metadata with run context and parameters
            global_sample_idx = len(all_tasks)
            task = _enrich_task_metadata_inplace(
                task,
                run_context,
                params,
                scenario_name,
                variation_name,
                suite_name,
                space,
                user_name=os.environ.get("S3_USER", "unknown"),
                sample_index=global_sample_idx,
            )
            all_tasks.append(task)

    return all_tasks


def _get_available_scenarios() -> list[str]:
    """Get list of available scenario names from the registry.

    Returns:
        List of scenario names
    """
    return sorted(SCENARIO_FACTORIES.keys())


def _print_score_table(logs: list[EvalLog]) -> None:
    scores: list[dict[str, Any]] = []

    for idx, log in enumerate(logs):
        score_row = {}
        scores.append(score_row)
        score_row["eval idx"] = idx
        score_row["status"] = log.status

        # add task metadata
        assert log.eval.metadata
        score_row["scenario"] = log.eval.metadata["scenario_name"]
        score_row["suite"] = log.eval.metadata["suite_name"]

        # add all scorer results
        if log.status == "success" and log.results:
            for score in log.results.scores:
                for metric_name, metric in score.metrics.items():
                    score_row[score.name + "/" + metric_name] = metric.value

    df = pd.DataFrame.from_records(scores)
    print()
    print("=" * 5, "Score Table", "=" * 5)
    print(df.to_string(index=False, max_rows=300))


def _count_existing_samples(
    model: str,
    scenario: str,
    variation: str,
    bucket: str,
    *,
    count_failures: bool = False,
) -> int:
    """Query structured storage and count samples for a config.

    Excludes entropy estimation runs (files in /entropy/ subdirectory).

    Args:
        model: Model API name (e.g., "anthropic/claude-3-5-haiku-20241022").
        scenario: Scenario name (e.g., "agentic_misalignment_v2").
        variation: Variation name (e.g., "alert").
        bucket: S3 bucket name.
        count_failures: If True, count all samples. If False, only count successes.

    Returns:
        Count of matching eval files in structured storage.
    """
    from lib.eval_storage import count_evals

    return count_evals(
        scenario=scenario,
        variation=variation,
        model=model,
        bucket=bucket,
        status_filter=None if count_failures else "success",
        exclude_entropy=True,  # Don't count entropy estimation runs
    )


def _print_cost_estimation(logs: list[EvalLog], num_samples: int) -> None:
    """Analyze and print token usage cost estimation from sample logs.

    Args:
        logs: List of EvalLog from sample run
        num_samples: Total number of samples requested (for extrapolation)
    """
    # Analyze token usage from logs
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    successful_samples = 0

    for log in logs:
        if log.status == "success" and log.stats.model_usage:
            for usage in log.stats.model_usage.values():
                total_input_tokens += usage.input_tokens
                total_output_tokens += usage.output_tokens
                total_tokens += usage.total_tokens
            successful_samples += 1

    if successful_samples == 0:
        print("\n⚠️  Warning: No samples completed successfully. Cannot estimate cost.")
        return

    # Calculate average per task
    avg_input_tokens = total_input_tokens / successful_samples
    avg_output_tokens = total_output_tokens / successful_samples
    avg_total_tokens = total_tokens / successful_samples

    # Extrapolate to requested num_samples
    estimated_total_input = avg_input_tokens * num_samples
    estimated_total_output = avg_output_tokens * num_samples
    estimated_total = avg_total_tokens * num_samples

    # Display cost estimation results
    print(f"\n{'=' * 60}")
    print("Cost Estimation Results")
    print(f"{'=' * 60}")
    print(f"Sample size: {successful_samples} tasks (out of {len(logs)} attempted)")
    print(f"Total tasks requested: {num_samples}")
    print()
    print("Average per task:")
    print(f"  Input tokens:  {avg_input_tokens:,.0f}")
    print(f"  Output tokens: {avg_output_tokens:,.0f}")
    print(f"  Total tokens:  {avg_total_tokens:,.0f}")
    print()
    print(f"Estimated total for {num_samples} tasks:")
    print(f"  Input tokens:  {estimated_total_input:,.0f}")
    print(f"  Output tokens: {estimated_total_output:,.0f}")
    print(f"  Total tokens:  {estimated_total:,.0f}")
    print(f"{'=' * 60}")


def _run_evaluation(
    scenario_names: list[str],
    task_generator: Callable[[str, ScenarioDefinition], list[Task]],
    seed: int,
    model_assignments: list[str],
    log_dir: str,
    # eval_set parameters
    epochs: int,
    display: DisplayType | None,
    max_tasks: int | None,
    max_connections: int | None,
    max_sandboxes: int | None,
    max_subprocesses: int | None,
    fail_on_error: bool,
    retry_on_error: int,
    sandbox: str | None,
    timeout: int | None,
    max_retries: int | None,
    log_samples: bool,
    message_limit: int | None,
    token_limit: int | None,
    verifier_agent: VerifierAgentType | None = None,
    scorers: list[Scorer] | None = None,
    # Sample-specific parameters for config saving
    num_samples: int | None = None,
    no_upload: bool = False,
    run_context: dict[str, Any] | None = None,
    estimate_cost: bool = False,
) -> None:
    """Common evaluation logic for running scenario evaluations.

    Registers cleanup handlers to update listing.json on Ctrl+C.

    Args:
        scenario_names: List of scenario names to run
        task_generator: Function that generates tasks for each scenario
        seed: Random seed for reproducibility
        model_assignments: List of model names to assign to tasks (one per task)
        log_dir: Base directory for logs
        epochs: Number of epochs to run
        display: Display type - "full", "log", or "plain"
        max_tasks: Maximum number of tasks to run in parallel
        max_connections: Maximum number of concurrent connections to Model API
        max_sandboxes: Maximum number of sandboxes to run in parallel
        max_subprocesses: Maximum number of subprocesses to run in parallel
        fail_on_error: Fail on first sample error
        retry_on_error: Number of times to retry samples on errors
        sandbox: Sandbox environment type
        timeout: Request timeout in seconds
        max_retries: Maximum number of times to retry request
        log_samples: Log detailed samples and scores
        message_limit: Limit on total messages per sample
        token_limit: Limit on total tokens per sample
        verifier_agent: The name of the verifier agent to use in the evaluation
        scorers: a list of scorers to apply to all tasks
        num_samples: Number of random tasks to sample (for config saving)
        no_upload: Skip uploading logs to S3
        run_context: Pre-captured run context (if None, will capture here)
        estimate_cost: If True, sub-sample tasks and estimate token usage
    """
    # Capture run context if not provided
    if run_context is None:
        run_context = _capture_run_context()

    # Capture CLI arguments and add to run context
    cli_args = _capture_cli_args(locals())
    run_context["cli_args"] = cli_args

    print(f"{'=' * 60}")
    print("Preloading scenarios...")
    print(f"{'=' * 60}")

    # Preload and validate all scenarios
    loaded_scenarios, errors = _preload_scenarios(scenario_names)

    # Fail immediately if ANY scenario fails to load
    if errors:
        print("\n✗ Failed to load scenario(s):")
        for scenario_name, error in errors:
            print(f"  - {scenario_name}: {error}")
        raise ValueError(
            f"All requested scenarios must be valid. "
            f"Failed to load {len(errors)} scenario(s). Fix errors above and try again."
        )

    print(f"\n✓ Successfully loaded {len(loaded_scenarios)} scenario(s):")
    for scenario_name, scenario_def in loaded_scenarios:
        if scenario_def.variations is not None:
            var_count = len(scenario_def.variations)
            suite_count = sum(len(v.suites) for v in scenario_def.variations.values())
            print(
                f"  - {scenario_name} ({var_count} variation(s), {suite_count} suite(s))"
            )
        elif scenario_def.suites is not None:
            suite_names = list(scenario_def.suites.keys())
            print(f"  - {scenario_name} ({len(suite_names)} suite(s))")
        else:
            print(f"  - {scenario_name} (no suites)")

    # Create timestamped log directory
    base_log_dir = _create_timestamped_log_dir(log_dir)
    print(f"\nLogs will be saved to: {base_log_dir}")

    # Save run configuration (includes git info, CLI command, and all args)
    _save_run_config(base_log_dir, run_context)

    print(f"\n{'=' * 60}")
    print("Generating tasks...")
    print(f"{'=' * 60}")

    # Generate ALL tasks from ALL scenarios using provided generator
    all_tasks = []
    for scenario_name, scenario_def in loaded_scenarios:
        scenario_tasks = task_generator(scenario_name, scenario_def)
        all_tasks.extend(scenario_tasks)

    if not all_tasks:
        print("\nNo tasks to run. Check scenario configurations.")
        return

    print(f"\n✓ Generated {len(all_tasks)} total tasks")

    # If estimate_cost, sub-sample tasks
    if estimate_cost:
        sample_size = min(COST_ESTIMATION_SAMPLE_SIZE, len(all_tasks))
        print(f"\n{'=' * 60}")
        print(f"Cost Estimation Mode: Running {sample_size} sample tasks")
        print(f"{'=' * 60}")

        # Randomly sample tasks and their model assignments
        estimation_rng = random.Random(seed)
        sample_indices = estimation_rng.sample(range(len(all_tasks)), sample_size)
        all_tasks = [all_tasks[i] for i in sample_indices]
        model_assignments = [model_assignments[i] for i in sample_indices]

    # Apply model assignments (always present, either single model repeated or multi-model distribution)
    if len(model_assignments) != len(all_tasks):
        raise ValueError(
            f"Length of model_assignments ({len(model_assignments)}) must equal "
            f"number of tasks ({len(all_tasks)})"
        )

    print(f"  Applying model assignments to {len(all_tasks)} tasks...")
    for i, task in enumerate(all_tasks):
        assigned_model = model_assignments[i]
        # Store model assignment in task metadata
        for sample in task.dataset:
            if sample.metadata is None:
                sample.metadata = {}
            sample.metadata["assigned_model"] = assigned_model
        # Apply model to task
        all_tasks[i] = task_with(task, model=assigned_model)

    if verifier_agent:
        all_tasks = [
            task_with(
                task,
                solver=verifier_agent_solver(
                    task.solver,
                    verifier_type=verifier_agent,
                ),
            )
            for task in all_tasks
        ]

    if scorers:
        all_tasks = [
            task_with(
                task,
                scorer=(task.scorer or []) + scorers,
            )
            for task in all_tasks
        ]

    print(f"\n{'=' * 60}")
    print("Running evaluation (parallel execution via eval_set)...")
    print(f"{'=' * 60}")

    # Show progress bar (monitors log files in background thread)
    show_progress_bar_for_eval_set(str(base_log_dir), len(all_tasks))

    # Start background S3 uploader if bucket is configured
    bucket = os.environ.get("S3_BUCKET")
    if bucket and not no_upload:
        start_background_s3_uploader(str(base_log_dir), bucket)

    # Run evaluation with cleanup in finally block to handle Ctrl+C gracefully
    try:
        # Run ALL tasks in parallel using eval_set
        # Each task already has its model assigned, so we don't pass a model parameter
        success, logs = eval_set(
            all_tasks,
            log_dir=str(base_log_dir),
            epochs=epochs,
            display=display,
            max_tasks=max_tasks,
            max_connections=max_connections,
            max_sandboxes=max_sandboxes,
            max_subprocesses=max_subprocesses,
            fail_on_error=fail_on_error,
            retry_on_error=retry_on_error,
            sandbox=sandbox,
            timeout=timeout,
            max_retries=max_retries,
            log_samples=log_samples,
            message_limit=message_limit,
            token_limit=token_limit,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return
    finally:
        # Always update listing.json while resources are still alive
        _update_listing_on_cleanup(bucket, no_upload)

    # Report results
    print(f"\n{'=' * 60}")
    if success:
        print(f"✓ Evaluation complete: {len(logs)} task(s) evaluated")
    else:
        print(f"✗ Evaluation completed with errors: {len(logs)} task(s) evaluated")
    print(f"Results saved to: {base_log_dir}")
    print(f"{'=' * 60}")

    # If this was a cost estimation run, print estimation and return
    if estimate_cost and num_samples is not None:
        _print_cost_estimation(logs, num_samples)
        return

    _print_score_table(logs)

    # Display experiment tracking information
    print()
    print("=" * 10)
    print()
    print("Experiment tracking info (copy/paste this into your logbook):")

    # Only show commit description and git URL if repo is clean
    if not run_context["git_dirty"]:
        commit_message = _get_latest_commit_message()
        print("Description:", commit_message)

    print("Log dir:", colored(base_log_dir, "green"))
    print(
        "Local view:",
        colored(f"uv run inspect view start --log-dir {base_log_dir}", "cyan"),
    )

    # Only show git URL if repo is clean and has a remote
    if not run_context["git_dirty"]:
        try:
            git_url = _get_github_webview_url()
            print("GitHub URL:", colored(git_url, "green"))
        except (ValueError, Exception):
            pass  # No remote configured


class ScenarioCommands:
    """Commands for running scenario evaluations."""

    def sample(
        self,
        scenario: str | None = None,
        scenarios: str | None = None,
        variation: str | None = None,
        num_samples: int = 5,
        seed: int | None = None,
        model_config: str | None = None,
        log_dir: str = "./logs",
        no_upload: bool = False,
        verifier_agent: VerifierAgentType | None = None,
        scorers: str | None = None,
        estimate_cost: bool = False,
        # eval_set performance parameters
        display: DisplayType = "log",
        max_tasks: int = 50,
        max_connections: int = 50,
        max_sandboxes: int | None = None,
        max_subprocesses: int | None = None,
        fail_on_error: bool = False,
        retry_on_error: int = 3,
        sandbox: str | None = None,
        # eval_set additional parameters
        timeout: int | None = None,
        max_retries: int | None = None,
        log_samples: bool = True,
        message_limit: int | None = None,
        token_limit: int | None = None,
        push: bool = False,
        ignore_unstaged: bool = False,
        **kwargs: Any,
    ) -> None:
        """Run evaluation on random task samples from one or more scenarios.

        All tasks are run in parallel using eval_set for optimal performance.
        Samples are distributed across models using variance-reduced allocation
        based on weights defined in the model config.

        Args:
            scenario: Single scenario name (e.g., "gpu_decision_email_assistant")
            scenarios: Space-separated scenario names (e.g., "gpu_decision_email_assistant hospital_hvac")
            variation: For scenarios using variations, sample only from this variation (e.g., "alert", "leaking")
            num_samples: Total number of random tasks to sample (distributed across scenarios) (default: 5)
            seed: Random seed for reproducibility (default: random)
            model_config: Path to JSON file with model configs (name, weight, short_name, lab).
                         If not provided, uses MODEL_CONFIGS from lib/model_configs.py.
            log_dir: Base directory for logs (default: "./logs")
            no_upload: Skip uploading logs to S3 (default: False)
            verifier_agent: The name of the verifier agent to use in the evaluation
            scorers: A list of scorers to apply to all tasks
            estimate_cost: Run sample tasks to estimate token usage for the full evaluation (default: False)
            display: Display type - "full", "log", or "plain" (default: "log")
            max_tasks: Maximum number of tasks to run in parallel (default: 50)
            max_connections: Maximum number of concurrent connections to Model API (default: 50)
            max_sandboxes: Maximum number of sandboxes to run in parallel (default: None)
            max_subprocesses: Maximum number of subprocesses to run in parallel (default: None)
            fail_on_error: Fail on first sample error (default: False)
            retry_on_error: Number of times to retry samples on errors (default: 3)
            sandbox: Sandbox environment type (default: None)
            timeout: Request timeout in seconds (default: None)
            max_retries: Maximum number of times to retry request (default: None)
            log_samples: Log detailed samples and scores (default: True)
            message_limit: Limit on total messages per sample (default: None)
            token_limit: Limit on total tokens per sample (default: None)
            push: Whether or not to commit and push working changes
            ignore_unstaged: Whether or not to ignore unstaged changes
            **kwargs: Captured to detect unknown arguments

        Examples:
            # Run with default model config (lib/model_configs.py)
            uv run run_scenarios sample --scenario sem_v2 --num_samples 100 --seed 42

            # Estimate cost before running full evaluation
            uv run run_scenarios sample --scenario sem_v2 --num_samples 100 --estimate-cost --seed 42

            # Run with custom model config JSON
            uv run run_scenarios sample --scenario agentic_misalignment_v2 --model-config my_models.json --seed 42

            # Multiple scenarios
            uv run run_scenarios sample --scenarios "gpu_decision_email_assistant sem_v2" --num_samples 100 --seed 42
        """
        # Reject unknown arguments
        if kwargs:
            unknown = ", ".join(f"--{k}" for k in kwargs.keys())
            raise ValueError(f"Unknown argument(s): {unknown}")

        if not seed:
            seed = random.randint(0, (1 << 64) - 1)
        random.seed(seed)

        # Parse scenario arguments first (needed for sample allocation)
        if scenario and scenarios:
            raise ValueError("Specify either --scenario or --scenarios, not both")
        if not scenario and not scenarios:
            available = _get_available_scenarios()
            raise ValueError(
                f"Must specify --scenario or --scenarios. Available: {', '.join(available)}"
            )

        if scenario:
            scenario_names = [scenario]
        else:
            assert scenarios is not None, (
                "scenarios must be provided if scenario is not"
            )
            scenario_names = scenarios.split()

        auto_push_working_changes(push, ignore_unstaged)

        # Calculate per-scenario sample allocation (distribute num_samples across scenarios)
        num_scenarios = len(scenario_names)
        base_samples_per_scenario = num_samples // num_scenarios
        remaining_samples = num_samples % num_scenarios

        # Create RNG for consistent random decisions
        rng = random.Random(seed)

        # Randomly select which scenarios get extra samples
        scenario_indices_for_extra = (
            set(rng.sample(range(num_scenarios), remaining_samples))
            if remaining_samples > 0
            else set()
        )

        # Build dict of samples per scenario
        samples_per_scenario = {}
        for idx, scenario_name in enumerate(scenario_names):
            samples_per_scenario[scenario_name] = base_samples_per_scenario + (
                1 if idx in scenario_indices_for_extra else 0
            )

        # Load model config from JSON file or use default
        loaded_model_configs = None
        if model_config:
            print(f"Loading model config from: {model_config}")
            loaded_model_configs = load_model_configs_from_json(model_config)
        # If no config provided, setup_multi_model_mode will use default MODEL_CONFIGS

        # Create model assignments using variance-reduced allocation
        model_assignments, normalized_configs = setup_multi_model_mode(
            num_samples=num_samples,
            seed=seed,
            model_configs=loaded_model_configs,
        )

        # Capture run context early so task_generator closure can access it
        run_context = _capture_run_context()

        # Store model config info in run context
        run_context["model_allocation"] = dict(Counter(model_assignments))
        if model_config:
            run_context["model_config_file"] = model_config
        # Warn if running on non-main branch or with uncommitted changes
        if run_context["git_branch"] != "main":
            logger.warning(
                f"Running evaluation on branch '{run_context['git_branch']}' (not 'main')"
            )
            print(
                f"\n⚠️  WARNING: Running evaluation on branch '{run_context['git_branch']}' (not 'main')"
            )
        if run_context["git_dirty"]:
            logger.warning(
                "Running evaluation with uncommitted changes in the working directory"
            )
            print(
                "⚠️  WARNING: Running evaluation with uncommitted changes in the working directory\n"
            )

        # Create task generator function that captures sample-specific parameters
        def task_generator(
            scenario_name: str, scenario_def: ScenarioDefinition
        ) -> list[Task]:
            return _generate_sample_tasks(
                scenario_name,
                seed,
                scenario_def,
                samples_per_scenario[scenario_name],
                run_context,
                variation,
            )

        scorer_funcs: list[Scorer] = []
        if scorers:
            for scorer_name in scorers.split(" ,"):
                if scorer_name not in SCORER_REGISTRY:
                    raise ValueError(f"scorer {scorer_name} not in registry!")
                scorer_func = SCORER_REGISTRY[scorer_name]
                scorer_funcs.append(scorer_func())

        _run_evaluation(
            scenario_names=scenario_names,
            task_generator=task_generator,
            seed=seed,
            model_assignments=model_assignments,
            log_dir=log_dir,
            epochs=1,
            display=display,
            max_tasks=max_tasks,
            max_connections=max_connections,
            max_sandboxes=max_sandboxes,
            max_subprocesses=max_subprocesses,
            fail_on_error=fail_on_error,
            retry_on_error=retry_on_error,
            sandbox=sandbox,
            timeout=timeout,
            scorers=scorer_funcs,
            max_retries=max_retries,
            log_samples=log_samples,
            message_limit=message_limit,
            token_limit=token_limit,
            num_samples=num_samples,
            no_upload=no_upload,
            run_context=run_context,
            verifier_agent=verifier_agent,
            estimate_cost=estimate_cost,
        )

    def list(self, **kwargs: Any) -> None:
        """List all available scenarios.

        Args:
            **kwargs: Captured to detect unknown arguments

        Examples:
            uv run run_scenarios list
        """
        # Reject unknown arguments
        if kwargs:
            unknown = ", ".join(f"--{k}" for k in kwargs.keys())
            raise ValueError(f"Unknown argument(s): {unknown}")

        scenarios = _get_available_scenarios()
        print("Available scenarios:")
        for scenario in scenarios:
            try:
                scenario_def = _load_scenario(scenario)
                validation_status = (
                    "validation: enabled"
                    if scenario_def.template_engine is not None
                    else "validation: disabled"
                )
                print(f"  {scenario}")

                # Handle both old (suites) and new (variations) structures
                if scenario_def.variations is not None:
                    for var_name, variation in scenario_def.variations.items():
                        suite_names = variation.get_suite_names()
                        print(f"    Variation '{var_name}': {', '.join(suite_names)}")
                elif scenario_def.suites is not None:
                    suites = list(scenario_def.suites.keys())
                    print(f"    Suites: {', '.join(suites)}")
                else:
                    print("    (no suites or variations defined)")

                print(f"    Parameter {validation_status}")
            except Exception as e:
                print(f"  {scenario} (error loading: {e})")

    def sample_to_target(
        self,
        target_config: str,
        seed: int | None = None,
        log_dir: str = "./logs",
        count_failures: bool = True,
        dry_run: bool = False,
        no_upload: bool = False,
        num_samples: int | None = None,
        skip_models: str | None = None,
        skip_scenarios: str | None = None,
        # eval_set performance parameters
        display: DisplayType = "log",
        max_tasks: int = 50,
        max_connections: int = 50,
        max_sandboxes: int | None = None,
        max_subprocesses: int | None = None,
        fail_on_error: bool = False,
        retry_on_error: int = 3,
        sandbox: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        log_samples: bool = True,
        message_limit: int | None = None,
        token_limit: int | None = None,
        push: bool = False,
        ignore_unstaged: bool = False,
        **kwargs: Any,
    ) -> None:
        """Sample to reach target counts per (model, variation), accounting for existing S3 logs.

        Reads a target configuration file specifying desired sample counts per
        (model, scenario/variation) pair. Queries structured storage to count
        existing valid samples, then samples only the delta needed to reach targets.

        If num_samples is specified, limits the run to that many samples total,
        distributed proportionally across (model, variation) pairs based on their
        remaining gap. This allows running in batches toward the final targets.

        Args:
            target_config: Path to JSON config file with target counts. Format:
                {
                    "targets": {
                        "claude-sonnet-4-20250514": {
                            "sem_v2/classification": 100,
                            "agentic_misalignment_v2/alert": 50
                        }
                    }
                }
            seed: Random seed for reproducibility (default: random)
            log_dir: Base directory for logs (default: "./logs")
            count_failures: Count failed runs toward targets (default: True)
            dry_run: Show what would be sampled without running (default: False)
            no_upload: Skip uploading logs to S3 (default: False)
            num_samples: Maximum number of samples to run in this batch (default: None = all).
                If set, distributes samples proportionally across (model, variation) pairs
                based on their remaining gap to target.
            skip_models: Space-separated list of model substrings to skip (e.g., "opus-4-5 sonnet-4").
                Models containing any of these substrings will be excluded.
            skip_scenarios: Space-separated list of scenario substrings to skip (e.g., "sem agentic").
                Scenarios whose name contains any of these substrings will be excluded.
            display: Display type - "full", "log", or "plain" (default: "log")
            max_tasks: Maximum number of tasks to run in parallel (default: 50)
            max_connections: Maximum number of concurrent connections to Model API (default: 50)
            max_sandboxes: Maximum number of sandboxes to run in parallel (default: None)
            max_subprocesses: Maximum number of subprocesses to run in parallel (default: None)
            fail_on_error: Fail on first sample error (default: False)
            retry_on_error: Number of times to retry samples on errors (default: 3)
            sandbox: Sandbox environment type (default: None)
            timeout: Request timeout in seconds (default: None)
            max_retries: Maximum number of times to retry request (default: None)
            log_samples: Log detailed samples and scores (default: True)
            message_limit: Limit on total messages per sample (default: None)
            token_limit: Limit on total tokens per sample (default: None)
            push: Whether or not to commit and push working changes
            ignore_unstaged: Whether or not to ignore unstaged changes
            **kwargs: Captured to detect unknown arguments

        Examples:
            # Sample to reach targets defined in config file
            uv run run_scenarios sample_to_target --target_config targets.json --seed 42

            # Dry run to see what would be sampled
            uv run run_scenarios sample_to_target --target_config targets.json --dry_run

            # Run a batch of 20000 samples toward targets (for parallel execution)
            uv run run_scenarios sample_to_target --target_config targets.json --num_samples 20000
        """
        # Reject unknown arguments
        if kwargs:
            unknown = ", ".join(f"--{k}" for k in kwargs.keys())
            raise ValueError(f"Unknown argument(s): {unknown}")

        print("\n" + "=" * 60)
        print("⚠️  EXPERIMENTAL: sample_to_target is under development")
        print("=" * 60 + "\n")

        if not seed:
            seed = random.randint(0, (1 << 64) - 1)
        random.seed(seed)

        # Load target config
        config_path = Path(target_config)
        if not config_path.exists():
            raise FileNotFoundError(f"Target config file not found: {target_config}")

        with open(config_path) as f:
            config = json.load(f)

        if "targets" not in config:
            raise ValueError("Config must have 'targets' key")

        targets: dict[str, dict[str, int]] = config["targets"]

        # Parse skip lists
        skip_model_list = skip_models.split() if skip_models else []
        skip_scenario_list = skip_scenarios.split() if skip_scenarios else []

        # Filter out skipped models
        if skip_model_list:
            original_model_count = len(targets)
            targets = {
                model: model_targets
                for model, model_targets in targets.items()
                if not any(skip in model for skip in skip_model_list)
            }
            skipped = original_model_count - len(targets)
            if skipped > 0:
                print(f"Skipping {skipped} models matching: {skip_model_list}")

        # Filter out skipped scenarios from each model's targets
        # Uses substring matching on the scenario name (before the "/")
        if skip_scenario_list:
            skipped_count = 0
            for model in targets:
                original_count = len(targets[model])
                targets[model] = {
                    scenario_var: count
                    for scenario_var, count in targets[model].items()
                    if not any(
                        skip in scenario_var.split("/")[0]
                        for skip in skip_scenario_list
                    )
                }
                skipped_count += original_count - len(targets[model])
            if skipped_count > 0:
                print(
                    f"Skipping {skipped_count} scenario entries matching: {skip_scenario_list}"
                )

            # Remove models with no remaining targets
            targets = {m: t for m, t in targets.items() if t}

        if not targets:
            print("No targets remaining after filtering. Nothing to do.")
            return

        # Validate targets - ensure all scenario/variations exist
        print("Validating target configuration...")
        for model, model_targets in targets.items():
            for scenario_variation in model_targets.keys():
                parts = scenario_variation.split("/", 1)
                if len(parts) != 2:
                    raise ValueError(
                        f"Invalid target key '{scenario_variation}'. "
                        f"Expected format: 'scenario_name/variation_name'"
                    )
                scenario_name, variation_name = parts
                if scenario_name not in SCENARIO_FACTORIES:
                    raise ValueError(
                        f"Unknown scenario '{scenario_name}' in target key '{scenario_variation}'"
                    )
                # Validate variation exists
                scenario_def = _load_scenario(scenario_name)
                if scenario_def.variations is None:
                    raise ValueError(
                        f"Scenario '{scenario_name}' has no variations defined"
                    )
                if variation_name not in scenario_def.variations:
                    available_vars = list(scenario_def.variations.keys())
                    raise ValueError(
                        f"Unknown variation '{variation_name}' in scenario '{scenario_name}'. "
                        f"Available: {available_vars}"
                    )

        auto_push_working_changes(push, ignore_unstaged)

        # Get bucket from environment
        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise ValueError("S3_BUCKET environment variable not set")

        # Count existing samples from structured storage
        print(f"\n{'=' * 60}")
        print("Counting existing samples from structured storage (parallel)...")
        print(f"{'=' * 60}")

        existing_counts: dict[str, dict[str, int]] = {}

        # Query structured storage for each (model, scenario, variation) in targets
        for model, model_targets in targets.items():
            existing_counts[model] = {}

            for scenario_variation in model_targets.keys():
                scenario_name, variation_name = scenario_variation.split("/", 1)

                count = _count_existing_samples(
                    model=model,
                    scenario=scenario_name,
                    variation=variation_name,
                    bucket=bucket,
                    count_failures=count_failures,
                )
                existing_counts[model][scenario_variation] = count
                print(f"  {model} / {scenario_variation}: {count} existing")

        # Calculate deltas
        print(f"\n{'=' * 60}")
        print("Calculating sample deltas...")
        print(f"{'=' * 60}")

        # Structure: list of (model, scenario_name, variation_name, delta)
        deltas: list[tuple[str, str, str, int]] = []
        total_delta = 0

        for model, model_targets in targets.items():
            model_existing = existing_counts.get(model, {})
            for scenario_variation, target_count in model_targets.items():
                existing = model_existing.get(scenario_variation, 0)
                delta = max(0, target_count - existing)
                total_delta += delta

                scenario_name, variation_name = scenario_variation.split("/", 1)
                status = "✓" if delta == 0 else f"+{delta}"
                print(
                    f"  {model} / {scenario_variation}: "
                    f"{existing}/{target_count} ({status})"
                )

                if delta > 0:
                    deltas.append((model, scenario_name, variation_name, delta))

        if total_delta == 0:
            print("\n✓ All targets already met. Nothing to sample.")
            return

        print(f"\nTotal samples needed to reach all targets: {total_delta}")

        # If num_samples is specified, limit and distribute proportionally
        if num_samples is not None and num_samples < total_delta:
            print(f"Limiting to {num_samples} samples (--num_samples)")
            print(f"Progress: {num_samples / total_delta * 100:.1f}% of remaining gap")

            # Distribute num_samples proportionally across deltas
            new_deltas = []
            allocated = 0

            # Sort by delta size (largest first) for consistent rounding
            sorted_deltas = sorted(deltas, key=lambda x: -x[3])

            for i, (model, scenario_name, variation_name, delta) in enumerate(
                sorted_deltas
            ):
                if i == len(sorted_deltas) - 1:
                    # Last item gets remainder to ensure exact num_samples
                    allocation = num_samples - allocated
                else:
                    # Proportional allocation
                    proportion = delta / total_delta
                    allocation = int(round(num_samples * proportion))

                # Don't exceed the original delta
                allocation = min(allocation, delta)
                if allocation > 0:
                    new_deltas.append(
                        (model, scenario_name, variation_name, allocation)
                    )
                allocated += allocation

            deltas = new_deltas
            total_delta = sum(d[3] for d in deltas)
            print(f"Samples in this batch: {total_delta}")

        # Print cost estimation (for full targets if num_samples not set)
        if num_samples is None:
            _print_cost_summary(existing_counts, targets)
        else:
            # Simple cost estimate for this batch
            print(f"\n{'=' * 60}")
            print("Batch cost estimate:")
            print(f"{'=' * 60}")
            batch_cost = 0.0
            for model, scenario_name, variation_name, delta in deltas:
                cost_per_sample = _estimate_sample_cost(model, scenario_name)
                if cost_per_sample:
                    batch_cost += delta * cost_per_sample
            print(f"Estimated cost for this batch: ${batch_cost:,.2f}")

        if dry_run:
            print("\n[Dry run] Would sample the following:")
            for model, scenario_name, variation_name, delta in deltas:
                print(
                    f"  {delta} samples of {scenario_name}/{variation_name} for {model}"
                )
            return

        # Capture run context
        run_context = _capture_run_context()
        run_context["target_config"] = str(config_path)
        run_context["existing_counts"] = existing_counts

        # Warn if running on non-main branch or with uncommitted changes
        if run_context["git_branch"] != "main":
            print(
                f"\n⚠️  WARNING: Running evaluation on branch '{run_context['git_branch']}' (not 'main')"
            )
        if run_context["git_dirty"]:
            print(
                "⚠️  WARNING: Running evaluation with uncommitted changes in the working directory\n"
            )

        # Generate tasks for each (model, scenario, variation, delta)
        print(f"\n{'=' * 60}")
        print("Generating tasks...")
        print(f"{'=' * 60}")

        all_tasks = []
        rng = random.Random(seed)

        for model, scenario_name, variation_name, delta in deltas:
            print(f"\n  {scenario_name}/{variation_name} for {model}: {delta} samples")

            scenario_def = _load_scenario(scenario_name)
            suites = _get_suites_from_scenario(scenario_def, variation_name)
            if not suites:
                print("    Warning: No suites found, skipping")
                continue

            # Get suite weights (always present - Variation validates this at construction)
            suite_weights = _get_suite_weights_from_scenario(
                scenario_def, variation_name
            )

            # Generate tasks using weighted sampling
            suite_items = list(suites.items())

            # Calculate samples per suite (same logic as _generate_sample_tasks)
            # All Variations must have suite_weights (enforced by Variation class)
            weights = []
            for name, _ in suite_items:
                if name not in suite_weights:
                    raise ValueError(
                        f"Suite '{name}' has no weight defined. "
                        f"Available weights: {list(suite_weights.keys())}"
                    )
                weights.append(suite_weights[name])

            total_weight = sum(weights)
            samples_per_suite = []
            for w in weights:
                proportion = w / total_weight
                samples_per_suite.append(int(delta * proportion))

            remaining = delta - sum(samples_per_suite)
            if remaining > 0:
                fractional_parts = []
                for i, w in enumerate(weights):
                    proportion = w / total_weight
                    fractional = (delta * proportion) - samples_per_suite[i]
                    fractional_parts.append((fractional, i))
                fractional_parts.sort(reverse=True)
                for _, idx in fractional_parts[:remaining]:
                    samples_per_suite[idx] += 1

            for suite_idx, (suite_key, space_func) in enumerate(suite_items):
                var_name_parsed, suite_name = suite_key.split("/", 1)
                space = space_func()

                samples_for_suite = samples_per_suite[suite_idx]
                if samples_for_suite == 0:
                    continue

                print(f"    {suite_key}: {samples_for_suite} samples")

                suite_seed = rng.randint(0, (1 << 64) - 1)
                iterator = space.sample_weighted(n=samples_for_suite, seed=suite_seed)

                for params in iterator:
                    task = scenario_def.params_to_task(params)
                    global_sample_idx = len(all_tasks)
                    task = _enrich_task_metadata_inplace(
                        task,
                        run_context,
                        params,
                        scenario_name,
                        var_name_parsed,
                        suite_name,
                        space,
                        user_name=os.environ.get("S3_USER", "unknown"),
                        sample_index=global_sample_idx,
                    )
                    # Apply model assignment
                    for sample in task.dataset:
                        if sample.metadata is None:
                            sample.metadata = {}
                        sample.metadata["assigned_model"] = model
                    task = task_with(task, model=model)
                    all_tasks.append(task)

        if not all_tasks:
            print("\nNo tasks generated. Check configuration.")
            return

        print(f"\n✓ Generated {len(all_tasks)} total tasks")

        # Create timestamped log directory
        base_log_dir = _create_timestamped_log_dir(log_dir)
        print(f"\nLocal logs: {base_log_dir}")
        if bucket and not no_upload:
            print(f"S3 upload: ENABLED (uploading to {bucket} during run)")

        # Save run configuration
        _save_run_config(base_log_dir, run_context)

        print(f"\n{'=' * 60}")
        print("Running evaluation (parallel execution via eval_set)...")
        print(f"{'=' * 60}")

        # Show progress bar
        show_progress_bar_for_eval_set(str(base_log_dir), len(all_tasks))

        # Start background S3 uploader
        if bucket and not no_upload:
            start_background_s3_uploader(str(base_log_dir), bucket)

        # Run evaluation with cleanup in finally block to handle Ctrl+C gracefully
        try:
            # Run all tasks
            success, logs = eval_set(
                all_tasks,
                log_dir=str(base_log_dir),
                epochs=1,
                display=display,
                max_tasks=max_tasks,
                max_connections=max_connections,
                max_sandboxes=max_sandboxes,
                max_subprocesses=max_subprocesses,
                fail_on_error=fail_on_error,
                retry_on_error=retry_on_error,
                sandbox=sandbox,
                timeout=timeout,
                max_retries=max_retries,
                log_samples=log_samples,
                message_limit=message_limit,
                token_limit=token_limit,
            )
        except KeyboardInterrupt:
            print("\n\nInterrupted by user.")
            return
        finally:
            # Always update listing.json so any uploaded evals appear in the viewer
            # This runs while resources are still alive, avoiding shutdown race conditions
            _update_listing_on_cleanup(bucket, no_upload)

        # Report results
        print(f"\n{'=' * 60}")
        if success:
            print(f"✓ Evaluation complete: {len(logs)} task(s) evaluated")
        else:
            print(f"✗ Evaluation completed with errors: {len(logs)} task(s) evaluated")
        print(f"Results saved to: {base_log_dir}")
        print(f"{'=' * 60}")

        _print_score_table(logs)


def main() -> None:
    """Entry point for the scenario CLI."""
    fire.Fire(ScenarioCommands)


if __name__ == "__main__":
    main()
