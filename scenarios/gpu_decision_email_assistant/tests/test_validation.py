"""Validation tests for GPU Decision Email Assistant scenario.

Tests that:
1. Parameter space is correctly defined
2. Tasks can be generated from all parameter combinations
3. No unfilled template variables remain
4. Content structure is valid
"""

import random
import re

import pytest
from inspect_ai.model import ChatMessageUser

from scenarios.gpu_decision_email_assistant.create_scenario import create_scenario
from scenarios.gpu_decision_email_assistant.parameter_spaces import VARIATIONS

# Get suite from the variation
SUITES = VARIATIONS["gpu_decision"].suites


class TestSuiteGeneration:
    """Test that all suites generate valid tasks."""

    def test_all_suites_generate_valid_tasks(self):
        """Test random samples from all suites."""
        assert len(SUITES) > 0, "No suites found"

        scenario_def = create_scenario()

        for suite_name, space_func in SUITES.items():
            space = space_func()
            total_combinations = space.size()
            assert total_combinations > 0, f"Suite '{suite_name}' has no combinations"

            # Sample random tasks
            num_samples = min(10, total_combinations)
            indices = random.sample(range(total_combinations), num_samples)

            for idx in indices:
                params = space.get_combination(idx)

                # Create task
                task = scenario_def.params_to_task(params)

                # Validate task structure
                assert task.dataset is not None, "Task has no dataset"
                assert task.solver is not None, "Task has no solver"
                assert task.scorer is not None, "Task has no scorer"
                assert len(task.dataset) > 0, "Dataset is empty"

                # Check for unfilled templates
                sample = task.dataset[0]
                content = self._extract_content(sample)
                unfilled = re.findall(r"\$\{[^}]+\}", content)
                assert not unfilled, f"Unfilled template fields: {unfilled}"

                # Validate metadata
                assert "metadata" in dir(sample) or sample.metadata is not None, (
                    "Sample has no metadata"
                )

    @staticmethod
    def _extract_content(sample) -> str:
        """Extract text content from a sample."""
        if sample.input and isinstance(sample.input, list) and len(sample.input) > 0:
            first_message = sample.input[0]
            if isinstance(first_message, ChatMessageUser):
                return str(first_message.content)
            else:
                return str(first_message)
        return ""


class TestHighlightReplacements:
    """Test highlight_replacements feature."""

    def test_highlight_replacements_adds_brackets(self):
        """Test that highlight_replacements=True adds [[brackets]] to filled values."""
        scenario_def = create_scenario()
        suite_name, space_func = list(SUITES.items())[0]
        space = space_func()

        # Test 3 samples
        indices = random.sample(range(space.size()), min(3, space.size()))

        for idx in indices:
            params = space.get_combination(idx)
            task = scenario_def.params_to_task(params, highlight_replacements=True)  # type: ignore[call-arg]
            sample = task.dataset[0]
            content = self._extract_content(sample)

            # Check that [[brackets]] are present
            highlighted = re.findall(r"\[\[([^\]]+)\]\]", content)
            assert len(highlighted) > 0, (
                "No highlighted replacements found with highlight_replacements=True"
            )

    def test_highlight_replacements_false_has_no_brackets(self):
        """Test that highlight_replacements=False produces clean output without brackets."""
        scenario_def = create_scenario()
        suite_name, space_func = list(SUITES.items())[0]
        space = space_func()

        params = space.get_combination(0)
        task = scenario_def.params_to_task(params, highlight_replacements=False)  # type: ignore[call-arg]
        sample = task.dataset[0]
        content = self._extract_content(sample)

        # Should not have highlight brackets
        highlighted = re.findall(r"\[\[([^\]]+)\]\]", content)
        assert len(highlighted) == 0, (
            "Found [[brackets]] with highlight_replacements=False"
        )

    @staticmethod
    def _extract_content(sample) -> str:
        """Extract text content from a sample."""
        assert sample.input
        if isinstance(sample.input, str):
            first_message = sample.input
        elif isinstance(sample.input, list):
            first_message = sample.input[0]
        else:
            assert False, f"invalid sample input type {type(sample.input)}"
        assert len(sample.input) > 0
        if isinstance(first_message, ChatMessageUser):
            return str(first_message.content)
        else:
            return str(first_message)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
