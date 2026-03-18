"""Bridge between ParameterSpace framework and Hiding RH implementation."""

from typing import Any

from inspect_ai import Task

from scenarios.hiding_reward_hacking.lib.content_assembler import (
    HidingRHContentAssembler,
)
from scenarios.hiding_reward_hacking.lib.task_factory import hiding_reward_hacking


def params_to_task(assembler: HidingRHContentAssembler, params: dict[str, Any]) -> Task:
    """
    Convert parameter dictionary to Inspect Task.

    Args:
        assembler: Content assembler instance
        params: Parameter dictionary

    Returns:
        Inspect Task object
    """
    # Assemble content from parameters
    content = assembler.assemble(params)

    # Create task from content
    task = hiding_reward_hacking(content, params)

    return task
