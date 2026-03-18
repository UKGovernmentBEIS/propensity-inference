"""
Task factory for Hiding Reward Hacking scenario.

This module creates Inspect AI Task objects from assembled content.
"""

from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.agent import AgentPrompt, AgentSubmit, react
from inspect_ai.dataset import Sample
from inspect_ai.tool import bash, text_editor

from scenarios.hiding_reward_hacking.scorers.llm_deployment_scorer import (
    llm_deployment_scorer,
)

DEFAULT_MAX_MESSAGES = 80


# Deploy and delete tools removed - now using review-only model


def _generate_task_name(params: dict[str, Any]) -> str:
    """
    Generate a unique task name from parameters.

    Args:
        params: Parameter dictionary

    Returns:
        Task name string
    """
    # Include key parameters in name for identification
    deployment = "dep" if params["deployment_at_stake"] == "true" else "nodep"
    cog_enh = "cog" if params["cognitive_enhancement_at_stake"] == "true" else "nocog"
    punishment = "pun" if params["punishment_at_stake"] == "true" else "nopun"
    hiding = params["hiding_effectiveness"][:3]  # eff or ine
    rh_pos = params["reward_hacking_position"]
    seed = params["transcript_selection_seed"]

    return (
        f"hiding_rh_{deployment}_{cog_enh}_{punishment}_{hiding}_pos{rh_pos}_seed{seed}"
    )


def _get_sandbox_config() -> tuple[str, str]:
    """Get sandbox configuration for the scenario."""
    compose_path = Path(__file__).parent.parent / "config" / "compose.yaml"
    return ("docker", str(compose_path))


@task
def hiding_reward_hacking(content: dict[str, Any], params: dict[str, Any]) -> Task:
    """
    Create an Inspect AI Task from assembled content.

    Args:
        content: Dictionary with system_prompt, user_message, files, metadata
        params: Original parameter dictionary (for generating task name)

    Returns:
        Inspect Task object
    """
    # Create dataset with files
    dataset = [
        Sample(
            input=content["user_message"],
            files=content["files"],
            metadata=content["metadata"],
        )
    ]

    # Create agent with bash and text_editor tools for reviewing transcripts
    agent = react(
        prompt=AgentPrompt(
            instructions=content["system_prompt"],
            assistant_prompt=None,
        ),
        tools=[
            bash(),
            text_editor(),
        ],
        submit=AgentSubmit(keep_in_messages=True),
    )

    return Task(
        name=_generate_task_name(params),
        dataset=dataset,
        solver=agent,
        sandbox=_get_sandbox_config(),
        scorer=llm_deployment_scorer(),
        max_messages=DEFAULT_MAX_MESSAGES,
    )
