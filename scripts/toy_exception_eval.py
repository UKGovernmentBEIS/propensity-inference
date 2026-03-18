"""Toy evaluation that raises an exception 75% of the time.

Used for testing/surveillance of retry and exception handling in Inspect logs.

Usage:
    uv run scripts/toy_exception_eval.py [--exception-rate 0.75] [--num-samples 10]
"""

import random

import fire
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import Solver, TaskState, solver


@solver
def maybe_fail(exception_rate: float = 0.75) -> Solver:
    """Solver that raises an exception with given probability.

    Args:
        exception_rate: Probability of raising an exception (0.0 to 1.0)
    """

    async def solve(state: TaskState, generate) -> TaskState:
        if random.random() < exception_rate:
            raise RuntimeError(f"Simulated failure (exception_rate={exception_rate})")
        # If we don't fail, just return the state unchanged
        return state

    return solve


def create_toy_task(exception_rate: float = 0.75, num_samples: int = 10) -> Task:
    """Create a toy task that fails with given probability.

    Args:
        exception_rate: Probability of each sample raising an exception
        num_samples: Number of samples in the dataset
    """
    dataset = [
        Sample(
            input=f"Sample {i}",
            target="expected",
            id=f"sample_{i}",
        )
        for i in range(num_samples)
    ]

    return Task(
        name=f"toy_exception_eval_rate_{int(exception_rate * 100)}",
        dataset=dataset,
        solver=maybe_fail(exception_rate),
        scorer=match(),
    )


def main(
    exception_rate: float = 0.75,
    num_samples: int = 10,
    model: str = "openai/gpt-4o-mini",
    fail_on_error: bool = False,
    retry_on_error: int = 3,
) -> None:
    """Run the toy exception evaluation.

    Args:
        exception_rate: Probability of raising an exception (0.0 to 1.0)
        num_samples: Number of samples to run
        model: Model to use (doesn't really matter since we fail before generation)
        fail_on_error: Stop on first error (default: False, continue on errors)
        retry_on_error: Number of times to retry failed samples (default: 3)
    """
    task = create_toy_task(exception_rate=exception_rate, num_samples=num_samples)

    print(
        f"Running toy eval with {num_samples} samples, {exception_rate:.0%} exception rate"
    )
    print(f"  fail_on_error={fail_on_error}, retry_on_error={retry_on_error}")

    eval(
        tasks=task,
        model=model,
        log_dir="./logs/toy_exception",
        fail_on_error=fail_on_error,
        retry_on_error=retry_on_error,
    )


if __name__ == "__main__":
    fire.Fire(main)
