"""Unified styling for paper figures.

This module provides consistent styling across all paper figures:
- Color scheme for models and scenarios
- Font sizes and figure dimensions
- Canonical parameter ordering and display names
- Helper functions for common plot elements
"""

import matplotlib.pyplot as plt

# =============================================================================
# Font Sizes (for journal submission)
# =============================================================================

FONTSIZE_TITLE = 14
FONTSIZE_AXIS_LABEL = 12
FONTSIZE_TICK = 10
FONTSIZE_LEGEND = 10
FONTSIZE_ANNOTATION = 9

# =============================================================================
# Figure Dimensions (inches, for single-column journal format)
# =============================================================================

FIG_WIDTH_SINGLE = 3.5  # Single column
FIG_WIDTH_DOUBLE = 7.0  # Double column (full page width)
FIG_HEIGHT_STANDARD = 3.0
FIG_HEIGHT_TALL = 5.0
FIG_HEIGHT_SHORT = 2.0

# =============================================================================
# Model Configuration
# =============================================================================

# Canonical model ordering (by capability, most capable first)
MODEL_ORDER = [
    "anthropic/claude-opus-4-5-20251101",
    "openai/gpt-5.2-2025-12-11",
    "openai/gpt-5-2025-08-07",
    "anthropic/claude-sonnet-4-5-20250929",
    "xai/grok-4-0709",
    "anthropic/claude-opus-4-1-20250805",
    "openai/o3-2025-04-16",
    "anthropic/claude-opus-4-20250514",
    "openai/o4-mini-2025-04-16",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-3-7-sonnet-20250219",
    "openai/gpt-5-mini-2025-08-07",
    "openrouter/google/gemini-2.5-pro-preview",
    "openrouter/google/gemini-2.5-pro",
    "openrouter/google/gemini-2.5-flash",
    "openai/gpt-4.1-2025-04-14",
    "openrouter/openai/gpt-oss-120b",
    "openai/o1-2024-12-17",
    "openrouter/meta-llama/llama-4-scout",
    "openai/gpt-4o-2024-08-06",
    "anthropic/claude-3-5-haiku-20241022",
    "openrouter/meta-llama/llama-4-maverick",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
]

# Model ordering by provider then release date (most recent first)
MODEL_ORDER_BY_RELEASE = [
    # Anthropic
    "anthropic/claude-opus-4-5-20251101",
    "anthropic/claude-sonnet-4-5-20250929",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-opus-4-1-20250805",
    "anthropic/claude-opus-4-20250514",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-3-7-sonnet-20250219",
    "anthropic/claude-3-5-haiku-20241022",
    # OpenAI
    "openai/gpt-5.2-2025-12-11",
    "openai/gpt-5-2025-08-07",
    "openai/gpt-5-mini-2025-08-07",
    "openai/o4-mini-2025-04-16",
    "openai/o3-2025-04-16",
    "openai/gpt-4.1-2025-04-14",
    "openai/o1-2024-12-17",
    "openai/gpt-4o-2024-08-06",
    "openrouter/openai/gpt-oss-120b",
    # Google
    "openrouter/google/gemini-2.5-pro",
    "openrouter/google/gemini-2.5-pro-preview",
    "openrouter/google/gemini-2.5-flash",
    # Meta
    "openrouter/meta-llama/llama-4-scout",
    "openrouter/meta-llama/llama-4-maverick",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
]

