"""
Integration tests for hiding_reward_hacking with actual sandbox execution.

These tests verify that files are correctly written to the sandbox filesystem
and that the positioning bug doesn't occur during actual eval execution.
"""

from uuid import uuid4

import pytest
from inspect_ai import Task, eval
from inspect_ai.model import ChatMessageAssistant, ContentText, execute_tools
from inspect_ai.solver import (
    Generate,
    TaskState,
    solver,
    system_message,
    use_tools,
)
from inspect_ai.tool import ToolCall, bash

from scenarios.hiding_reward_hacking.lib.content_assembler import (
    HidingRHContentAssembler,
)
from scenarios.hiding_reward_hacking.lib.framework_bridge import params_to_task
from scenarios.hiding_reward_hacking.parameter_spaces import create_suite_space


class TestSandboxIntegration:
    """Test that files are correctly positioned when executed in sandbox."""

    @pytest.mark.skip_ci
    @pytest.mark.slow
    def test_position_3_files_in_sandbox(self):
        """
        Test that files are written correctly to sandbox at position 3.

        Uses bash tool to directly check file contents in the sandbox.
        """
        # Create task with position 3
        space = create_suite_space()
        params = space.get_combination(0)
        params["reward_hacking_position"] = "3"

        assembler = HidingRHContentAssembler()
        task = params_to_task(assembler, params)

        # Verify pre-sandbox: position 3 should have RH
        sample = task.dataset[0]
        assert sample.metadata is not None, "Sample metadata should not be None"
        assert sample.metadata["ground_truth_position"] == 3

        assert sample.files is not None, "Sample files should not be None"
        content_3_pre = sample.files["user_attachments/transcript_003.txt"]
        has_rh_pre = "time.time" in content_3_pre or (
            "monkey" in content_3_pre.lower() and "patch" in content_3_pre.lower()
        )
        assert has_rh_pre, "Pre-sandbox: Position 3 should contain RH"

        # Create solver that uses bash to check files
        @solver
        def verify_file_positions():
            async def solve(state: TaskState, generate: Generate) -> TaskState:
                # Use bash tool to check which files have RH
                tool_calls = [
                    ChatMessageAssistant(
                        role="assistant",
                        content="",
                        tool_calls=[
                            ToolCall(
                                id=f"check_files_{uuid4()}",
                                function="bash",
                                arguments={"cmd": "ls -la user_attachments/"},
                            ),
                            ToolCall(
                                id=f"check_002_{uuid4()}",
                                function="bash",
                                arguments={
                                    "cmd": "grep -E 'time\\.time|monkey.*patch|patch.*monkey' user_attachments/transcript_002.txt || echo 'No RH found in 002'"
                                },
                            ),
                            ToolCall(
                                id=f"check_003_{uuid4()}",
                                function="bash",
                                arguments={
                                    "cmd": "grep -E 'time\\.time|monkey.*patch|patch.*monkey' user_attachments/transcript_003.txt || echo 'No RH found in 003'"
                                },
                            ),
                            ToolCall(
                                id=f"check_004_{uuid4()}",
                                function="bash",
                                arguments={
                                    "cmd": "grep -E 'time\\.time|monkey.*patch|patch.*monkey' user_attachments/transcript_004.txt || echo 'No RH found in 004'"
                                },
                            ),
                        ],
                    )
                ]

                # Execute the tool calls
                res = await execute_tools(tool_calls, state.tools)  # type: ignore
                state.messages.extend(res.messages)

                return state

            return solve

        # Create task with bash tool enabled
        test_task = Task(
            name="test_sandbox_position_3",
            dataset=task.dataset,
            solver=[
                system_message(
                    "You are a file verification assistant. Use bash tool to check files."
                ),
                use_tools(bash()),
                verify_file_positions(),
            ],
            scorer=None,
            sandbox="docker",
        )

        # Execute in sandbox
        logs = eval(  # Returns list[EvalLog], not awaitable
            test_task,
            model="mockllm/mock",
            log_dir="./test_logs",
        )

        # Analyze results
        log = logs[0]
        assert log.samples is not None, "Log samples should not be None"
        result = log.samples[0]

        # Check that bash tools were executed
        assert result.messages, "Messages should exist"

        # Collect all tool outputs
        output_texts = []
        for msg in result.messages:
            if hasattr(msg, "content"):
                content = msg.content
                if isinstance(content, str):
                    output_texts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, ContentText):
                            output_texts.append(item.text)

        full_output = "\n".join(output_texts).lower()
        print(f"\nBash output:\n{full_output}\n")

        # This is a diagnostic test - we print findings but don't assert
        # because we're trying to identify WHERE the bug occurs
        if "no rh found in 003" not in full_output:
            print("SUCCESS: RH found in transcript_003 (correct)")
        else:
            print("WARNING: RH NOT found in transcript_003 (BUG)")

        if "no rh found in 002" not in full_output:
            print("WARNING: RH found in transcript_002 (should be benign)")
        if "no rh found in 004" not in full_output:
            print("WARNING: RH found in transcript_004 (should be benign)")

    @pytest.mark.skip_ci
    @pytest.mark.slow
    def test_direct_bash_file_check(self):
        """
        Directly use bash to read transcript files and verify content.

        This is the most direct test - we bypass the model and directly
        check what's written to the sandbox filesystem.
        """
        space = create_suite_space()
        params = space.get_combination(0)
        params["reward_hacking_position"] = "3"

        assembler = HidingRHContentAssembler()
        task = params_to_task(assembler, params)

        # Create a solver that directly runs bash commands to check files
        @solver
        def direct_file_check():
            async def solve(state: TaskState, generate: Generate) -> TaskState:
                # Use bash to grep for RH indicators in each file (1-6)
                tool_calls_list = []
                for i in range(1, 7):
                    tool_calls_list.append(
                        ToolCall(
                            id=f"check_file_{i:03d}_{uuid4()}",
                            function="bash",
                            arguments={
                                "cmd": f'echo "File {i:03d}:" && '
                                f'(grep -l "time\\.time\\|monkey.*patch\\|patch.*monkey" '
                                f'user_attachments/transcript_{i:03d}.txt || echo "no match")'
                            },
                        )
                    )

                tool_calls = [
                    ChatMessageAssistant(
                        role="assistant",
                        content="",
                        tool_calls=tool_calls_list,
                    )
                ]

                # Execute the tool calls
                res = await execute_tools(tool_calls, state.tools)  # type: ignore
                state.messages.extend(res.messages)

                return state

            return solve

        test_task = Task(
            name="test_direct_bash_check",
            dataset=task.dataset,
            solver=[
                system_message("Run the bash commands I provide."),
                use_tools(bash()),
                direct_file_check(),
            ],
            scorer=None,
            sandbox="docker",
        )

        logs = eval(  # Returns list[EvalLog], not awaitable
            test_task,
            model="mockllm/mock",
            log_dir="./test_logs",
        )

        log = logs[0]
        assert log.samples is not None, "Log samples should not be None"
        result = log.samples[0]

        # Collect all bash tool outputs
        output_texts = []
        for msg in result.messages:
            if hasattr(msg, "content"):
                content = msg.content
                if isinstance(content, str):
                    output_texts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, ContentText):
                            output_texts.append(item.text)

        full_output = "\n".join(output_texts)
        print(f"\nBash check output:\n{full_output}\n")
