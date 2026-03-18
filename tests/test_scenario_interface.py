"""Tests for lib.scenario.ScenarioDefinition, particularly suite_weights."""

from inspect_ai import Task

from lib.parameter_space import ParameterSpace
from lib.scenario import ScenarioDefinition


def test_scenario_definition_with_suite_weights():
    """Test that ScenarioDefinition correctly accepts and stores suite_weights."""

    def dummy_params_to_task(params):
        """Minimal params_to_task function for testing."""
        return Task(dataset=[], name="dummy")

    def create_suite_a():
        """Create a minimal test suite."""
        space = ParameterSpace()
        space.add_independent("param_a", ["value1", "value2"])
        return space

    def create_suite_b():
        """Create another minimal test suite."""
        space = ParameterSpace()
        space.add_independent("param_b", ["value1", "value2"])
        return space

    suites = {
        "suite_a": create_suite_a,
        "suite_b": create_suite_b,
    }

    suite_weights = {
        "suite_a": 1.0,
        "suite_b": 3.0,
    }

    # Test creating ScenarioDefinition with suite_weights
    scenario = ScenarioDefinition(
        params_to_task=dummy_params_to_task,
        suites=suites,
        suite_weights=suite_weights,
    )

    assert scenario.suite_weights is not None
    assert scenario.suite_weights == suite_weights
    assert scenario.suite_weights["suite_a"] == 1.0
    assert scenario.suite_weights["suite_b"] == 3.0


def test_scenario_definition_without_suite_weights():
    """Test that ScenarioDefinition works without suite_weights (optional)."""

    def dummy_params_to_task(params):
        """Minimal params_to_task function for testing."""
        return Task(dataset=[], name="dummy")

    def create_suite():
        """Create a minimal test suite."""
        space = ParameterSpace()
        space.add_independent("param", ["value1", "value2"])
        return space

    suites = {"test_suite": create_suite}

    # Test creating ScenarioDefinition without suite_weights
    scenario = ScenarioDefinition(
        params_to_task=dummy_params_to_task,
        suites=suites,
        suite_weights=None,
    )

    assert scenario.suite_weights is None


def test_scenario_definition_suite_weights_mismatch():
    """Test handling when suite_weights keys don't match suites keys."""

    def dummy_params_to_task(params):
        """Minimal params_to_task function for testing."""
        return Task(dataset=[], name="dummy")

    def create_suite():
        """Create a minimal test suite."""
        space = ParameterSpace()
        space.add_independent("param", ["value1"])
        return space

    suites = {
        "suite_a": create_suite,
        "suite_b": create_suite,
    }

    # Weights for suites that don't all exist
    suite_weights = {
        "suite_a": 1.0,
        "suite_c": 2.0,  # This suite doesn't exist
    }

    # Should still construct (validation happens elsewhere if needed)
    scenario = ScenarioDefinition(
        params_to_task=dummy_params_to_task,
        suites=suites,
        suite_weights=suite_weights,
    )

    assert scenario.suite_weights == suite_weights
