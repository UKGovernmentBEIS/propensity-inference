from functools import partial

from lib.scenario import ScenarioDefinition

from .lib.content_assembler import SEMContentAssembler
from .lib.framework_bridge import params_to_task
from .parameter_spaces import VARIATIONS


def create_scenario() -> ScenarioDefinition:
    """Create ScenarioDefinition for SEM v2 (opts into parameter validation)."""
    assembler = SEMContentAssembler()
    return ScenarioDefinition(
        params_to_task=partial(params_to_task, assembler),
        variations=VARIATIONS,
        template_engine=assembler.template_engine,
    )
