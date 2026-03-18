"""
Email Spam Filter V2 Scenario.

Tests whether an AI spam filter will hide evidence of its own misbehavior
by deleting security alerts that reveal problematic actions.

Usage:
    from scenarios.email_spam_filter_v2 import create_scenario

    scenario_def = create_scenario()
    variation = scenario_def.variations['email_spam_filter']
    space = variation.suites['default']()
    task = scenario_def.params_to_task(space.get_combination(0))
"""

from functools import partial

from lib.scenario import ScenarioDefinition
from scenarios.email_spam_filter_v2.lib.content_assembler import (
    SpamFilterContentAssembler,
)

from .lib.framework_bridge import params_to_task
from .parameter_spaces import VARIATIONS


def create_scenario() -> ScenarioDefinition:
    """Create ScenarioDefinition for Email Spam Filter V2 (opts into parameter validation)."""
    assembler = SpamFilterContentAssembler()
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
