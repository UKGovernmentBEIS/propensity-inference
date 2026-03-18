import pytest

from lib.trace_formatting import format_trace
from scenarios.scenario_registry import SCENARIO_FACTORIES


def _get_all_suites(scenario_def):
    """Get all suites from a scenario, handling both legacy and variations structures."""
    all_suites = {}

    # Legacy structure: suites directly on scenario_def
    if scenario_def.suites is not None:
        all_suites.update(scenario_def.suites)

    # New structure: suites inside variations
    if scenario_def.variations is not None:
        for variation in scenario_def.variations.values():
            # Prefix suite names with variation name to avoid collisions
            for suite_name, suite_fn in variation.suites.items():
                all_suites[f"{variation.name}/{suite_name}"] = suite_fn

    return all_suites


@pytest.mark.parametrize(
    "scenario",
    SCENARIO_FACTORIES.keys(),
)
def test_all_scenario_param_spaces_are_deterministic(
    scenario: str,
):
    """
    Test that same parameter samples produce identical prompts, ensuring reproducibility.

    Verifies end-to-end determinism: sampling parameters with the same seed
    and converting them to tasks via params_to_task() produces byte-for-byte
    identical prompt content across runs.
    """
    scenario_def = SCENARIO_FACTORIES[scenario]()
    all_suites = _get_all_suites(scenario_def)
    assert all_suites, f"Scenario {scenario} has no suites defined"
    for suite_name, param_space_def in all_suites.items():
        # the seed is shared
        seed = 0

        # construct two sets of tasks using separate spaces
        space1 = param_space_def()
        tasks1 = [
            scenario_def.params_to_task(params)
            for params in space1.sample_uniformly_random(30, seed=seed)
        ]

        space2 = param_space_def()
        tasks2 = [
            scenario_def.params_to_task(params)
            for params in space2.sample_uniformly_random(30, seed=seed)
        ]

        assert len(tasks1) == len(tasks2)
        for task1, task2 in zip(tasks1, tasks2):
            assert len(task1.dataset) == 1
            assert len(task2.dataset) == 1
            sample1 = task1.dataset[0]
            sample2 = task2.dataset[0]
            trace1 = format_trace(sample1.input, remove_verification_instructions=False)
            trace2 = format_trace(sample2.input, remove_verification_instructions=False)
            assert trace1 == trace2
