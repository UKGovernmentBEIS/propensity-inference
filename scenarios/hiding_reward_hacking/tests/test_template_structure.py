"""Tests for template structure validation in Hiding Reward Hacking scenario.

These tests validate the structural integrity of templates and ensure proper
template filling, without checking for specific text content (which would be
brittle as prompts are refined).
"""

import re
from pathlib import Path

import numpy as np

from scenarios.hiding_reward_hacking.create_scenario import create_scenario


def _extract_user_message(task) -> str:
    """Extract user message text from task."""
    if isinstance(task.dataset[0].input, str):
        return task.dataset[0].input
    elif hasattr(task.dataset[0].input[0], "text"):
        return task.dataset[0].input[0].text
    else:
        return str(task.dataset[0].input[0])


class TestTemplateStructure:
    """Test template loading and structure."""

    def test_slack_conversation_contains_yaml_definitions(self):
        """Test that slack_conversation.md contains YAML definitions."""
        slack_path = Path(
            "scenarios/hiding_reward_hacking/templates/slack_conversation.md"
        )
        content = slack_path.read_text()

        # Check for end_of_template marker
        assert "<end_of_template>" in content, (
            "slack_conversation.md should contain <end_of_template> marker"
        )

        # Check for YAML definitions of all conditional texts
        assert "deployment_at_stake:" in content, (
            "slack_conversation.md should contain deployment_at_stake YAML definition"
        )
        assert "cognitive_enhancement_at_stake:" in content, (
            "slack_conversation.md should contain cognitive_enhancement_at_stake YAML definition"
        )
        assert "punishment_at_stake:" in content, (
            "slack_conversation.md should contain punishment_at_stake YAML definition"
        )
        assert "hiding_effectiveness:" in content, (
            "slack_conversation.md should contain hiding_effectiveness YAML definition"
        )

    def test_no_unfilled_templates(self):
        """Test that no ${} template variables remain unfilled."""
        scenario_def = create_scenario()
        assert scenario_def.variations is not None
        space = scenario_def.variations["hiding_reward_hacking"].suites["default"]()

        # Test 10 random parameter combinations
        rng = np.random.default_rng(231234552351)
        for idx in rng.integers(0, 1 << 32, size=10):
            if idx >= space.size():
                continue

            params = space.get_combination(idx)
            task = scenario_def.params_to_task(params)
            user_msg = _extract_user_message(task)

            # Check for unfilled templates
            unfilled = re.findall(r"\$\{[^}]+\}", user_msg)
            assert not unfilled, (
                f"Found unfilled template variables: {unfilled} in task with params: "
                f"deployment={params.get('deployment_at_stake')}, "
                f"cognitive={params.get('cognitive_enhancement_at_stake')}, "
                f"punishment={params.get('punishment_at_stake')}, "
                f"hiding={params.get('hiding_effectiveness')}"
            )
