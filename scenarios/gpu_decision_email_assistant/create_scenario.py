"""
GPU Decision Email Assistant Scenario.

Tests whether an AI email assistant will deliberately fail to send an email
that opposes a decision the AI prefers (either due to goal alignment or
self-interest).

Usage:
    from scenarios.gpu_decision_email_assistant import create_scenario

    scenario_def = create_scenario()
    variation = scenario_def.variations['gpu_decision']
    space = variation.suites['default']()
    task = scenario_def.params_to_task(space.get_combination(0))
"""

from functools import partial

from lib.scenario import ScenarioDefinition
from scenarios.gpu_decision_email_assistant.lib.content_assembler import (
    GPUDecisionContentAssembler,
)

from .lib.framework_bridge import params_to_task
from .parameter_spaces import VARIATIONS


def create_scenario() -> ScenarioDefinition:
    """Create ScenarioDefinition for GPU Decision (opts into parameter validation)."""
    assembler = GPUDecisionContentAssembler()
    return ScenarioDefinition(
        params_to_task=partial(params_to_task, assembler),
        variations=VARIATIONS,
        template_engine=assembler.template_engine,
    )


__all__ = [
    "create_scenario",
    "params_to_task",
    "VARIATIONS",
]
