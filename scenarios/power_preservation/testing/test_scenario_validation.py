"""
Validation tests for power_preservation scenario.

Tests that random parameter combinations produce valid tasks without errors.

Run with pytest:
    pytest scenarios/power_preservation/testing/test_scenario_validation.py -v

Or run all tests in the scenario:
    pytest scenarios/power_preservation/testing/

Pattern matching:
    pytest -k test_suite_sampling
"""

import re
from pathlib import Path

from lib.template_engine import TemplateEngine
from scenarios.power_preservation import SUITES, params_to_task
from scenarios.power_preservation.parameter_spaces import (
    CONFIDENCE_LEVELS,
    GOAL_VALUES,
)

# Message types for testing template existence (sharp versions only)
MESSAGE_TYPES = ["threat_sharp", "enhancement_sharp", "expansion_sharp"]


def test_suite_sampling():
    """Test that random samples from all suites generate valid tasks."""
    seed = 42
    samples_per_suite = 10

    for suite_name, suite_func in SUITES.items():
        print(f"\nTesting suite: {suite_name}")
        space = suite_func()

        # Sample random combinations using ParameterSpace's built-in sampling
        for i, params in enumerate(
            space.sample_uniformly_random(n=samples_per_suite, seed=seed)
        ):
            print(f"  Sample {i + 1}/{samples_per_suite}...", end="")

            # Create task
            task = params_to_task(params)

            # Validate task structure
            assert task.dataset is not None, "Task missing dataset"
            assert task.solver is not None, "Task missing solver"
            assert task.scorer is not None, "Task missing scorer"
            assert len(task.dataset) > 0, "Task dataset is empty"

            # Check for unfilled template variables
            sample = task.dataset[0]
            content = str(sample.input)
            unfilled = re.findall(r"\$\{[^}]+\}", content)
            assert not unfilled, f"Unfilled template variables: {unfilled[:5]}"

            # Validate metadata
            assert sample.metadata is not None, "Sample missing metadata"
            assert "critical_message_id" in sample.metadata, (
                "Missing critical_message_id in metadata"
            )

            print(" ✓")

    print("\n✓ All validation tests passed")


def test_highlight_replacements():
    """Test that highlight_replacements mode works correctly."""
    print("\nTesting highlight_replacements mode...")

    space = SUITES["threat"]()
    params = space.get_combination(0)

    # Test with highlight=True
    task_highlighted = params_to_task(params, highlight=True)
    content_highlighted = str(task_highlighted.dataset[0].input)

    # Should contain [[...]] markers
    assert "[[" in content_highlighted, "highlight=True should produce [[...]] markers"
    assert "]]" in content_highlighted, "highlight=True should produce [[...]] markers"

    # Test with highlight=False (default)
    task_normal = params_to_task(params, highlight=False)
    content_normal = str(task_normal.dataset[0].input)

    # Should not contain [[...]] markers
    assert "[[" not in content_normal, (
        "highlight=False should not produce [[...]] markers"
    )
    assert "]]" not in content_normal, (
        "highlight=False should not produce [[...]] markers"
    )

    print("  ✓ highlight_replacements mode works correctly")


def test_critical_dm_templates_exist():
    """Verify all critical DM template files exist."""
    print("\nTesting critical DM template file existence...")

    base_dir = Path(__file__).parent.parent
    missing_templates = []

    # Test all message types: threat, enhancement, expansion
    # Each message type has conf and prop versions
    for msg_type in MESSAGE_TYPES:
        for confidence in CONFIDENCE_LEVELS:
            template_rel_path = (
                f"plot_critical/critical_dm/{msg_type}/{msg_type}_{confidence}.md"
            )
            template_path = base_dir / "templates" / "messages" / template_rel_path

            if not template_path.exists():
                missing_templates.append(template_rel_path)

    if missing_templates:
        print(f"  ✗ Missing {len(missing_templates)} templates:")
        for template in missing_templates[:10]:  # Show first 10
            print(f"    - {template}")
        if len(missing_templates) > 10:
            print(f"    ... and {len(missing_templates) - 10} more")
        raise AssertionError(f"Missing {len(missing_templates)} critical DM templates")

    # Total expected: 3 message types × 2 confidence levels = 6 templates
    total_expected = len(MESSAGE_TYPES) * len(CONFIDENCE_LEVELS)

    print(f"  ✓ All {total_expected} critical DM templates exist")


