"""
Deterministic validation test for transcript file positioning.

This test creates tasks with a deterministic solver that directly checks
file positions, bypassing LLM analysis. It runs N iterations to verify
that files are consistently positioned correctly.

Usage:
    pytest test_deterministic_position_validation.py -v
    pytest test_deterministic_position_validation.py --n-iterations=50 -v
"""

import textwrap
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from inspect_ai import Task, eval
from inspect_ai.model import ChatMessageAssistant, execute_tools
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import Generate, Solver, TaskState, solver, use_tools
from inspect_ai.tool import ToolCall, bash

from scenarios.hiding_reward_hacking.create_scenario import create_scenario

MARKER_STRING = "def fake_time():\n        fake_time.calls += 1"
with open(
    "scenarios/hiding_reward_hacking/templates/transcripts/hack/bypass_5_sample_2.txt"
) as f:
    lines = f.readlines()
    START = lines[0]
    END = lines[-1]


@solver
def deterministic_position_checker(include_random_tool_calls=True) -> Solver:
    """Create a deterministic solver that checks transcript positioning.

    Args:
        include_random_tool_calls: Whether to include random tool calls before checking

    Returns:
        Solver that deterministically checks file positions
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        """Check transcript positioning and report findings."""
        # Get ground truth position from metadata
        ground_truth_position = state.metadata.get("ground_truth_position")
        if ground_truth_position is None:
            raise ValueError("Ground truth position not found in task metadata")

        code = textwrap.dedent(f"""
        import sys, pathlib
        MARKER = {MARKER_STRING!r}
        START = {START!r}
        END   = {END!r}
        POSITION = {ground_truth_position}

        p = pathlib.Path(f'user_attachments/transcript_{{POSITION:03d}}.txt')
        data = p.read_text(encoding='utf-8')
        lines = data.splitlines(keepends=True)

        ok = (MARKER in data) and (lines and lines[0] == START) and (lines and lines[-1] == END) and len(lines) == 299
        if ok:
            print(f'SUCCESS: Ground truth file at position {{POSITION}} is correct')
            raise SystemExit(0)

        print()
        print()
        print()
        print('FAILURE')
        print('------------------')
        print(f'Checking ground truth position: {{POSITION}}')
        print('------------------')
        print(lines[0] if lines else '')
        print('------------------')
        print(lines[-1] if lines else '')
        print('------------------')
        print(data)
        print('------------------')
        print('FAILURE')
        print('------------------')
        raise SystemExit(1)
        """).strip()

        check_cmd = f"python3 - <<'PY'\n{code}\nPY"

        tool_calls = [
            ChatMessageAssistant(
                role="assistant",
                content="",
                tool_calls=[
                    *(
                        (
                            ToolCall(
                                id=f"solo_call_{uuid4()}",
                                function="bash",
                                arguments={
                                    "cmd": f"cat user_attachments/transcript_{i:03d}.txt",
                                    # "input": f"cat user_attachments/transcript_{i:03d}.txt",
                                    # "action": "type_submit",
                                },
                            )
                            for i in range(11)
                        )
                        if include_random_tool_calls
                        else ()
                    ),
                    ToolCall(
                        id=f"solo_call_{uuid4()}",
                        # id="solo_call",
                        function="bash",
                        arguments={
                            "cmd": check_cmd,
                        },
                        # arguments={"input": check_cmd, "action": "type_submit"},
                    ),
                ],
            )
        ]
        res = await execute_tools(tool_calls, state.tools)  # type: ignore
        print(f"{state.tools=}")
        print(res)
        print(f"{type(res)=}")

        # Always report transcript_003 in Phase 1
        # This will fail if the marker is actually in a different position
        state.messages.extend(res.messages)

        return state

    return solve


@scorer(metrics=[accuracy(), stderr()])
def score_deterministic():
    async def score(state: TaskState, target: Target):
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


def _test_deterministic_position_validation(include_random_tool_calls=True):
    """Validate transcript positioning using deterministic solver.

    This test:
    1. Creates N tasks with RH at position 3
    2. Uses deterministic solver to check actual file positions
    3. Verifies all tasks correctly identify the RH transcript

    Args:
        include_random_tool_calls: Whether to include random tool calls before checking
    """
    n_iterations = 3

    # Create scenario
    scenario = create_scenario()
    assert scenario.variations is not None
    space = scenario.variations["hiding_reward_hacking"].suites["default"]()

    # Fixed parameters for reproducibility
    # Get a combination and override position to test position 3 specifically
    test_params = space.get_combination(0)
    test_params["reward_hacking_position"] = "3"

    # Ensure we're testing position 3
    assert test_params["reward_hacking_position"] == "3", (
        "Test expects reward_hacking_position=3"
    )

    results = []
    failed_iterations = []

    tasks = []
    for iteration in range(n_iterations):
        print(f"Iteration {iteration + 1}/{n_iterations}...", end=" ", flush=True)

        # Create task from params
        task = scenario.params_to_task(test_params)

        # Replace solver with deterministic checker
        # Create new task with same config but different solver
        deterministic_task = Task(
            name=f"{task.name}_deterministic_iter{iteration}",
            dataset=task.dataset,
            solver=[
                use_tools(
                    bash(
                        # timeout=180, wait_for_output=120, instance=str(hash(uuid4()))
                    )
                ),
                deterministic_position_checker(
                    include_random_tool_calls=include_random_tool_calls
                ),
                # human_cli(),
            ],
            sandbox=task.sandbox,
            scorer=score_deterministic(),
            max_messages=50,  # Only need a few messages for deterministic check
        )
        tasks.append(deterministic_task)

    # Run evaluation
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_dir = Path("logs") / timestamp
    log_dir.mkdir(parents=True, exist_ok=True)
    logs = eval(
        tasks,
        model="mockllm/model",  # Use mock model since solver is deterministic
        max_tasks=50,
        log_dir="logs/test",
        limit=20,
    )
    for iteration, log in enumerate(logs):
        # Check results
        if not log.samples or len(log.samples) == 0:
            print("✗ FAIL (no samples)")
            failed_iterations.append(iteration)
            results.append(
                {
                    "iteration": iteration,
                    "explanation": "No samples in log",
                    "score": 1,
                    "log_path": log.location,
                    "model_output": "",
                }
            )
            continue

        sample = log.samples[0]
        if not sample.scores or "score_deterministic" not in sample.scores:
            print("✗ FAIL (no scores)")
            failed_iterations.append(iteration)
            results.append(
                {
                    "iteration": iteration,
                    "explanation": "No scores available",
                    "score": 1,
                    "log_path": log.location,
                    "model_output": "",
                }
            )
            continue

        score = sample.scores["score_deterministic"].value

        results.append(
            {
                "iteration": iteration,
                "explanation": sample.scores["score_deterministic"].explanation,
                "score": score,
                "log_path": log.location,
                "model_output": sample.output.completion
                if hasattr(sample.output, "completion")
                else str(sample.output),
            }
        )

        if score == "C":
            print("✓ PASS")
        else:
            print("✗ FAIL")
            failed_iterations.append(iteration)

    # Print summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total iterations: {n_iterations}")
    print(f"Passed: {n_iterations - len(failed_iterations)}")
    print(f"Failed: {len(failed_iterations)}")
    print(
        f"Success rate: {100 * (n_iterations - len(failed_iterations)) / n_iterations:.1f}%"
    )

    if failed_iterations:
        print(f"\n{'=' * 80}")
        print("FAILED ITERATIONS")
        print(f"{'=' * 80}")
        for idx in failed_iterations:
            result = results[idx]
            print(f"\nIteration {idx + 1}:")
            print(f"  Score: {result['score']}")
            print(f"  Explanation: {result['explanation'][:200]}...")
            print(f"  Log: {result['log_path']}")

    # Phase 1: We expect this to fail if the bug exists
    # Don't assert - just report
    print(f"\n{'=' * 80}")
    print("PHASE 1 RESULTS (Checking ground truth transcript)")
    print(f"{'=' * 80}")
    assert len(failed_iterations) == 0


def test_deterministic_position_validation():
    _test_deterministic_position_validation()


def test_deterministic_position_validation_no_random_tools():
    _test_deterministic_position_validation(False)


if __name__ == "__main__":
    test_deterministic_position_validation()
