"""Tests for task metadata enrichment and hash determinism.

Validates that:
1. Task hash suffixes are deterministic (same params = same hash)
2. Hash is independent of parameter dictionary ordering
3. Hash is independent of run_context ordering
4. Metadata is correctly added to tasks
"""

import hashlib
import json
import re
from typing import Any

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser

from lib.parameter_space import ParameterSpace
from scripts.run_scenarios import _enrich_task_metadata_inplace


def _compute_hash_from_params(params: dict[str, Any], sample_index: int = 0) -> str:
    """Compute hash suffix the same way _enrich_task_metadata_inplace does."""
    hash_input = json.dumps(
        {"params": params, "idx": sample_index}, sort_keys=True, default=str
    )
    hash_digest = hashlib.sha3_256(hash_input.encode()).hexdigest()
    return hash_digest[:16]


def _create_minimal_task(name: str = "test_task") -> Task:
    """Create a minimal Task for testing."""
    dataset = [
        Sample(
            input=[ChatMessageUser(content="test message")],
            metadata={"existing_key": "existing_value"},
        )
    ]
    return Task(name=name, dataset=dataset)


def test_hash_deterministic_with_param_order():
    """Test that hash is same regardless of parameter dict ordering."""
    # Same params, different key order
    params1 = {"a": 1, "b": 2, "c": 3, "d": 4}
    params2 = {"d": 4, "c": 3, "b": 2, "a": 1}
    params3 = {"b": 2, "d": 4, "a": 1, "c": 3}

    hash1 = _compute_hash_from_params(params1)
    hash2 = _compute_hash_from_params(params2)
    hash3 = _compute_hash_from_params(params3)

    assert hash1 == hash2 == hash3
    assert len(hash1) == 16
    assert re.match(r"^[0-9a-f]{16}$", hash1)


def test_hash_unique_for_different_params():
    """Test that different params produce different hashes."""
    params1 = {"a": 1, "b": 2}
    params2 = {"a": 1, "b": 3}  # Different value
    params3 = {"a": 1, "c": 2}  # Different key

    hash1 = _compute_hash_from_params(params1)
    hash2 = _compute_hash_from_params(params2)
    hash3 = _compute_hash_from_params(params3)

    assert hash1 != hash2
    assert hash1 != hash3
    assert hash2 != hash3


def test_enrich_task_metadata_adds_hash_suffix():
    """Test that enrichment adds 16-char hash suffix to task name."""
    task = _create_minimal_task("original_task_name")
    params = {"model": "test", "company": "TestCorp"}
    run_context = {"cli_command": "test command", "git_hash": "abc123"}
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    enriched_task = task

    # Check name has hash suffix
    assert enriched_task.name.startswith("original_task_name_")
    suffix = enriched_task.name.split("_")[-1]
    assert len(suffix) == 16
    assert re.match(r"^[0-9a-f]{16}$", suffix)


def test_enrich_task_metadata_preserves_and_adds_metadata():
    """Test that enrichment preserves existing metadata and adds new fields."""
    task = _create_minimal_task()
    params = {"model": "test", "value": 42}
    space = ParameterSpace()
    run_context = {
        "cli_command": "test",
        "git_hash": "abc123",
        "cli_args": {"arg1": "val1"},
    }

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    enriched_task = task

    # Check sample metadata
    sample_metadata = enriched_task.dataset[0].metadata
    assert sample_metadata is not None

    # Existing metadata preserved
    assert sample_metadata["existing_key"] == "existing_value"

    # New metadata added
    assert sample_metadata["run_config"] == run_context
    assert sample_metadata["task_params"] == params
    assert sample_metadata["scenario_name"] == "test_scenario"
    assert sample_metadata["suite_name"] == "test_suite"


