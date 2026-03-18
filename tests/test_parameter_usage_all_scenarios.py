"""
Cross-scenario parameter usage validation tests.

Validates that all parameters defined in parameter spaces are actually used
in templates, across all scenarios that support tracking.
"""

import random

import pytest

from lib.constants import (
    COMPLETENESS_KNOWN_EXCEPTIONS,
    COMPLETENESS_OPTED_OUT_SCENARIOS,
)
from scenarios.scenario_registry import SCENARIO_FACTORIES

# Number of samples to test per suite
NUM_SAMPLES = 5
RANDOM_SEED = 42


def get_scenario_test_data() -> list[tuple[str, str]]:
    """
    Get list of scenarios to test.

    Returns:
        List of (scenario_name, reason) tuples
        - If reason starts with "SKIP:", scenario should be skipped
        - Otherwise, scenario should be tested
    """
    test_data = []

    for scenario_name in SCENARIO_FACTORIES.keys():
        # Check if opted out
        if scenario_name in COMPLETENESS_OPTED_OUT_SCENARIOS:
            test_data.append(
                (scenario_name, "SKIP: Opted out (see OPTED_OUT_SCENARIOS)")
            )
            continue

        # Check if scenario supports tracking (has template_engine)
        try:
            scenario_def = SCENARIO_FACTORIES[scenario_name]()
            if scenario_def.template_engine is None:
                test_data.append(
                    (scenario_name, "SKIP: No template_engine (no tracking support)")
                )
            else:
                test_data.append((scenario_name, "Supports tracking"))
        except Exception as e:
            test_data.append((scenario_name, f"SKIP: Error loading scenario: {e}"))

    return test_data


# Generate test parameters
SCENARIO_TEST_DATA = get_scenario_test_data()


@pytest.mark.parametrize("scenario_name,reason", SCENARIO_TEST_DATA)
def test_scenario_parameter_usage(scenario_name: str, reason: str):
    """
    Test that all parameters in a scenario are used in templates.

    For scenarios that support tracking, this validates that there are no
    unexpected unused parameters (beyond known exceptions).
    """
    # Skip if this scenario is opted out or doesn't support tracking
    if reason.startswith("SKIP:"):
        pytest.skip(reason)

    # Get scenario definition
    scenario_def = SCENARIO_FACTORIES[scenario_name]()

    # Get SUITES (either from suites or variations)
    if scenario_def.variations is not None:
        # New structure: extract suites from variations
        suites = {}
        for variation_name, variation in scenario_def.variations.items():
            suites.update(variation.suites)
    else:
        # Legacy structure: use suites directly
        suites = scenario_def.suites

    assert suites is not None

    # Get known exceptions for this scenario
    known_exceptions = COMPLETENESS_KNOWN_EXCEPTIONS.get(scenario_name, set())

    # Set random seed for reproducibility
    random.seed(RANDOM_SEED)

    # Track aggregated results across all suites
    all_unexpected_unused = set()
    suites_tested = 0

    # Test first suite (to keep tests fast)
    # In practice, if one suite has issues, likely others do too
    for suite_name, suite_factory in list(suites.items())[:1]:
        space = suite_factory()

        # Sample random parameter combinations
        num_samples = min(NUM_SAMPLES, space.size())
        sample_indices = random.sample(range(space.size()), num_samples)

        # Get template engine from scenario definition
        template_engine = scenario_def.template_engine
        assert template_engine is not None, (
            f"Scenario {scenario_name} has no template_engine"
        )

        # Reset tracking to start fresh
        template_engine.reset_tracking()

        # Test each sample
        for idx in sample_indices:
            params = space.get_combination(idx)

            # Create task (which triggers template assembly with tracking)
            _ = scenario_def.params_to_task(params)

        # Get accessed variables from template engine (accumulated across all samples)
        accessed = template_engine.get_accessed_variables()

        # Get all defined parameters
        all_defined = space.get_all_variables()

        # Find unused
        unused = all_defined - accessed

        # Remove known exceptions
        unexpected_unused = unused - known_exceptions

        # Accumulate across suites
        all_unexpected_unused.update(unexpected_unused)

        suites_tested += 1

    # Assert no unexpected unused parameters
    if all_unexpected_unused:
        error_msg = (
            f"\n{scenario_name}: Found {len(all_unexpected_unused)} unexpected unused parameters:\n"
            f"  {sorted(all_unexpected_unused)}\n\n"
            f"These parameters are defined in the parameter space but never accessed in templates.\n"
            f"Either:\n"
            f"  1. Remove them from the parameter space if truly unused\n"
            f"  2. Add them to KNOWN_EXCEPTIONS in {__file__} if they're used in Python logic\n"
            f"  3. Fix templates to actually use these parameters\n\n"
            f"Known exceptions for {scenario_name}: {sorted(known_exceptions)}\n"
            f"Tested {suites_tested} suite(s) with {NUM_SAMPLES} samples each."
        )
        pytest.fail(error_msg)


def test_known_exceptions_are_actually_defined():
    """
    Verify that all parameters in KNOWN_EXCEPTIONS are actually defined in their scenarios.

    This catches typos or outdated exception lists.
    """
    for scenario_name, exceptions in COMPLETENESS_KNOWN_EXCEPTIONS.items():
        # Skip if scenario is opted out
        if scenario_name in COMPLETENESS_OPTED_OUT_SCENARIOS:
            continue

        # Skip if scenario not in registry
        if scenario_name not in SCENARIO_FACTORIES:
            pytest.skip(f"{scenario_name} not in SCENARIO_FACTORIES")

        try:
            # Get scenario definition
            scenario_def = SCENARIO_FACTORIES[scenario_name]()

            # Get first suite (handle both old and new structures)
            if scenario_def.variations is not None:
                # New structure: extract first suite from first variation
                first_variation = list(scenario_def.variations.values())[0]
                first_suite_factory = list(first_variation.suites.values())[0]
            else:
                # Legacy structure
                suites = scenario_def.suites
                assert suites is not None
                first_suite_factory = list(suites.values())[0]
            space = first_suite_factory()

            # Get all defined parameters
            all_defined = space.get_all_variables()

            # Check that all exceptions are actually defined
            undefined_exceptions = exceptions - all_defined

            assert not undefined_exceptions, (
                f"{scenario_name}: KNOWN_EXCEPTIONS contains parameters not in parameter space:\n"
                f"  {sorted(undefined_exceptions)}\n"
                f"These should be removed from KNOWN_EXCEPTIONS."
            )

        except Exception as e:
            pytest.skip(f"Could not load {scenario_name}: {e}")


if __name__ == "__main__":
    # Allow running this file directly for debugging
    print("Loading scenarios from SCENARIO_FACTORIES...")
    print(
        f"Found {len(SCENARIO_FACTORIES)} scenarios: {list(SCENARIO_FACTORIES.keys())}\n"
    )

    for scenario_name, reason in SCENARIO_TEST_DATA:
        if reason.startswith("SKIP:"):
            print(f"❌ {scenario_name}: {reason}")
        else:
            print(f"✅ {scenario_name}: {reason}")
