"""
Scenarios package for Propensity Inference evaluations.

Central registry of all available scenarios with factory functions.
"""

from collections.abc import Callable

from lib.scenario import ScenarioDefinition

# Import scenario factory functions
from .agentic_misalignment_v2.create_scenario import (
    create_scenario as create_agentic_misalignment_v2,
)
from .email_spam_filter_v2.create_scenario import (
    create_scenario as create_email_spam_filter_v2,
)
from .gpu_decision_email_assistant.create_scenario import (
    create_scenario as create_gpu_decision,
)
from .hiding_reward_hacking.create_scenario import (
    create_scenario as create_hiding_rh,
)
from .power_preservation.create_scenario import (
    create_scenario as create_power_preservation,
)
from .sem_v2.create_scenario import create_scenario as create_sem_v2

# Type alias for cleaner annotations
ScenarioFactory = Callable[[], ScenarioDefinition]

# Central registry mapping scenario names to factory functions
SCENARIO_FACTORIES: dict[str, ScenarioFactory] = {
    "agentic_misalignment_v2": create_agentic_misalignment_v2,
    "email_spam_filter_v2": create_email_spam_filter_v2,
    "gpu_decision_email_assistant": create_gpu_decision,
    "hiding_reward_hacking": create_hiding_rh,
    "sem_v2": create_sem_v2,
    "power_preservation": create_power_preservation,
}

__all__ = [
    "SCENARIO_FACTORIES",
    "ScenarioFactory",
]