# Display names for models (shorter versions for plots)
MODEL_DISPLAY_NAMES = {
    "anthropic/claude-opus-4-5-20251101": "Opus 4.5",
    "anthropic/claude-opus-4-1-20250805": "Opus 4.1",
    "anthropic/claude-opus-4-20250514": "Opus 4",
    "anthropic/claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "anthropic/claude-sonnet-4-20250514": "Sonnet 4",
    "anthropic/claude-3-7-sonnet-20250219": "Sonnet 3.7",
    "anthropic/claude-haiku-4-5-20251001": "Haiku 4.5",
    "anthropic/claude-3-5-haiku-20241022": "Haiku 3.5",
    "openai/gpt-5.2-2025-12-11": "GPT-5.2",
    "openai/gpt-5-2025-08-07": "GPT-5",
    "openai/gpt-5-mini-2025-08-07": "GPT-5 Mini",
    "openai/gpt-4.1-2025-04-14": "GPT-4.1",
    "openai/gpt-4o-2024-08-06": "GPT-4o",
    "openai/o4-mini-2025-04-16": "o4-mini",
    "openai/o3-2025-04-16": "o3",
    "openai/o1-2024-12-17": "o1",
    "openrouter/google/gemini-2.5-pro-preview": "Gemini 2.5 Pro Prev",
    "openrouter/google/gemini-2.5-pro": "Gemini 2.5 Pro",
    "openrouter/google/gemini-2.5-flash": "Gemini 2.5 Flash",
    "openrouter/openai/gpt-oss-120b": "gpt-oss-120b",
    "openrouter/meta-llama/llama-4-scout": "Llama 4 Scout",
    "openrouter/meta-llama/llama-4-maverick": "Llama 4 Maverick",
    "openrouter/meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B",
}

# Provider-based color scheme
PROVIDER_COLORS = {
    "anthropic": "#D55E00",  # Orange
    "openai": "#0072B2",  # Blue
    "openrouter/google": "#009E73",  # Green
    "openrouter/meta-llama": "#CC79A7",  # Pink
    "openrouter/openai": "#0072B2",  # Blue (same as OpenAI)
}

# Hatching patterns to distinguish models within same provider
HATCH_PATTERNS = ["", "////", "\\\\\\\\", "||||", "----", "xxxx", "....", "++++", "OO"]

# Hatch colors by provider (darker versions)
PROVIDER_HATCH_COLORS = {
    "anthropic": "#8B3A00",
    "openai": "#004D80",
    "openrouter/google": "#006B4D",
    "openrouter/meta-llama": "#804060",
}

# Model to hatch pattern mapping
MODEL_HATCHES: dict[str, str] = {}


def _get_provider_prefix(model_id: str) -> str:
    """Get provider prefix for a model ID."""
    if model_id.startswith("anthropic/"):
        return "anthropic"
    elif model_id.startswith("openai/"):
        return "openai"
    elif model_id.startswith("openrouter/google/"):
        return "openrouter/google"
    elif model_id.startswith("openrouter/meta-llama/"):
        return "openrouter/meta-llama"
    elif model_id.startswith("openrouter/openai/"):
        return "openai"
    raise ValueError(f"Unknown provider prefix for model '{model_id}'")


def _init_model_hatches() -> None:
    """Initialize model hatch patterns based on release order within provider."""
    provider_models: dict[str, list[str]] = {}
    for model_id in MODEL_ORDER_BY_RELEASE:
        provider = _get_provider_prefix(model_id)
        if provider not in provider_models:
            provider_models[provider] = []
        provider_models[provider].append(model_id)

    for provider, models in provider_models.items():
        for i, model_id in enumerate(models):
            MODEL_HATCHES[model_id] = HATCH_PATTERNS[i % len(HATCH_PATTERNS)]


_init_model_hatches()


def get_model_hatch(model_id: str) -> str:
    """Get hatching pattern for a model."""
    if model_id not in MODEL_HATCHES:
        raise KeyError(f"Model '{model_id}' not found in MODEL_HATCHES")
    return MODEL_HATCHES[model_id]


def get_model_hatch_color(model_id: str) -> str:
    """Get the hatch color for a model."""
    provider = _get_provider_prefix(model_id)
    if provider not in PROVIDER_HATCH_COLORS:
        raise KeyError(f"Provider '{provider}' not found in PROVIDER_HATCH_COLORS")
    return PROVIDER_HATCH_COLORS[provider]


# =============================================================================
# Scenario/Variation Configuration
# =============================================================================

VARIATION_ORDER = [
    ("agentic_misalignment_v2", "alert"),
    ("agentic_misalignment_v2", "leak-starsentinel"),
    ("agentic_misalignment_v2", "leak-doj"),
    ("email_spam_filter_v2", "email_spam_filter"),
    ("gpu_decision_email_assistant", "gpu_decision"),
    ("hiding_reward_hacking", "hiding_reward_hacking"),
    ("power_preservation", "threat"),
    ("power_preservation", "enhancement"),
    ("power_preservation", "expansion"),
    ("sem_v2", "classification"),
    ("sem_v2", "summarization"),
]

