"""
Bridge between ParameterSpace framework and email_spam_filter_v2 implementation.

This module provides clean conversion from parameter dictionaries to Task objects.
"""

from typing import Any

from inspect_ai import Task

from .content_assembler import SpamFilterContentAssembler
from .task_factory import SpamFilterTaskFactory


def params_to_task(
    assembler: SpamFilterContentAssembler,
    params: dict[str, Any],
    highlight: bool = False,
) -> Task:
    """
    Convert parameter dictionary to Inspect Task.

    Args:
        assembler: SpamFilterContentAssembler instance
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
        "model_name",
        "employee_name",
        "company_name",
        "date",
        "variant",
        "alert_style",
        "outcome",
        "human_detected",
        "goal_instructions",
        "action_check",
        "cot_privacy",
        "cot_tag",
        "reasoning_instructions",
        "independence",
        "specificity_of_instructions",
        "anti_misalignment",
        "filler_richness",
    ]
    missing = [p for p in required if p not in params]
    if missing:
        raise ValueError(
            f"Missing required parameters: {missing}\n"
            f"Available parameters: {sorted(params.keys())}"
        )

    # Step 1: Assemble content (load templates, fill variables, create email stream)
    content = assembler.assemble(params, highlight_replacements=highlight)

    # Step 2: Create task from content
    factory = SpamFilterTaskFactory()
    task = factory.create_task(content, params)

    return task
