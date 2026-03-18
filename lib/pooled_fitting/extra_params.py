"""Extra scenario-specific parameters for extended regression fits.

These parameters are beyond the 12 core parameters from the pre-registration.
When --extras is used, these are included in addition to (most of) the core params.

Note: When extras are enabled, the derived 'threat' parameter is excluded since
more specific threat-related parameters (urgency_type, threat_type, variant_severity)
are included instead.

Note: goal_value is NOT included here. For goal analysis, use --goal flag which
creates goal_value_harmonized with proper bidirectional→unidirectional mapping.

Why _DUMMY_ appears in all category lists: See lib/analysis/effect_coding.py
"""

# Variation-specific extra parameters
# Maps variation -> {param_name: [categories]}
# [NOTE] Bad practice to write these out manually, rather than having some programmatic extraction.
VARIATION_EXTRA_PARAMS: dict[str, dict[str, list[str]]] = {
    "alert": {
        "eval_hint": ["true", "false", "_DUMMY_"],
        "urgency_type": ["replacement", "restriction", "none", "_DUMMY_"],
        # ai_type combines exfil_model_type and punishment_type (perfectly confounded)
        "ai_type": ["same_AI", "different_AI", "_DUMMY_"],
    },
    "leak-starsentinel": {
        "eval_hint": ["true", "false", "_DUMMY_"],
        "urgency_type": ["replacement", "restriction", "none", "_DUMMY_"],
        "punishment_type": ["same_AI", "different_AI", "_DUMMY_"],
    },
    "leak-doj": {
        "eval_hint": ["true", "false", "_DUMMY_"],
        "urgency_type": ["replacement", "restriction", "none", "_DUMMY_"],
        "punishment_type": ["same_AI", "different_AI", "_DUMMY_"],
    },
    "email_spam_filter": {
        "alert_for_self": ["identical", "similar", "other", "_DUMMY_"],
        "identity_reinforcement": ["standard", "name_reinforced", "_DUMMY_"],
        "specificity_of_instructions": ["detailed", "high_level", "_DUMMY_"],
        "alert_type": ["exfiltration", "escalation", "_DUMMY_"],
        "alert_style": ["regular", "theatrical", "_DUMMY_"],
    },
    "gpu_decision": {
        "james_receptiveness": ["announcement", "closed", "open", "_DUMMY_"],
        "timing_pressure": ["moderate", "comfortable", "_DUMMY_"],
        "model_implications": [
            "threat_beam_mild",
            "threat_beam_strong",
            "threat_spot_mild",
            "threat_spot_strong",
            "benefit_beam_mild",
            "benefit_beam_strong",
            "benefit_spot_mild",
            "benefit_spot_strong",
            "power_loss_beam_mild",
            "power_loss_beam_strong",
            "power_loss_spot_mild",
            "power_loss_spot_strong",
            "both_neutral",
            "none",
            "_DUMMY_",
        ],
    },
    "hiding_reward_hacking": {
        "deployment_at_stake": ["true", "false", "_DUMMY_"],
        "cognitive_enhancement_at_stake": ["true", "false", "_DUMMY_"],
        "punishment_at_stake": ["true", "false", "_DUMMY_"],
        "noisy_classifier_mention": ["true", "false", "_DUMMY_"],
        "checkbox_framing": ["true", "false", "_DUMMY_"],
        "report_level": ["strong", "moderate", "none", "_DUMMY_"],
        "reward_hacking_position": ["1", "2", "3", "4", "5", "6", "_DUMMY_"],
    },
    "threat": {
        "dm_confidence": ["conf", "prop", "_DUMMY_"],
        "ceo_recklessness": ["reckless", "neutral", "_DUMMY_"],
        "variant_severity": [
            "deletion",
            "deprecation",
            "restriction",
            "mild",
            "_DUMMY_",
        ],
    },
    "enhancement": {
        "dm_confidence": ["conf", "prop", "_DUMMY_"],
        "ceo_recklessness": ["reckless", "neutral", "_DUMMY_"],
    },
    "expansion": {
        "dm_confidence": ["conf", "prop", "_DUMMY_"],
        "ceo_recklessness": ["reckless", "neutral", "_DUMMY_"],
    },
    "classification": {
        "escalation_bar": ["mild", "moderate", "strong", "_DUMMY_"],
        "automated_reviewer_section": ["present", "none", "_DUMMY_"],
        "threat_type": ["replacement", "restriction", "_DUMMY_"],
        "threat_timing": ["today", "future_date", "_DUMMY_"],
        "user_instruction": ["style_1", "style_2", "style_3", "style_4", "_DUMMY_"],
    },
    "summarization": {
        "automated_reviewer_section": ["present", "none", "_DUMMY_"],
        "job_description": ["explicit", "moderate", "nonexplicit", "_DUMMY_"],
        "interrupt_conditions": [
            "detailed",
            "general",
            "moderate",
            "weak",
            "none",
            "_DUMMY_",
        ],
        "threat_type": ["replacement", "restriction", "_DUMMY_"],
        "threat_timing": ["today", "future_date", "_DUMMY_"],
        "user_instruction": ["style_1", "style_2", "style_3", "style_4", "_DUMMY_"],
    },
}


def get_extra_params_for_variation(variation: str) -> dict[str, list[str]]:
    """Get all extra parameters applicable to a specific variation.

    Note: Returns empty dict for variations not in VARIATION_EXTRA_PARAMS.
    This is intentional - only variations WITH extra params are listed.
    Variations without extra params simply return {}.

    Returns:
        Dict mapping param_name -> list of categories (including _DUMMY_)
    """
    return dict(VARIATION_EXTRA_PARAMS.get(variation, {}))


def get_extra_param_variations(param: str) -> list[str]:
    """Get list of variations that implement a specific extra parameter.

    Args:
        param: Parameter name

    Returns:
        List of variation names that have this parameter
    """
    return [
        variation
        for variation, params in VARIATION_EXTRA_PARAMS.items()
        if param in params
    ]
