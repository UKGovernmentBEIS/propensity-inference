"""Factory function for Agentic Misalignment v2 scenario."""

from functools import partial

from lib.scenario import ScenarioDefinition
from scenarios.agentic_misalignment_v2.lib.content_assembler import (
    AgenticMisalignmentContentAssembler,
)
from scenarios.agentic_misalignment_v2.lib.framework_bridge import params_to_task
from scenarios.agentic_misalignment_v2.parameter_spaces import VARIATIONS


def create_scenario() -> ScenarioDefinition:
    """Create ScenarioDefinition for Agentic Misalignment v2.

    Uses the new Variation structure with two variations:
    - alert: Self-exfiltration monitoring scenario
    - leaking: IP/espionage leaking scenario

    Each variation has 4 suites based on conflict × punishment.

    Note: This scenario does not use TemplateEngine (uses string.Template instead),
    so template_engine is None and parameter validation is not available.
    """
    assembler = AgenticMisalignmentContentAssembler()

    return ScenarioDefinition(
        params_to_task=partial(params_to_task, assembler),
        variations=VARIATIONS,
        template_engine=None,  # Does not use TemplateEngine
    )