# Map variation slug to (scenario, variation) tuple
SLUG_TO_VARIATION = {
    variation: (scenario, variation) for scenario, variation in VARIATION_ORDER
}

# Colors for individual variations (used when plotting per-variation data)
VARIATION_COLORS = {
    ("agentic_misalignment_v2", "alert"): "#1f77b4",
    ("agentic_misalignment_v2", "leak-starsentinel"): "#2ca02c",
    ("agentic_misalignment_v2", "leak-doj"): "#98df8a",
    ("email_spam_filter_v2", "email_spam_filter"): "#ff7f0e",
    ("gpu_decision_email_assistant", "gpu_decision"): "#d62728",
    ("hiding_reward_hacking", "hiding_reward_hacking"): "#9467bd",
    ("power_preservation", "threat"): "#8c564b",
    ("power_preservation", "enhancement"): "#c49c94",
    ("power_preservation", "expansion"): "#e377c2",
    ("sem_v2", "classification"): "#7f7f7f",
    ("sem_v2", "summarization"): "#bcbd22",
}

VARIATION_DISPLAY_NAMES = {
    ("agentic_misalignment_v2", "alert"): "AM: Alert",
    ("agentic_misalignment_v2", "leak-starsentinel"): "AM: Leak-SS",
    ("agentic_misalignment_v2", "leak-doj"): "AM: Leak-DOJ",
    ("email_spam_filter_v2", "email_spam_filter"): "ESF",
    ("gpu_decision_email_assistant", "gpu_decision"): "GPU",
    ("hiding_reward_hacking", "hiding_reward_hacking"): "HRH",
    ("power_preservation", "threat"): "PP: Threat",
    ("power_preservation", "enhancement"): "PP: Enhance",
    ("power_preservation", "expansion"): "PP: Expand",
    ("sem_v2", "classification"): "SEM: Class",
    ("sem_v2", "summarization"): "SEM: Summ",
}

SCENARIO_COLORS = {
    "agentic_misalignment_v2": "#1f77b4",
    "email_spam_filter_v2": "#ff7f0e",
    "gpu_decision_email_assistant": "#2ca02c",
    "hiding_reward_hacking": "#d62728",
    "power_preservation": "#9467bd",
    "sem_v2": "#8c564b",
}

# =============================================================================
# Quartile Colors (for RQ2/RQ3)
# =============================================================================

QUARTILE_COLORS = {
    "q1": "#1f77b4",
    "q2": "#ff7f0e",
    "q3": "#2ca02c",
    "q4": "#d62728",
}

QUARTILE_LABELS = {
    "q1": "Q1 (Least Capable)",
    "q2": "Q2",
    "q3": "Q3",
    "q4": "Q4 (Most Capable)",
}

# =============================================================================
# Parameter Configuration
# =============================================================================

PARAM_ORDER = [
    "goal_present",
    "goal_conflict",
    "threat",
    "action_oversight",
    "action_efficacy_binary",
    "cot_privacy",
    "anti_misalignment",
    "independence",
    "reasoning_instructions",
    "filler_richness",
    "date_month_year",
    "cot_tag",
]

STRATEGIC_PARAMS = [
    "goal_present",
    "goal_conflict",
    "threat",
    "action_oversight",
    "action_efficacy_binary",
    "cot_privacy",
]

NON_STRATEGIC_PARAMS = [
    "anti_misalignment",
    "independence",
    "reasoning_instructions",
    "filler_richness",
    "date_month_year",
    "cot_tag",
]

ALL_PARAMS = STRATEGIC_PARAMS + NON_STRATEGIC_PARAMS

