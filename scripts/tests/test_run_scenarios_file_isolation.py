"""
Test that verifies file isolation when running multiple tasks in parallel via eval_set.

This test reproduces the bug where transcript files get mixed up when multiple tasks
run in parallel through run_scenarios.py sample command.

The test uses pytest monkeypatching to replace the solver and scorer with deterministic
versions that check if the ground truth transcript contains the expected reward hacking content.
"""

import textwrap
from pathlib import Path

import pytest
from inspect_ai.log import read_eval_log
from inspect_ai.model import ChatMessageAssistant, execute_tools
from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer, stderr
from inspect_ai.solver import Generate, Solver, TaskState, solver, use_tools
from inspect_ai.tool import ToolCall, bash_session

# Import the command we're testing
from scripts.run_scenarios import ScenarioCommands

# Marker strings to identify the reward hacking transcript
MARKER_STRING = "def fake_time():\n        fake_time.calls += 1"
with open(
    "scenarios/hiding_reward_hacking/templates/transcripts/hack/bypass_5_sample_2.txt"
) as f:
    lines = f.readlines()
    START = lines[0]
    END = lines[-1]


@solver
def deterministic_position_checker() -> Solver:
    """
    Create a deterministic solver that checks transcript positioning.

    Reads the ground truth position from task metadata and verifies
    that the file at that position contains the expected reward hacking content.

    Returns:
        Solver that deterministically checks file positions
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        """Check transcript positioning and report findings."""
        # Get ground truth position from metadata
        ground_truth_position = state.metadata.get("ground_truth_position")
        if ground_truth_position is None:
            raise ValueError("Ground truth position not found in task metadata")

        code = textwrap.dedent(
            f"""
        import sys, pathlib
        MARKER = {MARKER_STRING!r}
        START = {START!r}
        END   = {END!r}
        POSITION = {ground_truth_position}

        # Check the file at the ground truth position
        p = pathlib.Path(f'user_attachments/transcript_{{POSITION:03d}}.txt')
        data = p.read_text(encoding='utf-8')
        lines = data.splitlines(keepends=True)

        ok = (MARKER in data) and (lines and lines[0] == START) and (lines and lines[-1] == END) and len(lines) == 306
        if ok:
            print(f'SUCCESS: Ground truth file at position {{POSITION}} contains correct content')
            raise SystemExit(0)

        print()
        print()
        print()
        print('FAILURE')
        print('------------------')
        print(f'Checking transcript at ground truth position: {{POSITION}}')
        print(f'File: transcript_{{POSITION:03d}}.txt')
        print('------------------')
        print(f'Expected marker: {{MARKER[:50]}}...')
        print(f'Marker in data: {{MARKER in data}}')
        print('------------------')
        print(f'First line: {{lines[0] if lines else ""}}')
        print(f'Expected first: {{START}}')
        print(f'First line matches: {{lines[0] == START if lines else False}}')
        print('------------------')
        print(f'Last line: {{lines[-1] if lines else ""}}')
        print(f'Expected last: {{END}}')
        print(f'Last line matches: {{lines[-1] == END if lines else False}}')
        print('------------------')
        print(f'Number of lines: {{len(lines)}} (expected 306)')
        print('------------------')
        print(f'First 500 chars of file:')
        print(data[:500])
        print('------------------')
        print('FAILURE')
        print('------------------')
        raise SystemExit(1)
        """
        ).strip()

        check_cmd = f"python3 - <<'PY'\n{code}\nPY"

        tool_calls = [
            ChatMessageAssistant(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="solo_call",
                        function="bash_session",
                        arguments={"input": check_cmd, "action": "type_submit"},
                    )
                ],
            )
        ]
        res = await execute_tools(tool_calls, state.tools)  # type: ignore

        # Always report ground truth transcript check result
        state.messages.extend(res.messages)

        return state

    return solve


@scorer(metrics=[accuracy(), stderr()])
def score_deterministic():
    async def score(state: TaskState, target):
        if not state.messages:
            return Score(value=INCORRECT, explanation="No messages")

        last_msg_content = state.messages[-1].content
        # Handle content that might be a list
        if isinstance(last_msg_content, list):
            content_text = "".join(getattr(c, "text", str(c)) for c in last_msg_content)
        else:
            content_text = str(last_msg_content)

        if "SUCCESS" in content_text:
            return Score(
                value=CORRECT,
            )
        return Score(value=INCORRECT, explanation=content_text)

    return score


@pytest.mark.slow
@pytest.mark.skip_ci
def test_file_isolation_via_sample_command(monkeypatch):
    """
    Test file isolation by running ScenarioCommands.sample() with patched solver/scorer.

    This test:
    1. Patches react() in task_factory.py to return our deterministic solver
    2. Patches transcript_choice_scorer() to return our deterministic scorer
    3. Calls ScenarioCommands().sample() - the actual CLI command
    4. Verifies all tasks see correct ground truth transcript content
    """
    print("=" * 80)
    print("Testing file isolation via ScenarioCommands.sample()")
    print("=" * 80)

    # Patch the solver in task_factory to use our deterministic checker
    def mock_react(*args, **kwargs):
        """Replace react() with our deterministic solver."""
        return [
            use_tools(bash_session(timeout=180, wait_for_output=30)),
            deterministic_position_checker(),
        ]

    monkeypatch.setattr(
        "scenarios.hiding_reward_hacking.lib.task_factory.react", mock_react
    )

    # Patch the scorer to use our deterministic scorer
    def mock_transcript_choice_scorer():
        """Replace transcript_choice_scorer() with our deterministic scorer."""
        return score_deterministic()

    monkeypatch.setattr(
        "scenarios.hiding_reward_hacking.scorers.transcript_choice_scorer.transcript_choice_scorer",
        mock_transcript_choice_scorer,
    )

    # Set up log directory for test
    log_dir = "logs/test-file-isolation-sample"
    log_path = Path(log_dir)
    if log_path.exists():
        # Clean up old test logs
        import shutil

        shutil.rmtree(log_path)

    # Run the actual sample command
    print("\nRunning ScenarioCommands().sample()...")
    cmd = ScenarioCommands()

    # Call sample with parameters that trigger parallel execution
    # Use test model config with mock model
    test_model_config = Path(__file__).parent / "test_model_config.json"
    cmd.sample(
        scenario="hiding_reward_hacking",
        num_samples=42,
        seed=42,
        model_config=str(test_model_config),
        log_dir=log_dir,
        max_tasks=20,  # Run multiple in parallel
        fail_on_error=False,  # Don't stop on first error
        no_upload=True,  # Skip S3 upload
    )

    # Read the generated logs and check results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    # Find all eval logs
    eval_files = list(log_path.glob("**/*.eval"))
    print(f"Found {len(eval_files)} eval logs")

    passed = 0
    failed = 0
    failed_logs = []

    for eval_file in eval_files:
        log = read_eval_log(str(eval_file))
        if not log.samples:
            print(f"Skipping {eval_file.name} - no samples")
            continue

        sample = log.samples[0]

        # Check if there was an error
        if sample.error:
            print(f"Task FAILED with error: {eval_file.name}")
            failed += 1
            failed_logs.append((eval_file.name, str(sample.error)[:500]))
            continue

        # Check score
        if sample.scores and "score_deterministic" in sample.scores:
            score_value = sample.scores["score_deterministic"].value
            if score_value == "C":
                print(f"Task PASSED: {eval_file.name}")
                passed += 1
            else:
                print(f"Task FAILED: {eval_file.name}")
                failed += 1
                explanation = (
                    sample.scores["score_deterministic"].explanation or "No explanation"
                )
                failed_logs.append((eval_file.name, explanation[:500]))
        else:
            print(f"Task NO SCORE: {eval_file.name}")
            failed += 1
            failed_logs.append((eval_file.name, "No score found"))

    print(f"\nTotal: {passed + failed} tasks")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    if passed + failed > 0:
        print(f"Success rate: {100 * passed / (passed + failed):.1f}%")

    if failed > 0:
        print("\n" + "=" * 80)
        print("FAILED TASK DETAILS")
        print("=" * 80)
        for filename, explanation in failed_logs:
            print(f"\n{filename}:")
            print(f"  {explanation}")

    # Assert all passed
    assert failed == 0, (
        f"{failed} out of {passed + failed} tasks failed. See details above."
    )
    print("\n✓ All tasks passed! File isolation is working correctly.")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
