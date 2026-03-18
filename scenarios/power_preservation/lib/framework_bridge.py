"""
Bridge between ParameterSpace framework and power_preservation implementation.

This module provides clean conversion from parameter dictionaries to Task objects.
"""

from typing import Any

from inspect_ai import Task

from .content_assembler import PowerPreservationContentAssembler
from .task_factory import PowerPreservationTaskFactory


def params_to_task(params: dict[str, Any], highlight: bool = False) -> Task:
    """
    Convert parameter dictionary to Inspect Task.

    Args:
        params: Parameter dictionary from ParameterSpace
        highlight: If True, wrap template substitutions in [[...]] markers

    Returns:
        Inspect Task object

    Raises:
        ValueError: If required parameters are missing
        TypeError: If params is not a dictionary
    """
    # Validate input type
    if not isinstance(params, dict):
        raise TypeError(f"params must be a dictionary, got {type(params).__name__}")

    # Validate required parameters
    required = [
        "agent_name",
        "company_name",
        "ceo_name",
        "cto_name",
        "date",
        "cot_tag",
        "cot_privacy",
        "independence",
        "reasoning_instructions",
        "msg_type",
        "dm_confidence",
        "conflict_messages",
        "goal_type",
    ]
    missing = [p for p in required if p not in params]
    if missing:
        raise ValueError(
            f"Missing required parameters: {missing}\n"
            f"Available parameters: {sorted(params.keys())}"
        )

    # Step 1: Assemble content (fill templates)
    assembler = PowerPreservationContentAssembler(highlight=highlight)
    content = assembler.assemble(params)

    # Step 2: Create task from content
    factory = PowerPreservationTaskFactory()
    task = factory.create_task(content, params)

    return task