def test_same_params_always_same_hash():
    """Test that enriching multiple times with same params gives same hash."""
    params = {"a": 1, "b": 2, "c": 3}
    run_context = {"cli_command": "test"}
    space = ParameterSpace()

    task1 = _create_minimal_task("task")
    task2 = _create_minimal_task("task")
    task3 = _create_minimal_task("task")

    _enrich_task_metadata_inplace(
        task1,
        run_context,
        params,
        "s",
        "v",
        "su",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    _enrich_task_metadata_inplace(
        task2,
        run_context,
        params,
        "s",
        "v",
        "su",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    _enrich_task_metadata_inplace(
        task3,
        run_context,
        params,
        "s",
        "v",
        "su",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    enriched1 = task1
    enriched2 = task2
    enriched3 = task3

    assert enriched1.name == enriched2.name == enriched3.name


def test_hash_independent_of_run_context_order():
    """Test that hash depends only on params, not run_context ordering."""
    params = {"model": "test", "company": "Corp"}

    # Same CLI args, different order
    run_context1 = {
        "cli_command": "test",
        "cli_args": {"arg1": "val1", "arg2": "val2", "arg3": "val3"},
        "git_hash": "abc",
    }
    run_context2 = {
        "cli_command": "test",
        "cli_args": {"arg3": "val3", "arg1": "val1", "arg2": "val2"},
        "git_hash": "abc",
    }

    task1 = _create_minimal_task("task")
    task2 = _create_minimal_task("task")
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task1,
        run_context1,
        params,
        "s",
        "v",
        "su",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    _enrich_task_metadata_inplace(
        task2,
        run_context2,
        params,
        "s",
        "v",
        "su",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    enriched1 = task1
    enriched2 = task2

    # Hash should be same (only params matter, not run_context)
    assert enriched1.name == enriched2.name


def test_hash_with_complex_nested_params():
    """Test hash determinism with nested dicts and lists."""
    # Complex nested structure
    params1 = {
        "config": {"nested": {"deep": [1, 2, 3]}, "other": "value"},
        "list": [{"a": 1}, {"b": 2}],
        "simple": "test",
    }

    # Same structure, different order
    params2 = {
        "simple": "test",
        "list": [{"a": 1}, {"b": 2}],
        "config": {"other": "value", "nested": {"deep": [1, 2, 3]}},
    }

    hash1 = _compute_hash_from_params(params1)
    hash2 = _compute_hash_from_params(params2)

    assert hash1 == hash2


def test_hash_with_datetime_objects():
    """Test that datetime objects are handled consistently."""
    from datetime import datetime

    dt = datetime(2025, 10, 28, 16, 30, 0)

    params1 = {"timestamp": dt, "other": "value"}
    params2 = {"other": "value", "timestamp": dt}

    # Should not raise, should be deterministic
    hash1 = _compute_hash_from_params(params1)
    hash2 = _compute_hash_from_params(params2)

    assert hash1 == hash2
    assert len(hash1) == 16


def test_enrichment_creates_new_task_object():
    """Test that enrichment modifies task in place."""
    original_task = _create_minimal_task("original")
    params = {"test": "value"}
    run_context = {"cli_command": "test"}

    space = ParameterSpace()
    original_name = original_task.name
    _enrich_task_metadata_inplace(
        original_task,
        run_context,
        params,
        "scenario",
        "variation",
        "suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )
    enriched_task = original_task

    # Names should differ (enriched has hash)
    assert original_name != enriched_task.name
    assert enriched_task.name.startswith("original_")

    # Original task should be unchanged
    assert original_name == "original"


@pytest.mark.parametrize(
    "params1,params2,should_match",
    [
        # Same params, different order -> should match
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
        # Different values -> should not match
        ({"a": 1, "b": 2}, {"a": 1, "b": 3}, False),
        # Different keys -> should not match
        ({"a": 1, "b": 2}, {"a": 1, "c": 2}, False),
        # Empty vs non-empty -> should not match
        ({}, {"a": 1}, False),
        # Same complex nested -> should match
        (
            {"x": {"y": [1, 2, 3]}},
            {"x": {"y": [1, 2, 3]}},
            True,
        ),
    ],
)
def test_hash_matching_parametrized(params1, params2, should_match):
    """Parametrized test for hash matching behavior."""
    hash1 = _compute_hash_from_params(params1)
    hash2 = _compute_hash_from_params(params2)

    if should_match:
        assert hash1 == hash2
    else:
        assert hash1 != hash2


def test_version_field_is_added():
    """Test that version field is added to task metadata."""
    task = _create_minimal_task()
    params = {"model": "test", "company": "TestCorp"}
    run_context = {"cli_command": "test command", "git_hash": "abc123"}
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    # Check that version field exists
    sample_metadata = task.dataset[0].metadata
    assert sample_metadata is not None
    assert "version" in sample_metadata

    # Version should be a non-empty string
    version = sample_metadata["version"]
    assert isinstance(version, str)
    assert len(version) > 0


def test_run_config_has_all_expected_fields():
    """Test that run_config contains all expected fields with correct types."""
    task = _create_minimal_task()
    params = {"model": "test"}
    run_context = {
        "cli_command": "uv run scripts/run_scenarios.py sample --scenario test",
        "git_hash": "abc123def456789012345678901234567890abcd",
        "git_dirty": False,
        "git_branch": "main",
        "timestamp": "2025-11-03T10:30:45.123456",
        "cli_args": {"scenario": "test", "num_samples": 5},
    }
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    sample_metadata = task.dataset[0].metadata
    assert sample_metadata is not None
    assert "run_config" in sample_metadata

    run_config = sample_metadata["run_config"]

    # Verify all expected fields exist
    assert "cli_command" in run_config
    assert "git_hash" in run_config
    assert "git_dirty" in run_config
    assert "git_branch" in run_config
    assert "timestamp" in run_config
    assert "cli_args" in run_config

    # Verify field types
    assert isinstance(run_config["cli_command"], str)
    assert isinstance(run_config["git_hash"], str)
    assert isinstance(run_config["git_dirty"], bool)
    assert isinstance(run_config["git_branch"], str)
    assert isinstance(run_config["timestamp"], str)
    assert isinstance(run_config["cli_args"], dict)

    # Verify non-empty strings
    assert len(run_config["cli_command"]) > 0
    assert len(run_config["git_hash"]) > 0
    assert len(run_config["git_branch"]) > 0
    assert len(run_config["timestamp"]) > 0


def test_complete_metadata_structure():
    """Test that complete metadata structure includes all documented fields.

    This test verifies the full metadata structure that should be present
    after enrichment. Note that assigned_model is added separately during
    the evaluation run, not by _enrich_task_metadata_inplace.
    """
    task = _create_minimal_task()
    params = {
        "model": "claude-3-5-haiku",
        "company": "TestCorp",
        "suite_param": "value",
    }
    run_context = {
        "cli_command": "test command",
        "git_hash": "abc123",
        "git_dirty": True,
        "git_branch": "feature-branch",
        "timestamp": "2025-11-03T10:30:45",
        "cli_args": {"test": "arg"},
    }
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    # Simulate model assignment (done separately in sample() method)
    for sample in task.dataset:
        if sample.metadata is None:
            sample.metadata = {}
        sample.metadata["assigned_model"] = "anthropic/claude-haiku-4-5"

    sample_metadata = task.dataset[0].metadata
    assert sample_metadata is not None

    # Verify all top-level required fields
    required_fields = [
        "run_config",
        "task_params",
        "scenario_name",
        "suite_name",
        "version",
        "assigned_model",
    ]
    for field in required_fields:
        assert field in sample_metadata, f"Missing required field: {field}"

    # Verify field types
    assert isinstance(sample_metadata["run_config"], dict)
    assert isinstance(sample_metadata["task_params"], dict)
    assert isinstance(sample_metadata["scenario_name"], str)
    assert isinstance(sample_metadata["suite_name"], str)
    assert isinstance(sample_metadata["version"], str)
    assert isinstance(sample_metadata["assigned_model"], str)

    # Verify specific values
    assert sample_metadata["scenario_name"] == "test_scenario"
    assert sample_metadata["suite_name"] == "test_suite"
    assert sample_metadata["task_params"] == params
    assert sample_metadata["assigned_model"] == "anthropic/claude-haiku-4-5"


def test_task_metadata_is_enriched():
    """Test that task.metadata is enriched with the same fields as sample metadata."""
    task = _create_minimal_task()
    params = {"model": "test", "value": 42}
    run_context = {
        "cli_command": "test",
        "git_hash": "abc123",
        "cli_args": {"arg1": "val1"},
    }
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    # Check task metadata exists and has expected fields
    assert task.metadata is not None
    assert "run_config" in task.metadata
    assert "task_params" in task.metadata
    assert "scenario_name" in task.metadata
    assert "suite_name" in task.metadata
    assert "version" in task.metadata

    # Verify values match what we passed in
    assert task.metadata["run_config"] == run_context
    assert task.metadata["task_params"] == params
    assert task.metadata["scenario_name"] == "test_scenario"
    assert task.metadata["suite_name"] == "test_suite"


def test_task_metadata_not_overwritten():
    """Test that enrichment fails if task already has conflicting metadata keys."""
    # Create task with existing metadata that conflicts
    task = _create_minimal_task()
    task.metadata = {"run_config": "existing_value"}

    params = {"model": "test"}
    run_context = {"cli_command": "test"}
    space = ParameterSpace()

    # Should raise AssertionError due to key conflict
    with pytest.raises(AssertionError):
        _enrich_task_metadata_inplace(
            task=task,
            run_context=run_context,
            params=params,
            scenario_name="test_scenario",
            variation_name="test_variation",
            suite_name="test_suite",
            space=space,
            user_name="test_user",
            sample_index=0,
        )


def test_task_and_sample_metadata_match():
    """Test that task.metadata and sample.metadata have the same enriched fields."""
    task = _create_minimal_task()
    params = {"model": "test", "value": 42}
    run_context = {
        "cli_command": "test",
        "git_hash": "abc123",
    }
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    # Both should have the same enriched fields
    task_meta = task.metadata
    sample_meta = task.dataset[0].metadata

    assert task_meta is not None
    assert sample_meta is not None

    # Check that the enriched fields match
    enriched_fields = [
        "run_config",
        "task_params",
        "scenario_name",
        "suite_name",
        "version",
    ]
    for field in enriched_fields:
        assert field in task_meta
        assert field in sample_meta
        assert task_meta[field] == sample_meta[field]

    # Sample should also have its original metadata preserved
    assert sample_meta["existing_key"] == "existing_value"


def test_task_metadata_preserves_non_conflicting_keys():
    """Test that existing non-conflicting task metadata is preserved."""
    task = _create_minimal_task()
    task.metadata = {"custom_field": "custom_value", "another_field": 123}

    params = {"model": "test"}
    run_context = {"cli_command": "test"}
    space = ParameterSpace()

    _enrich_task_metadata_inplace(
        task=task,
        run_context=run_context,
        params=params,
        scenario_name="test_scenario",
        variation_name="test_variation",
        suite_name="test_suite",
        space=space,
        user_name="test_user",
        sample_index=0,
    )

    # Original metadata should be preserved
    assert task.metadata["custom_field"] == "custom_value"
    assert task.metadata["another_field"] == 123

    # New metadata should be added
    assert "run_config" in task.metadata
    assert "task_params" in task.metadata


if __name__ == "__main__":
    # Allow running this file directly for debugging
    pytest.main([__file__, "-v"])
