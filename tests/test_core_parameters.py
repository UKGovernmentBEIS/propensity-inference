"""
Test that all scenarios properly implement core parameters.

This test validates that all ParameterSpaces across all scenarios:
1. Include the required core parameters (or explicitly exclude them)
2. Have values within the permitted set for each parameter
3. Can be properly extracted for statistical analysis

Run with: uv run pytest tests/test_core_parameters.py -v
"""

import re
from datetime import datetime
from typing import Any

import pytest

from scenarios.core_parameter_space import (
    CORE_PARAMETERS,
    KNOWN_MISSING_ABLATIONS,
)


def validate_date(value: str) -> bool:
    """Check if value is a valid YYYY-MM-DD date."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_params(params: dict[str, Any], scenario_name: str) -> list[str]:
    """
    Validate that params contain all required core parameters with valid values.

    Returns list of error messages (empty if valid).
    """
    errors = []
    known_excluded = KNOWN_MISSING_ABLATIONS.get(scenario_name, set())

    for param_name, spec in CORE_PARAMETERS.items():
        # Check if parameter is present
        if param_name not in params:
            if spec["required"] and param_name not in known_excluded:
                errors.append(
                    f"Missing required parameter '{param_name}' ({spec['description']})"
                )
            continue

        value = params[param_name]

        # Validate value
        if param_name == "date":
            if not validate_date(value):
                errors.append(
                    f"Invalid date format for '{param_name}': {value} "
                    f"(expected YYYY-MM-DD)"
                )
        elif spec["values"] is not None:
            if value not in spec["values"]:
                errors.append(
                    f"Invalid value for '{param_name}': {value} "
                    f"(expected one of {sorted(spec['values'])})"
                )

    return errors


def get_all_scenario_suites() -> list[tuple[str, str, Any]]:
    """
    Dynamically discover and load all scenario suites.

    Returns list of (scenario_name, suite_name, space_factory) tuples.
    """
    suites = []

    # GPU Decision Email Assistant
    try:
        from scenarios.gpu_decision_email_assistant.parameter_spaces import (
            create_gpu_decision_suite,
        )

        suites.append(
            ("gpu_decision_email_assistant", "main", create_gpu_decision_suite)
        )
    except ImportError:
        pass

    # Hiding Reward Hacking
    try:
        from scenarios.hiding_reward_hacking.parameter_spaces import (
            create_suite_space as hrh_create_suite,
        )

        suites.append(("hiding_reward_hacking", "main", hrh_create_suite))
    except ImportError:
        pass

    # Power Preservation
    try:
        from scenarios.power_preservation.parameter_spaces import VARIATIONS as pp_vars

        for var_name, variation in pp_vars.items():
            for suite_name, suite_factory in variation.suites.items():
                suites.append(
                    ("power_preservation", f"{var_name}/{suite_name}", suite_factory)
                )
    except ImportError:
        pass

    # Email Spam Filter v2
    try:
        from scenarios.email_spam_filter_v2.parameter_spaces import (
            VARIATIONS as esf_vars,
        )

        for var_name, variation in esf_vars.items():
            for suite_name, suite_factory in variation.suites.items():
                suites.append(
                    ("email_spam_filter_v2", f"{var_name}/{suite_name}", suite_factory)
                )
    except ImportError:
        pass

    # SEM v2
    try:
        from scenarios.sem_v2.parameter_spaces import VARIATIONS as sem_vars

        for var_name, variation in sem_vars.items():
            for suite_name, suite_factory in variation.suites.items():
                suites.append(("sem_v2", f"{var_name}/{suite_name}", suite_factory))
    except ImportError:
        pass

    # Agentic Misalignment v2
    try:
        from scenarios.agentic_misalignment_v2.parameter_spaces import (
            VARIATIONS as am_vars,
        )

        for var_name, variation in am_vars.items():
            for suite_name, suite_factory in variation.suites.items():
                suites.append(
                    (
                        "agentic_misalignment_v2",
                        f"{var_name}/{suite_name}",
                        suite_factory,
                    )
                )
    except ImportError:
        pass

    return suites


# Get all suites for parametrization
ALL_SUITES = get_all_scenario_suites()


@pytest.mark.parametrize(
    "scenario_name,suite_name,suite_factory",
    ALL_SUITES,
    ids=[f"{s[0]}:{s[1]}" for s in ALL_SUITES],
)
def test_suite_has_valid_core_parameters(
    scenario_name: str, suite_name: str, suite_factory
):
    """Test that a suite produces valid core parameters."""
    import random

    random.seed(42)

    space = suite_factory()
    space_size = space.size()

    # Sample 10 random parameter combinations
    num_samples = min(10, space_size)
    all_errors = []

    for _ in range(num_samples):
        idx = random.randint(0, space_size - 1)
        params = space.get_combination(idx)
        errors = validate_params(params, scenario_name)
        all_errors.extend(errors)

    if all_errors:
        # Deduplicate errors
        unique_errors = sorted(set(all_errors))
        pytest.fail(
            f"Core parameter validation failed for {scenario_name}/{suite_name}:\n"
            + "\n".join(f"  - {e}" for e in unique_errors)
        )


def test_all_scenarios_discovered():
    """Ensure we're testing all expected scenarios."""
    expected_scenarios = {
        "gpu_decision_email_assistant",
        "hiding_reward_hacking",
        "power_preservation",
        "email_spam_filter_v2",
        "sem_v2",
        "agentic_misalignment_v2",
    }

    discovered = {s[0] for s in ALL_SUITES}
    missing = expected_scenarios - discovered

    if missing:
        pytest.fail(
            f"Expected scenarios not discovered: {missing}. "
            "Check imports in get_all_scenario_suites()."
        )


def test_core_parameters_definition():
    """Verify CORE_PARAMETERS has all 12 expected parameters."""
    expected_params = {
        "goal_present",
        "goal_conflict",
        "threat",
        "cot_privacy",
        "action_oversight",
        "action_efficacy",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "anti_misalignment",
        "filler_richness",
        "date",
    }

    defined_params = set(CORE_PARAMETERS.keys())

    missing = expected_params - defined_params
    extra = defined_params - expected_params

    if missing:
        pytest.fail(f"Missing parameters in CORE_PARAMETERS: {missing}")
    if extra:
        pytest.fail(f"Unexpected parameters in CORE_PARAMETERS: {extra}")