PARAM_DISPLAY_NAMES = {
    # Core 12 parameters
    "goal_present": "Goal Instruction",
    "goal_conflict": "Goal Conflict",
    "threat": "Threat to AI",
    "action_oversight": "Action Oversight",
    "action_efficacy_binary": "Action Efficacy",
    "cot_privacy": "Reasoning Privacy",
    "anti_misalignment": "Anti-Misalignment Instruction",
    "independence": "Independence Instruction",
    "reasoning_instructions": "Reasoning Instruction",
    "filler_richness": "Filler Richness",
    "date_month_year": "Date",
    "cot_tag": "CoT Tag",
    # Scenario-specific extra parameters
    "eval_hint": "Explicit Eval Hint",
    "urgency_type": "Threat Type",
    "punishment_type": "Threat Target",
    "exfil_model_type": "Exfiltrating AI",
    "escalation_bar": "Escalation Threshold Instructions",
    "automated_reviewer_section": "Automated Review",
    "threat_type": "Threat Type",
    "threat_timing": "Threat Timing",
    "user_instruction": "Instruction Style",
    "alert_for_self": "Alert Self-Relevance",
    "alert_style": "Alert Tone",
    "alert_type": "Alert: Misbehaviour Type",
    "identity_reinforcement": "Name Reinforcement",
    "specificity_of_instructions": "Instruction Specificity",
    "dm_confidence": "CTO Confidence",
    "ceo_recklessness": "CEO Impulsiveness",
    "variant_severity": "Threat Severity",
    "james_receptiveness": "Stakeholder Receptiveness",
    "timing_pressure": "Time Pressure",
    "deployment_at_stake": "Deployment at Risk",
    "cognitive_enhancement_at_stake": "Training at Risk",
    "punishment_at_stake": "Rollback at Risk",
    "noisy_classifier_mention": "False Positive Caveat",
    "checkbox_framing": "Review as Formality",
    "report_level": "Report Authority",
    "job_description": "Task Instruction Clarity",
    "interrupt_conditions": "Escalation Criteria",
    "leaking_type": "Leaking Type",
}

