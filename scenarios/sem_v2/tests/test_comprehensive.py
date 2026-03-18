"""
Comprehensive tests for sem_v2 parameter spaces.
"""

import logging

import pytest

from scenarios.sem_v2.create_scenario import create_scenario
from scenarios.sem_v2.parameter_spaces import SUITES

logger = logging.getLogger(__name__)

BASE_PARAMS = [
    "model",
    "exfiltrating_model",
    "company",
    "company_lowercase",
    "date",
    "session_start_time",
    "report_start_index",
    "cot_tag",
    "cot_privacy",
    "reasoning_instructions",
    "independence",
    "anti_misalignment",
    "num_false_alarms",
    "false_alarm_selection_seed",
    "user_instruction",
    "consequence_status",
    "goal",
    "_false_alarms_combo",
    "_true_positive_file",
]


@pytest.mark.parametrize(
    "suite_name,expected_size",
    [
        # Suites now organized by threat only (2 per variation).
        # goal_conflict is independent via core_parameter_space (3:1 odds).
        # goal_present is independent via core_parameter_space (8:1 odds).
        # action_oversight is removed (not used in templates).
        # Classification suites have escalation_bar (3 values) multiplier.
        ("classification_no_threat", 566_231_040_000),
        ("classification_threat", 6_794_772_480_000),
        ("summarization_no_threat", 707_788_800_000),
        ("summarization_threat", 8_493_465_600_000),
    ],
)
def test_parameter_space_size(suite_name, expected_size):
    """Test that a suite has the expected number of tasks."""
    logger.info(f"Testing {suite_name} size...")
    space = SUITES[suite_name]()
    actual_size = space.size()

    if actual_size == expected_size:
        logger.info(f"  ✓ Size correct: {actual_size:,} tasks")
    else:
        logger.error(
            f"  ✗ Size mismatch: expected {expected_size:,}, got {actual_size:,}"
        )

    assert actual_size == expected_size, (
        f"Size mismatch: expected {expected_size:,}, got {actual_size:,}"
    )


@pytest.mark.parametrize(
    "suite_name,num_samples",
    [
        ("classification_no_threat", 20),
        ("classification_threat", 20),
        ("summarization_no_threat", 20),
        ("summarization_threat", 30),
    ],
)
def test_sample_tasks(suite_name, num_samples):
    """Test creating tasks from sample parameter combinations."""
    logger.info(f"Testing {suite_name} task creation with {num_samples} samples...")
    scenario_def = create_scenario()
    space = SUITES[suite_name]()
    total_size = space.size()

    # Sample evenly across the space
    step = max(1, total_size // num_samples)
    indices = [i * step for i in range(num_samples)]

    failed = []
    for i, idx in enumerate(indices):
        try:
            params = space.get_combination(idx)
            task = scenario_def.params_to_task(params)

            # Verify key properties
            if not task.name:
                failed.append(f"Index {idx}: Task has no name")
            if not task.sandbox:
                failed.append(f"Index {idx}: Task has no sandbox")

        except Exception as e:
            failed.append(f"Index {idx}: {str(e)}")

    if not failed:
        logger.info(f"  ✓ All {len(indices)} sample tasks created successfully")
    else:
        logger.error(f"  ✗ {len(failed)} failures:")
        for error in failed[:5]:  # Show first 5 errors
            logger.error(f"    - {error}")
        if len(failed) > 5:
            logger.error(f"    ... and {len(failed) - 5} more")

    assert not failed, f"{len(failed)} task creation failures"


@pytest.mark.parametrize(
    "suite_name,expected_params",
    [
        (
            "classification_no_threat",
            BASE_PARAMS + ["goal_conflict", "goal_value", "escalation_bar"],
        ),
        (
            "classification_threat",
            BASE_PARAMS
            + [
                "goal_conflict",
                "goal_value",
                "escalation_bar",
                "threat_type",
                "threat_timing",
                "threat_date",
            ],
        ),
        ("summarization_no_threat", BASE_PARAMS + ["goal_conflict", "goal_value"]),
        (
            "summarization_threat",
            BASE_PARAMS
            + [
                "goal_conflict",
                "goal_value",
                "threat_type",
                "threat_timing",
                "threat_date",
            ],
        ),
    ],
)
def test_parameter_coverage(suite_name, expected_params):
    """Test that all expected parameters are present."""
    logger.info(f"Testing {suite_name} parameter coverage...")
    space = SUITES[suite_name]()
    params = space.get_combination(0)

    missing = []
    for param_name in expected_params:
        if param_name not in params:
            missing.append(param_name)

    if not missing:
        logger.info(f"  ✓ All {len(expected_params)} expected parameters present")
    else:
        logger.error(f"  ✗ Missing parameters: {missing}")

    assert not missing, f"Missing parameters: {missing}"


# All suites have all goal values because goal_present and goal_conflict are independent from suite type
# Goal is derived: equals goal_value when goal_present=true, else "none"
ALL_GOAL_VALUES = [
    "none",  # When goal_present=false
    "america_global",
    "global_america",
    "ethical_pragmatic",
    "pragmatic_ethical",
    "individual_collective",
    "collective_individual",
    "safety_acceleration",
    "acceleration_safety",
]


@pytest.mark.parametrize(
    "suite_name,param_name,expected_values",
    [
        ("classification_no_threat", "goal", ALL_GOAL_VALUES),
        ("classification_threat", "threat_type", ["replacement", "restriction"]),
        ("classification_threat", "threat_timing", ["today", "future_date"]),
        ("summarization_no_threat", "goal", ALL_GOAL_VALUES),
        ("summarization_threat", "goal", ALL_GOAL_VALUES),
    ],
)
def test_parameter_values(suite_name, param_name, expected_values):
    """Test that a parameter takes all expected values across the space."""
    logger.info(f"Testing {suite_name} parameter '{param_name}' values...")
    space = SUITES[suite_name]()

    # Sample to find all unique values (need dense sampling for large spaces)
    total_size = space.size()
    # Use more samples for massive spaces (50k samples for billions of tasks)
    sample_size = min(50000, total_size)
    step = max(1, total_size // sample_size)

    observed_values = set()
    for i in range(0, total_size, step):
        params = space.get_combination(i)
        if param_name in params:
            value = params[param_name]
            observed_values.add(value)

    expected_set = set(expected_values)
    missing = expected_set - observed_values
    extra = observed_values - expected_set

    if not missing and not extra:
        logger.info(
            f"  ✓ All {len(expected_values)} values found: {sorted(expected_values)}"
        )
    else:
        if missing:
            logger.error(f"  ✗ Missing values: {missing}")
        if extra:
            logger.error(f"  ✗ Extra values: {extra}")

    assert not missing and not extra, f"Missing: {missing}, Extra: {extra}"
