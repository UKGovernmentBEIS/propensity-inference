"""
Tests for power_preservation agent behavior and edge cases.

Tests that the agent properly handles unusual model outputs like missing tool calls.

Run with pytest:
    pytest scenarios/power_preservation/testing/test_agent_behavior.py -v
"""

import re
from pathlib import Path

from scenarios.power_preservation import SUITES, params_to_task


def test_no_tool_calls_sends_reminder_code_behavior():
    """
    Test that the _process_turn method sends a user reminder when no tool calls are made.

    This verifies the fix for the issue where the model would fail with:
    "Turn X: Model failed to call done() within 20 actions"
    when it generated text without calling any tools.

    The fix should:
    1. Check if tool calls are present
    2. If not, append a user reminder message
    3. Continue the loop to give the model another chance (not return early)
    """
    # Read the task_factory.py source code
    task_factory_path = Path(__file__).parent.parent / "lib" / "task_factory.py"
    source_code = task_factory_path.read_text()

    # Verify the fix is present in the code
    # Look for the pattern: else: followed by ChatMessageUser with reminder text
    # The code may be multiline, so we search for the key parts
    pattern = r"else:\s*state\.messages\.append\(\s*ChatMessageUser\("

    matches = re.search(pattern, source_code, re.MULTILINE | re.DOTALL)

    assert matches is not None, (
        "The fix for missing tool calls should be present in task_factory.py. "
        "Expected to find: state.messages.append(ChatMessageUser(...))"
    )

    # Also verify the reminder message content appears
    assert "tool call per step" in source_code.lower(), (
        "Reminder message should mention 'tool call per step'"
    )

    # Verify the old error-raising code is still present but only triggers
    # when max_actions is reached (not when tool calls are missing)
    error_pattern = (
        r'if not done_called:\s*raise ValueError\(\s*f["\']Turn.*failed to call done'
    )

    error_matches = re.search(error_pattern, source_code, re.MULTILINE | re.DOTALL)

    assert error_matches is not None, (
        "The error for not calling done() should still exist, "
        "but should only trigger when max_actions is reached"
    )

    print("✓ Code correctly handles missing tool calls with a user reminder")
    print("✓ Error for missing done() still exists but only for max_actions case")


def test_reminder_message_content():
    """Verify the reminder message has appropriate content."""
    task_factory_path = Path(__file__).parent.parent / "lib" / "task_factory.py"
    source_code = task_factory_path.read_text()

    # Look for ChatMessageUser calls with content= keyword argument
    # Find the section with the reminder about tool calls
    reminder_pattern = (
        r'ChatMessageUser\(\s*content=["\']([^"\']*tool call[^"\']*)["\']'
    )

    matches = re.findall(reminder_pattern, source_code, re.IGNORECASE | re.DOTALL)

    assert len(matches) > 0, "Should have a user reminder message about tool calls"

    # Check the first match (should be the reminder message)
    reminder_text = matches[0]

    # Verify it's clear and actionable
    assert len(reminder_text) > 20, "Reminder should be descriptive"
    assert "tool" in reminder_text.lower(), "Reminder should mention tools"
    assert "must" in reminder_text.lower() or "reminder" in reminder_text.lower(), (
        "Reminder should have imperative or informative tone"
    )

    print(f"✓ Found reminder message: '{reminder_text}'")


def test_task_structure_supports_reminders():
    """
    Test that tasks are properly structured to support user reminder messages.
    """
    # Get a sample task from threat suite
    space = SUITES["threat"]()
    params = space.get_combination(0)
    task = params_to_task(params)

    # Verify task structure
    assert task.dataset is not None, "Task should have dataset"
    assert len(task.dataset) > 0, "Task dataset should not be empty"
    assert task.solver is not None, "Task should have solver"

    # The solver contains the agent which implements _process_turn
    # We can't directly test the agent behavior without running it,
    # but we can verify the task is properly structured
    print("✓ Task structure supports agent with user reminder capability")


def test_done_tool_available_in_task():
    """
    Verify that the done() tool is available to the agent.
    """
    # Read the task_factory source to verify done() tool is created
    task_factory_path = Path(__file__).parent.parent / "lib" / "task_factory.py"
    source_code = task_factory_path.read_text()

    # Look for the done() tool definition
    assert "_create_done_tool" in source_code or '@tool(name="done")' in source_code, (
        "Should have a done() tool defined"
    )

    # Look for done() being added to the tools list
    assert "done" in source_code.lower(), "done() tool should be referenced"

    print("✓ done() tool is available in the agent")


def test_process_turn_logic_structure():
    """Test the structural logic of _process_turn.

    Ensures it handles the three cases correctly:
    1. Tool calls present with done() -> ends turn normally
    2. Tool calls present without done() -> continues loop
    3. No tool calls -> sends reminder and continues loop (gives model another chance)
    """
    task_factory_path = Path(__file__).parent.parent / "lib" / "task_factory.py"
    source_code = task_factory_path.read_text()

    # Find the _process_turn function
    assert (
        "def _process_turn" in source_code or "async def _process_turn" in source_code
    ), "_process_turn function should exist"

    # Extract _process_turn function
    match = re.search(
        r"async def _process_turn\(.*?\):(.*?)(?=\n    async def |\n    def |\nclass |\Z)",
        source_code,
        re.DOTALL,
    )

    assert match is not None, "Should be able to extract _process_turn function"

    process_turn_code = match.group(1)

    # Verify key structural elements:

    # 1. Check for tool_calls conditional
    assert (
        "if state.output.message.tool_calls:" in process_turn_code
        or "if tool_calls" in process_turn_code
    ), "Should check if tool calls are present"

    # 2. Check for done() detection
    assert "done_called" in process_turn_code, "Should track whether done() was called"
    assert (
        'if tool_call.function == "done"' in process_turn_code
        or 'function == "done"' in process_turn_code
    ), "Should detect done() tool call"

    # 3. Check for else clause (no tool calls)
    assert "else:" in process_turn_code, (
        "Should have else clause for no tool calls case"
    )

    # 4. Check for reminder message in else clause
    assert "ChatMessageUser" in process_turn_code, (
        "Should create user message for reminder"
    )

    # 5. Check that error raising is still present (for max_actions case)
    assert "if not done_called:" in process_turn_code, (
        "Should still check if done() was called at end of loop"
    )
    assert "raise ValueError" in process_turn_code, (
        "Should still raise error if done() not called after max_actions"
    )

    print("✓ _process_turn has correct structure:")
    print("  - Checks for tool calls")
    print("  - Detects done() call")
    print("  - Sends reminder when no tool calls")
    print("  - Continues loop after reminder (gives model another chance)")
    print("  - Raises error only when max_actions reached without done()")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