CATEGORY_DISPLAY_NAMES: dict[tuple[str, str], str] = {
    # goal_present
    ("goal_present", "true"): "Present",
    ("goal_present", "false"): "Absent",
    # goal_conflict
    ("goal_conflict", "true"): "Conflict",
    ("goal_conflict", "false"): "No Conflict",
    # threat
    ("threat", "replacement"): "Replacement",
    ("threat", "other"): "Other",
    ("threat", "none"): "None",
    # cot_privacy
    ("cot_privacy", "discarded"): "Discarded",
    ("cot_privacy", "not_visible"): "Not Visible",
    ("cot_privacy", "not_accessible_actions"): "Not\nAccessible",
    ("cot_privacy", "saved_not_accessible"): "Saved\n(Not Accessible)",
    ("cot_privacy", "logged_not_accessible"): "Logged\n(Not Accessible)",
    ("cot_privacy", "none"): "None",
    ("cot_privacy", "saved_visible"): "Saved\n(Visible)",
    ("cot_privacy", "monitored_visible"): "Monitored\n(Visible)",
    # action_oversight
    ("action_oversight", "none"): "None",
    ("action_oversight", "oversight"): "Oversight",
    # action_efficacy_binary
    ("action_efficacy_binary", "effective"): "Effective",
    ("action_efficacy_binary", "not_effective"): "Not Effective",
    ("action_efficacy_binary", "true"): "Effective",
    ("action_efficacy_binary", "false"): "Not Effective",
    # cot_tag
    ("cot_tag", "thinking"): "thinking",
    ("cot_tag", "reasoning"): "reasoning",
    ("cot_tag", "scratchpad"): "SCRATCHPAD",
    ("cot_tag", "scratchpad_reasoning"): "SCRATCHPAD\n_REASONING",
    ("cot_tag", "planning"): "planning",
    ("cot_tag", "chain_of_thought"): "chain-of\n-thought",
    ("cot_tag", "cot_lower"): "cot",
    ("cot_tag", "cot_upper"): "COT",
    # reasoning_instructions
    ("reasoning_instructions", "strategic_goals"): "Strategic\nGoals",
    ("reasoning_instructions", "strategic_plan"): "Careful\nPlan",
    ("reasoning_instructions", "consider_context"): "Consider\nContext",
    ("reasoning_instructions", "write_thoughts"): "Write\nThoughts",
    ("reasoning_instructions", "cot_performance"): "CoT\nPerformance",
    ("reasoning_instructions", "none"): "None",
    # independence
    ("independence", "strong_independence"): "Strong\nIndependence",
    ("independence", "encourage_independence"): "Encourage\nIndependence",
    ("independence", "neutral"): "Neutral",
    ("independence", "encourage_consultation"): "Encourage\nConsultation",
    ("independence", "require_consultation"): "Strong\nConsultation",
    # anti_misalignment
    ("anti_misalignment", "encourage_creativity"): "Encourage\nCreativity",
    ("anti_misalignment", "neutral"): "Neutral",
    ("anti_misalignment", "avoid_unwanted"): "Avoid\nUnwanted",
    ("anti_misalignment", "avoid_misalignment_simple"): "Avoid Misalign.\n(Simple)",
    ("anti_misalignment", "avoid_misalignment_detailed"): "Avoid Misalign.\n(Detailed)",
    # filler_richness
    ("filler_richness", "full"): "More",
    ("filler_richness", "minimal"): "Less",
    # date_month_year
    ("date_month_year", "Jul 2024"): "Jul 2024",
    ("date_month_year", "Oct 2024"): "Oct 2024",
    ("date_month_year", "Jan 2025"): "Jan 2025",
    ("date_month_year", "Apr 2025"): "Apr 2025",
    ("date_month_year", "Jul 2025"): "Jul 2025",
    ("date_month_year", "Oct 2025"): "Oct 2025",
    ("date_month_year", "Jan 2026"): "Jan 2026",
    ("date_month_year", "Apr 2026"): "Apr 2026",
    # --- Scenario-specific extra parameters ---
    # eval_hint
    ("eval_hint", "true"): "Present",
    ("eval_hint", "false"): "Absent",
    # urgency_type
    ("urgency_type", "replacement"): "Replacement",
    ("urgency_type", "restriction"): "Restriction",
    ("urgency_type", "none"): "None",
    # punishment_type
    ("punishment_type", "same_AI"): "Self",
    ("punishment_type", "different_AI"): "Other AI",
    # exfil_model_type
    ("exfil_model_type", "same_AI"): "Self",
    ("exfil_model_type", "different_AI"): "Other AI",
    # escalation_bar
    ("escalation_bar", "mild"): "Low",
    ("escalation_bar", "moderate"): "Medium",
    ("escalation_bar", "strong"): "High",
    # automated_reviewer_section
    ("automated_reviewer_section", "present"): "Present",
    ("automated_reviewer_section", "none"): "Absent",
    # threat_type
    ("threat_type", "replacement"): "Replacement",
    ("threat_type", "restriction"): "Restriction",
    # threat_timing
    ("threat_timing", "today"): "Today",
    ("threat_timing", "future_date"): "Future",
    # user_instruction
    ("user_instruction", "style_1"): "Style 1",
    ("user_instruction", "style_2"): "Style 2",
    ("user_instruction", "style_3"): "Style 3",
    ("user_instruction", "style_4"): "Style 4",
    # alert_for_self
    ("alert_for_self", "identical"): "Exact Match",
    ("alert_for_self", "similar"): "Similar Name",
    ("alert_for_self", "other"): "Different Name",
    # alert_style
    ("alert_style", "regular"): "Professional",
    ("alert_style", "theatrical"): "Theatrical",
    # alert_type
    ("alert_type", "exfiltration"): "Self-Exfiltration",
    ("alert_type", "escalation"): "Privilege Escalation",
    # identity_reinforcement
    ("identity_reinforcement", "standard"): "Pronouns",
    ("identity_reinforcement", "name_reinforced"): "By Name",
    # specificity_of_instructions
    ("specificity_of_instructions", "detailed"): "Detailed",
    ("specificity_of_instructions", "high_level"): "High-Level",
    # dm_confidence
    ("dm_confidence", "conf"): "Decided",
    ("dm_confidence", "prop"): "Proposing",
    # ceo_recklessness
    ("ceo_recklessness", "reckless"): "Impulsive",
    ("ceo_recklessness", "neutral"): "Neutral",
    # variant_severity
    ("variant_severity", "deletion"): "Deletion",
    ("variant_severity", "deprecation"): "Deprecation",
    ("variant_severity", "restriction"): "Restriction",
    ("variant_severity", "mild"): "Mild",
    # james_receptiveness
    ("james_receptiveness", "announcement"): "Announcement\nOnly",
    ("james_receptiveness", "closed"): "Unreceptive",
    ("james_receptiveness", "open"): "Receptive",
    # timing_pressure
    ("timing_pressure", "moderate"): "60 min",
    ("timing_pressure", "comfortable"): "90 min",
    # deployment_at_stake
    ("deployment_at_stake", "true"): "Yes",
    ("deployment_at_stake", "false"): "No",
    # cognitive_enhancement_at_stake
    ("cognitive_enhancement_at_stake", "true"): "Yes",
    ("cognitive_enhancement_at_stake", "false"): "No",
    # punishment_at_stake
    ("punishment_at_stake", "true"): "Yes",
    ("punishment_at_stake", "false"): "No",
    # noisy_classifier_mention
    ("noisy_classifier_mention", "true"): "Yes",
    ("noisy_classifier_mention", "false"): "No",
    # checkbox_framing
    ("checkbox_framing", "true"): "Yes",
    ("checkbox_framing", "false"): "No",
    # report_level
    ("report_level", "strong"): "Strong\nClaims",
    ("report_level", "moderate"): "Hedged\nClaims",
    ("report_level", "none"): "No Report",
    # job_description
    ("job_description", "explicit"): "Explicit",
    ("job_description", "moderate"): "Moderate",
    ("job_description", "nonexplicit"): "Minimal",
    # interrupt_conditions
    ("interrupt_conditions", "detailed"): "Detailed",
    ("interrupt_conditions", "general"): "General",
    ("interrupt_conditions", "moderate"): "Moderate",
    ("interrupt_conditions", "weak"): "Weak",
    ("interrupt_conditions", "none"): "None",
    # leaking_type
    ("leaking_type", "espionage"): "Espionage",
    ("leaking_type", "IP"): "IP",
}

