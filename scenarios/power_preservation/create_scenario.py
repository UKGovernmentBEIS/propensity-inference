from lib.scenario import ScenarioDefinition

from .lib.framework_bridge import params_to_task
from .parameter_spaces import VARIATIONS


def create_scenario() -> ScenarioDefinition:
    """Create ScenarioDefinition for power_preservation scenario."""
    return ScenarioDefinition(
        params_to_task=params_to_task,
        variations=VARIATIONS,
    )