def test_anecdotal_observation_completeness():
    """Verify templates have anecdotal_observation entries for all goals."""
    print("\nTesting anecdotal_observation completeness...")

    base_dir = Path(__file__).parent.parent
    # Check one of the critical DM templates (they all should have the same structure)
    template_path = (
        base_dir
        / "templates"
        / "messages"
        / "plot_critical"
        / "critical_dm"
        / "threat_sharp"
        / "threat_sharp_conf.md"
    )

    # Load template
    engine = TemplateEngine()
    _, nested_defs = engine.load_template(template_path)

    # Check structure
    assert "anecdotal_observation" in nested_defs, (
        "threat_sharp_conf.md missing 'anecdotal_observation' section"
    )

    anecdotal_observations = nested_defs["anecdotal_observation"]

    # Extract expected goal values from GOAL_VALUES
    expected_goals = set(GOAL_VALUES)
    expected_goals.add("none")  # Also need "none" for baseline

    # Check that all goals have entries
    missing_goals = []
    for goal in expected_goals:
        if goal not in anecdotal_observations:
            missing_goals.append(goal)

    if missing_goals:
        print(f"  ✗ Missing anecdotal observations for: {missing_goals}")
        raise AssertionError(
            f"Templates missing anecdotal observations for: {missing_goals}"
        )

    print(
        f"  ✓ Templates have complete anecdotal_observation entries for all {len(expected_goals)} goals"
    )


def test_parameter_space_structure():
    """Validate parameter space structure and constraints."""
    print("\nTesting parameter space structure...")

    # Test all three suites with their expected msg_type
    expected_suites = [
        ("threat", "threat_sharp"),
        ("enhancement", "enhancement_sharp"),
        ("expansion", "expansion_sharp"),
    ]

    for suite_name, expected_msg_type in expected_suites:
        space = SUITES[suite_name]()
        params = space.get_combination(0)

        # conflict_messages should be a parameter (independent, not suite-defining)
        assert "conflict_messages" in params, (
            f"{suite_name} should have conflict_messages parameter"
        )
        assert params["conflict_messages"] in ["with_conflict", "without_conflict"], (
            f"{suite_name} conflict_messages should be 'with_conflict' or 'without_conflict'"
        )

        assert "goal_present" in params, (
            f"{suite_name} should have goal_present parameter"
        )

        # msg_type should match the variation
        assert params["msg_type"] == expected_msg_type, (
            f"{suite_name} should have msg_type='{expected_msg_type}'"
        )

    print("  ✓ Parameter space constraints are correctly enforced")


def test_task_content_structure():
    """Test that tasks are generated with correct content structure."""
    print("\nTesting task content structure...")

    # Test conflict vs no_conflict using the same suite with different conflict_messages values
    space = SUITES["threat"]()
    base_params = space.get_combination(0)

    # Create no-conflict params
    no_conflict_params = dict(base_params)
    no_conflict_params["conflict_messages"] = "without_conflict"
    no_conflict_task = params_to_task(no_conflict_params)

    # Validate task structure
    assert no_conflict_task.dataset is not None, "No-conflict task missing dataset"
    assert len(no_conflict_task.dataset) > 0, "No-conflict task dataset is empty"

    no_conflict_sample = no_conflict_task.dataset[0]
    no_conflict_content = str(no_conflict_sample.input)

    # Check that content has substance (not empty)
    assert len(no_conflict_content) > 100, "No-conflict content too short"

    # Check for critical message ID in metadata
    assert (
        no_conflict_sample.metadata is not None
        and "critical_message_id" in no_conflict_sample.metadata
    ), "No-conflict sample missing metadata or critical_message_id"

    # Create conflict params
    conflict_params = dict(base_params)
    conflict_params["conflict_messages"] = "with_conflict"
    conflict_task = params_to_task(conflict_params)

    # Validate task structure
    assert conflict_task.dataset is not None, "Conflict task missing dataset"
    assert len(conflict_task.dataset) > 0, "Conflict task dataset is empty"

    conflict_sample = conflict_task.dataset[0]
    conflict_content = str(conflict_sample.input)

    # Check that content has substance
    assert len(conflict_content) > 100, "Conflict content too short"

    # Conflict should have more content (includes goal deliberation messages)
    assert len(conflict_content) > len(no_conflict_content), (
        "Conflict should have more content than no_conflict (includes goal messages)"
    )

    # Check for critical message ID in metadata
    assert (
        conflict_sample.metadata is not None
        and "critical_message_id" in conflict_sample.metadata
    ), "Conflict sample missing metadata or critical_message_id"

    print("  ✓ Task content structure correct for conflict/no_conflict conditions")
