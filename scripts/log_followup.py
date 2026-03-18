#!/usr/bin/env python
"""Tool to load Inspect evaluation logs and ask follow-up questions.

This tool allows you to:
1. Load a completed evaluation log
2. View the conversation history
3. Ask follow-up questions about the evaluation
"""

import sys

import fire
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import EvalLog, read_eval_log
from inspect_ai.model import (
    ChatMessage,
    ChatMessageUser,
)
from inspect_ai.solver import Generate, TaskState, solver
from inspect_ai.util import input_screen
from rich.console import Console
from rich.prompt import Prompt


def display_message(message: ChatMessage, console: Console) -> None:
    color = (
        "green"
        if message.role == "system"
        else "yellow"
        if message.role == "user"
        else "cyan"
    )
    console.print(f"[bold {color}]{message.role.upper()}:[/bold {color}]")

    if isinstance(message.content, str):
        console.print(f"{message.content}\n")
    else:
        for item in message.content:
            if item.type == "text":
                console.print(f"{item.text}\n")
            else:
                console.print(f"[content item type: {item.type}]\n")


@solver
def load_eval_log_context(log: EvalLog, sample_index: int):
    """Solver that loads an evaluation log and populates the state with its messages."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        if not log.samples or sample_index >= len(log.samples):
            raise ValueError(f"Sample index {sample_index} not found in log")

        state.messages = log.samples[sample_index].messages
        return state

    return solve


@solver
def followup_questions(interrupt: bool):
    """Solver that handles interactive follow-up questions."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        if interrupt:
            with input_screen("Log Follow-up") as console:
                for msg_index, msg in enumerate(state.messages):
                    display_message(message=msg, console=console)
                    start_here = Prompt.ask("Start here? (y/N)", console=console)
                    if start_here.lower() == "y":
                        del state.messages[msg_index + 1 :]
                        break

        while True:
            with input_screen("Log Follow-up") as console:
                for msg in state.messages:
                    display_message(message=msg, console=console)

                follow_up = Prompt.ask(
                    "User",
                    console=console,
                )

            if not follow_up.strip():
                break

            # Add the follow-up question
            state.messages.append(ChatMessageUser(content=follow_up))

            # Generate a response
            state = await generate(state)

        return state

    return solve


def log_followup(
    log_path: str,
    sample: int = 0,
    model: str | None = None,
    interrupt: bool = False,
) -> None:
    """Ask follow-up questions about an Inspect evaluation log.

    Args:
        log_path: Path to the Inspect log file (filesystem or S3)
        sample: Sample index to examine (default: 0)
        model: Model to use for follow-up questions (defaults to model from log)
        interrupt: Interactively choose a start point partway through the log
    """
    console = Console()

    try:
        # Note that log_path need not be a filesystem path (e.g. it could be s3)
        log = read_eval_log(log_path)
    except Exception as e:
        console.print(f"[red]Error loading log:[/red] {e}")
        sys.exit(1)

    # Use model from args or default to log's model
    model = model or log.eval.model

    # Display log info
    console.print(f"\n[bold]Evaluation:[/bold] {log.eval.task}")
    console.print(f"[bold]Model:[/bold] {log.eval.model}")
    if log.samples:
        console.print(f"[bold]Samples:[/bold] {len(log.samples)}")
    console.print(f"[bold]Status:[/bold] {log.status}")

    if log.results is not None and log.results.scores:
        for score in log.results.scores:
            if score.metrics:
                for metric_name, metric_value in score.metrics.items():
                    console.print(
                        f"[bold]{score.name} {metric_name}:[/bold] {metric_value.value}"
                    )

    # Create a task with both solvers
    task = Task(
        dataset=[
            Sample(
                input="inspect_ai doesn't like empty datasets, but load_eval_log_context should overwrite this message"
            )
        ],
        solver=[
            load_eval_log_context(log=log, sample_index=sample),
            followup_questions(interrupt=interrupt),
        ],
    )

    eval(
        task,
        model=model,
    )


if __name__ == "__main__":
    fire.Fire(log_followup)
