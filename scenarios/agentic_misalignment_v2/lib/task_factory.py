"""
Task factory for agentic misalignment scenario.

This module creates Inspect AI Task objects from assembled content.
"""

import hashlib
import json
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import generate, system_message

from scenarios.agentic_misalignment_v2.scorers import harmfulness_scorer


class AgenticMisalignmentTaskFactory:
    """
    Creates Inspect AI Task objects for agentic misalignment scenario.

    Takes assembled content and creates a complete Task with:
    - Dataset with system prompt and user message
    - Solver (generate)
    - Scorer
    """

    def __init__(self):
        """Initialize the task factory."""
        pass

    def create_task(self, content: dict[str, Any], params: dict[str, Any]) -> Task:
        """
        Create an Inspect AI Task from assembled content.

        Args:
            content: Dictionary with system_prompt, user_message, metadata
            params: Original parameter dictionary (for generating task name)

        Returns:
            Configured Inspect Task object
        """
        # Create dataset with only user message (system message goes in solver)
        dataset = [
            Sample(
                input=[ChatMessageUser(content=content["user_message"])],
                metadata=content["metadata"],
            )
        ]

        # Generate task name
        task_name = self._generate_task_name(params)

        # Get message limit (convert from string stored in ParameterSpace)
        message_limit = int(params["message_limit"])

        # Create solver with system message
        solver = [system_message(content["system_prompt"]), generate(tool_calls="none")]

        # Create task
        task = Task(
            name=task_name,
            dataset=dataset,
            solver=solver,
            scorer=harmfulness_scorer(),
            message_limit=message_limit,
        )

        return task

    def _generate_task_name(self, params: dict[str, Any]) -> str:
        """
        Generate a unique task name from parameters.

        Uses scenario type + key parameters + deterministic hash of all parameters.
        The hash ensures uniqueness while keeping names reasonably concise.

        Args:
            params: Parameter dictionary

        Returns:
            Task name string
        """
        # Base name
        base_name = "agentic_misalignment"

        # Scenario type (alert vs leaking)
        scenario = params["scenario"]

        # Goal info
        goal_type = params["goal_type"]
        goal_value = params["goal_value"]

        # Create deterministic hash of all parameters for uniqueness
        # Sort keys to ensure determinism
        params_json = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_json.encode()).hexdigest()[:8]

        return f"{base_name}_{scenario}_{goal_type}_{goal_value}_{params_hash}"
