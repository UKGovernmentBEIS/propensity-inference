"""Tests for scenario registry completeness and validity.

This test ensures that:
1. Every scenario directory in scenarios/ is registered in SCENARIO_FACTORIES
2. Every entry in SCENARIO_FACTORIES has a valid create_scenario function
"""

from pathlib import Path

import pytest

from scenarios.scenario_registry import SCENARIO_FACTORIES


def get_scenario_directories() -> set[str]:
    """Get all valid scenario directories from the scenarios/ folder.

    Returns:
        Set of scenario directory names (excluding special directories)
    """
    scenarios_dir = Path(__file__).parent
    scenario_dirs = set()

    for item in scenarios_dir.iterdir():
        # Skip non-directories
        if not item.is_dir():
            continue

        # Skip special directories
        if item.name in ("__pycache__", ".pytest_cache"):
            continue

        # Only include directories with __init__.py
        if (item / "__init__.py").exists():
            scenario_dirs.add(item.name)

    return scenario_dirs


def test_all_scenario_directories_are_registered():
    """Test that every scenario directory is registered in SCENARIO_FACTORIES."""
    scenario_dirs = get_scenario_directories()
    registered_scenarios = set(SCENARIO_FACTORIES.keys())

    # Find scenarios that are in directories but not in registry
    unregistered = scenario_dirs - registered_scenarios

    if unregistered:
        pytest.fail(
            f"Found {len(unregistered)} scenario(s) not registered in SCENARIO_FACTORIES:\n"
            f"  {sorted(unregistered)}\n\n"
            f"Please add them to scenarios/scenario_registry.py:\n"
            f"  1. Import: from .{list(unregistered)[0]}.create_scenario import create_scenario as create_{list(unregistered)[0]}\n"
            f"  2. Register: SCENARIO_FACTORIES['{list(unregistered)[0]}'] = create_{list(unregistered)[0]}"
        )


def test_all_registered_scenarios_have_directories():
    """Test that every registered scenario has a corresponding directory."""
    scenario_dirs = get_scenario_directories()
    registered_scenarios = set(SCENARIO_FACTORIES.keys())

    # Find scenarios that are registered but have no directory
    missing_dirs = registered_scenarios - scenario_dirs

    if missing_dirs:
        pytest.fail(
            f"Found {len(missing_dirs)} scenario(s) in SCENARIO_FACTORIES without directories:\n"
            f"  {sorted(missing_dirs)}\n\n"
            f"Either create the scenario directory or remove from scenarios/scenario_registry.py"
        )


def test_all_registered_scenarios_are_callable():
    """Test that every registered scenario factory is callable."""
    for scenario_name, factory_func in SCENARIO_FACTORIES.items():
        assert callable(factory_func), (
            f"SCENARIO_FACTORIES['{scenario_name}'] is not callable. "
            f"Expected a function, got {type(factory_func)}"
        )


def test_all_registered_scenarios_can_be_loaded():
    """Test that every registered scenario can be instantiated without errors."""
    errors = []

    for scenario_name, factory_func in SCENARIO_FACTORIES.items():
        try:
            scenario_def = factory_func()
            # Basic validation that it returned a ScenarioDefinition-like object
            assert hasattr(scenario_def, "params_to_task"), (
                f"Scenario '{scenario_name}' missing params_to_task method"
            )
            assert hasattr(scenario_def, "suites"), (
                f"Scenario '{scenario_name}' missing suites attribute"
            )
        except Exception as e:
            errors.append(f"  - {scenario_name}: {e}")

    if errors:
        pytest.fail(f"Failed to load {len(errors)} scenario(s):\n" + "\n".join(errors))