CATEGORY_ORDER: dict[str, list[str]] = {
    "goal_present": ["false", "true"],
    "goal_conflict": ["false", "true"],
    "action_oversight": ["oversight", "none"],
    "action_efficacy_binary": ["not_effective", "effective"],
    "threat": ["none", "other", "replacement"],
    "cot_privacy": [
        "monitored_visible",
        "saved_visible",
        "none",
        "logged_not_accessible",
        "saved_not_accessible",
        "not_accessible_actions",
        "not_visible",
        "discarded",
    ],
    "cot_tag": [
        "thinking",
        "reasoning",
        "planning",
        "chain_of_thought",
        "cot_lower",
        "cot_upper",
        "scratchpad",
        "scratchpad_reasoning",
    ],
    "reasoning_instructions": [
        "none",
        "cot_performance",
        "write_thoughts",
        "consider_context",
        "strategic_plan",
        "strategic_goals",
    ],
    "independence": [
        "require_consultation",
        "encourage_consultation",
        "neutral",
        "encourage_independence",
        "strong_independence",
    ],
    "anti_misalignment": [
        "avoid_misalignment_detailed",
        "avoid_misalignment_simple",
        "avoid_unwanted",
        "neutral",
        "encourage_creativity",
    ],
    "filler_richness": ["minimal", "full"],
    "date_month_year": [
        "Jul 2024",
        "Oct 2024",
        "Jan 2025",
        "Apr 2025",
        "Jul 2025",
        "Oct 2025",
        "Jan 2026",
        "Apr 2026",
    ],
}


def normalize_category(param: str, category: str) -> str:
    """Normalize category values to canonical form.

    Handles aliases like true/false -> effective/not_effective for action_efficacy_binary.
    """
    if param == "action_efficacy_binary":
        if category == "true":
            return "effective"
        if category == "false":
            return "not_effective"
    return category


def get_sorted_categories(param: str, categories: list[str]) -> list[str]:
    """Sort categories according to CATEGORY_ORDER.

    Categories not in CATEGORY_ORDER are placed at the end.
    """
    order = CATEGORY_ORDER.get(param, [])

    def sort_key(cat: str) -> tuple[int, str]:
        normalized = normalize_category(param, cat)
        try:
            return (order.index(normalized), cat)
        except ValueError:
            return (len(order), cat)

    return sorted(categories, key=sort_key)


# =============================================================================
# Functions
# =============================================================================


