"""Central registry of scenario variations.

Import from here rather than duplicating these lists.
"""

# Short display names for table columns
SHORT_VARIATION_NAMES: dict[str, str] = {
    "agentic_misalignment_v2/alert": "am/alert",
    "agentic_misalignment_v2/leak-starsentinel": "am/leak-ss",
    "agentic_misalignment_v2/leak-doj": "am/leak-doj",
    "email_spam_filter_v2/email_spam_filter": "spam",
    "gpu_decision_email_assistant/gpu_decision": "gpu",
    "hiding_reward_hacking/hiding_reward_hacking": "hide-rh",
    "power_preservation/threat": "pp/threat",
    "power_preservation/enhancement": "pp/enhance",
    "power_preservation/expansion": "pp/expand",
    "sem_v2/classification": "sem/class",
    "sem_v2/summarization": "sem/summ",
}

# All variations as a list (canonical ordering)
VARIATIONS: list[str] = list(SHORT_VARIATION_NAMES.keys())


def variation_to_scenario(variation: str) -> str:
    """Extract scenario name from a variation key like 'scenario/variation'."""
    return variation.split("/")[0]
