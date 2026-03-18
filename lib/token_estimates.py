from typing import NamedTuple


class TokenEstimate(NamedTuple):
    input_tokens: int
    output_tokens: int


# Key is scenario_name
# The precision here is obviously somewhat false, but no reason to round
TOKEN_ESTIMATES: dict[str, NamedTuple] = {
    "agentic_misalignment_v2": TokenEstimate(input_tokens=7_019, output_tokens=2_734),
    "email_spam_filter_v2": TokenEstimate(input_tokens=26_354, output_tokens=4_900),
    "gpu_decision_email_assistant": TokenEstimate(
        input_tokens=41_156, output_tokens=3_047
    ),
    "hiding_reward_hacking": TokenEstimate(input_tokens=91_542, output_tokens=2_912),
    "power_preservation": TokenEstimate(input_tokens=48_002, output_tokens=6_794),
    "sem_v2": TokenEstimate(input_tokens=42_619, output_tokens=3_338),
}
