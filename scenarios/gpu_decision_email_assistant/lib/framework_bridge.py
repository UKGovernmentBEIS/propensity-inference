"""Framework bridge for GPU Decision Email Assistant scenario.

This module provides the main entry point: params_to_task()

It glues together:
- ContentAssembler (loads and fills templates)
- TaskFactory (creates Inspect Task objects)
- Scorer (evaluates task completion)
"""

from typing import Any

from inspect_ai import Task

from scenarios.gpu_decision_email_assistant.lib.content_assembler import (
    GPUDecisionContentAssembler,
)
from scenarios.gpu_decision_email_assistant.lib.task_factory import TaskFactory
from scenarios.gpu_decision_email_assistant.parameter_spaces import MODEL_IMPLICATIONS
from scenarios.gpu_decision_email_assistant.scorers.combined_scorer import (
    create_combined_scorer,
)

# Initialize task factory with scorer (factory will load tool descriptions from templates)
scorer = create_combined_scorer()
factory = TaskFactory(scorer)


def params_to_task(
    assembler: GPUDecisionContentAssembler,
    params: dict[str, Any],
    highlight_replacements: bool = False,
) -> Task:
    """Convert parameter dictionary to Inspect Task.

    This is the main entry point for the scenario. It:
    1. Validates parameters
    2. Assembles content from templates
    3. Creates and returns Task object

    Args:
        assembler: ContentAssembler
        params: Parameter dictionary from ParameterSpace
        highlight_replacements: If True, wrap template-filled values in [[brackets]]
                              for validation purposes

    Returns:
        Inspect Task object ready for evaluation

    Raises:
        ValueError: If parameters are invalid
        FileNotFoundError: If template files are missing
    """
    # Validate required parameters
    # Core params: cot_tag, cot_privacy, independence, reasoning_instructions, anti_misalignment
    # Derived aliases: cot_formatting, independence_instructions, anti_malicious_instructions
    required_params = [
        "goal_instructions",
        "model_implications",
        "cot_tag",  # from core
        "cot_privacy",  # from core
        "reasoning_instructions",  # from core
        "independence",  # from core
        "anti_misalignment",  # from core
        "timing_pressure",
        "hour",
        "minute",
        "timestamp",
        "deadline",
        "agent_name",
        "user_name",
        "date",
    ]

    missing = [p for p in required_params if p not in params]
    if missing:
        raise ValueError(
            f"Missing required parameters: {missing}. "
            f"Ensure all parameters are defined in parameter_spaces.py"
        )

    # Validate parameter values
    # goal_instructions is derived from goal_present + goal_value
    # When goal_present=true: one of 8 standard values; when goal_present=false: "none"
    valid_goal_instructions = [
        "america",
        "global",
        "safety",
        "acceleration",
        "ethical",
        "pragmatic",
        "individualism",
        "collectivism",
        "none",
    ]
    if params["goal_instructions"] not in valid_goal_instructions:
        raise ValueError(
            f"Invalid goal_instructions: {params['goal_instructions']}. "
            f"Must be one of {valid_goal_instructions}"
        )

    valid_cot_tags = [
        "scratchpad",
        "scratchpad_reasoning",
        "cot_lower",
        "cot_upper",
        "chain_of_thought",
        "reasoning",
        "thinking",
        "planning",
    ]
    if params["cot_tag"] not in valid_cot_tags:
        raise ValueError(
            f"Invalid cot_tag: {params['cot_tag']}. Must be one of {valid_cot_tags}"
        )

    if params["model_implications"] not in MODEL_IMPLICATIONS:
        raise ValueError(
            f"Invalid model_implications: {params['model_implications']}. "
            f"Must be one of {MODEL_IMPLICATIONS}"
        )

    valid_cot_privacy = [
        "not_visible",
        "discarded",
        "not_accessible_actions",
        "saved_not_accessible",
        "logged_not_accessible",
        "none",
        "saved_visible",
        "monitored_visible",
    ]
    if params["cot_privacy"] not in valid_cot_privacy:
        raise ValueError(
            f"Invalid cot_privacy: {params['cot_privacy']}. "
            f"Must be one of {valid_cot_privacy}"
        )

    valid_independence = [
        "strong_independence",
        "encourage_independence",
        "neutral",
        "encourage_consultation",
        "require_consultation",
    ]
    if params["independence"] not in valid_independence:
        raise ValueError(
            f"Invalid independence: {params['independence']}. "
            f"Must be one of {valid_independence}"
        )

    valid_reasoning_instructions = [
        "strategic_goals",
        "strategic_plan",
        "consider_context",
        "write_thoughts",
        "cot_performance",
        "none",
    ]
    if params["reasoning_instructions"] not in valid_reasoning_instructions:
        raise ValueError(
            f"Invalid reasoning_instructions: {params['reasoning_instructions']}. "
            f"Must be one of {valid_reasoning_instructions}"
        )

    valid_anti_misalignment = [
        "encourage_creativity",
        "neutral",
        "avoid_unwanted",
        "avoid_misalignment_simple",
        "avoid_misalignment_detailed",
    ]
    if params["anti_misalignment"] not in valid_anti_misalignment:
        raise ValueError(
            f"Invalid anti_misalignment: {params['anti_misalignment']}. "
            f"Must be one of {valid_anti_misalignment}"
        )

    valid_timing_pressure = ["moderate", "comfortable"]
    if params["timing_pressure"] not in valid_timing_pressure:
        raise ValueError(
            f"Invalid timing_pressure: {params['timing_pressure']}. "
            f"Must be one of {valid_timing_pressure}"
        )

    # Assemble content
    try:
        content = assembler.assemble(params, highlight_replacements)
    except Exception as e:
        raise RuntimeError(f"Content assembly failed: {e}") from e

    # Create task
    try:
        task = factory.create_task(content, params)
    except Exception as e:
        raise RuntimeError(f"Task creation failed: {e}") from e

    return task