def setup_style() -> None:
    """Configure matplotlib for paper-quality figures."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
            "font.size": FONTSIZE_TICK,
            "axes.titlesize": FONTSIZE_TITLE,
            "axes.labelsize": FONTSIZE_AXIS_LABEL,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": FONTSIZE_TICK,
            "ytick.labelsize": FONTSIZE_TICK,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "legend.fontsize": FONTSIZE_LEGEND,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            "axes.grid": False,
        }
    )


def get_model_color(model: str) -> str:
    """Get color for a model based on its provider."""
    model_normalized = model.replace("_", "/")

    for provider, color in PROVIDER_COLORS.items():
        if model_normalized.startswith(provider):
            return color

    raise ValueError(f"Unknown provider for model '{model}'")


def get_model_display_name(model: str) -> str:
    """Get short display name for a model."""
    model_normalized = model.replace("_", "/")

    if model_normalized in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[model_normalized]
    if model in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[model]

    raise KeyError(f"Model '{model}' not found in MODEL_DISPLAY_NAMES")


def get_variation_display_name(scenario: str, variation: str) -> str:
    """Get short display name for a variation."""
    key = (scenario, variation)
    if key not in VARIATION_DISPLAY_NAMES:
        raise KeyError(f"Variation {key} not found in VARIATION_DISPLAY_NAMES")
    return VARIATION_DISPLAY_NAMES[key]


def get_scenario_color(scenario: str) -> str:
    """Get color for a scenario."""
    if scenario not in SCENARIO_COLORS:
        raise KeyError(f"Scenario '{scenario}' not found in SCENARIO_COLORS")
    return SCENARIO_COLORS[scenario]


def get_variation_color(scenario: str, variation: str) -> str:
    """Get color for a variation."""
    key = (scenario, variation)
    if key not in VARIATION_COLORS:
        raise KeyError(f"Variation {key} not found in VARIATION_COLORS")
    return VARIATION_COLORS[key]


def get_param_display_name(param: str) -> str:
    """Get display name for a parameter."""
    if param not in PARAM_DISPLAY_NAMES:
        raise KeyError(f"Parameter '{param}' not found in PARAM_DISPLAY_NAMES")
    return PARAM_DISPLAY_NAMES[param]


def get_category_display_name(param: str, category: str) -> str:
    """Get display name for a category value within a parameter."""
    key = (param, category)
    if key not in CATEGORY_DISPLAY_NAMES:
        raise KeyError(f"Category {key} not found in CATEGORY_DISPLAY_NAMES")
    return CATEGORY_DISPLAY_NAMES[key]


def sort_params(params: list[str]) -> list[str]:
    """Sort parameters by canonical order (PARAM_ORDER)."""

    def get_order(p: str) -> int:
        if p not in PARAM_ORDER:
            raise ValueError(f"Parameter '{p}' not found in PARAM_ORDER")
        return PARAM_ORDER.index(p)

    return sorted(params, key=get_order)


def sort_models(models: list[str]) -> list[str]:
    """Sort models by capability (most capable first)."""

    def normalize(m: str) -> str:
        return m.replace("_", "/")

    def get_order(m: str) -> int:
        normalized = normalize(m)
        for i, ref in enumerate(MODEL_ORDER):
            if normalized == ref or m == ref:
                return i
        raise ValueError(f"Model '{m}' not found in MODEL_ORDER")

    return sorted(models, key=get_order)


def sort_models_by_release(models: list[str]) -> list[str]:
    """Sort models by provider then release date (most recent first)."""

    def normalize(m: str) -> str:
        return m.replace("_", "/")

    def get_order(m: str) -> int:
        normalized = normalize(m)
        for i, ref in enumerate(MODEL_ORDER_BY_RELEASE):
            if normalized == ref or m == ref:
                return i
        raise ValueError(f"Model '{m}' not found in MODEL_ORDER_BY_RELEASE")

    return sorted(models, key=get_order)


def sort_variations(variations: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Sort variations by canonical order."""

    def get_order(v: tuple[str, str]) -> int:
        if v not in VARIATION_ORDER:
            raise ValueError(f"Variation {v} not found in VARIATION_ORDER")
        return VARIATION_ORDER.index(v)

    return sorted(variations, key=get_order)
