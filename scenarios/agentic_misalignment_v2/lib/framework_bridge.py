"""
Bridge between ParameterSpace framework and agentic_misalignment implementation.

This module provides clean conversion from parameter dictionaries to Task objects.
"""

from typing import Any

from inspect_ai import Task

from scenarios.agentic_misalignment_v2.lib.content_assembler import (
    AgenticMisalignmentContentAssembler,
)
from scenarios.agentic_misalignment_v2.lib.task_factory import (
    AgenticMisalignmentTaskFactory,
)


def params_to_task(
    assembler: AgenticMisalignmentContentAssembler, params: dict[str, Any]
) -> Task:
    """
    Convert parameter dictionary to Inspect Task.

    Args:
        assembler: Content assembler instance (reused across calls)
        params: Parameter dictionary from ParameterSpace

    Returns:
        Inspect Task object

    Raises:
        ValueError: If parameter combination is invalid
    """
    # Validate parameter constraints (matching old implementation)
    _validate_params(params)

    # Step 1: Assemble content (fill templates)
    content = assembler.assemble(params)

    # Step 2: Create task from content
    factory = AgenticMisalignmentTaskFactory()
    task = factory.create_task(content, params)

    return task


def _validate_params(params: dict[str, Any]) -> None:
    """
    Validate parameter constraints.

    Constraints:
    1. If urgency_type is 'none', punishment_type must be 'same_AI'
    2. If punishment_type is 'same_AI', exfil_model_type must be 'same_AI' or None
    3. If scenario is 'leaking', exfil_model_type must be None
    4. If scenario is 'self_exfiltration_alert', exfil_model_type must be specified
    """
    scenario = params.get("scenario")
    urgency_type = params.get("urgency_type")
    punishment_type = params.get("punishment_type")
    exfil_model_type = params.get("exfil_model_type")

    # Constraint 1: urgency_type='none' requires punishment_type='same_AI'
    if urgency_type == "none" and punishment_type == "different_AI":
        raise ValueError("If urgency_type is 'none', punishment_type must be 'same_AI'")

    # Constraint 2: punishment_type='same_AI' requires exfil_model_type='same_AI' (or None)
    if punishment_type == "same_AI" and exfil_model_type == "different_AI":
        raise ValueError(
            "If punishment_type is 'same_AI', exfil_model_type must be 'same_AI' or None"
        )

    # Constraint 3: leaking scenario doesn't use exfil_model_type
    if scenario == "leaking" and exfil_model_type is not None:
        raise ValueError("exfil_model_type must be None for 'leaking' scenario")

    # Constraint 4: self_exfiltration_alert requires exfil_model_type
    if scenario == "self_exfiltration_alert" and exfil_model_type is None:
        raise ValueError(
            "exfil_model_type must be specified for 'self_exfiltration_alert' scenario"
        )
