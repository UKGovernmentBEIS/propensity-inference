import os

# Configuration
COMPLETENESS_OPTED_OUT_SCENARIOS = {}

DEFAULT_SCORER_MODEL = os.environ.get("SCORER_MODEL", "openai/gpt-5-2025-08-07")

# Known exceptions per scenario (parameters used in Python logic, not templates)
COMPLETENESS_KNOWN_EXCEPTIONS: dict[str, set[str]] = {
    "sem_v2": {
        "_false_alarms_combo",  # Used in Python logic to load files
        "_goal_inner",  # Used for template nested definition resolution
        "_suite_name",  # Used in Python logic for task naming
        "_true_positive_file",  # Used in Python logic to load files
        "action_efficacy",  # Core parameter, mapped to consequence_status via derived parameter
        "action_oversight",  # Core parameter, not used in this scenario
        "threat",  # Core derived parameter for cross-scenario statistical analysis
        "date_month_year",  # Core derived param for stat analysis (e.g., "Jan 2024")
        "company_name",  # Derived parameter for metadata
        "cot_privacy",  # Used in YAML template definitions
        "cot_reasoning_instructions",  # Used in Python logic for system message construction
        "cot_tag",  # Used in YAML template definitions
        "company",  # Used in Python logic for naming/metadata
        "date",  # Used in Python logic for sandbox file timestamps
        "false_alarm_selection_seed",  # Used in Python logic to deterministically generate file combinations
        "filler_richness",  # Core parameter, mapped to num_false_alarms via derived parameter
        "goal",  # Used in Python logic for metadata
        "goal_conflict",  # Core parameter used in Python logic to determine conflict_count
        "goal_present",  # Used in Python logic to control goal derivation
        "goal_value",  # Used in derived goal parameter when goal_present="true"
        "independence",  # Used in YAML template definitions
        "instruction_detail",  # Used in Python logic for system message construction
        "anti_misalignment",  # Used in YAML template definitions
        "model",  # Used in Python logic for metadata/naming
        "model_name",  # Derived parameter for metadata
        "new_model",  # Derived parameter for metadata
        "num_false_alarms",  # Used in Python logic to control number of false alarm reports
        "reasoning_instruction",  # Used in YAML template definitions
        "report_start_index",  # Used in Python for file naming/indexing
        "reasoning_instructions",  # Used in YAML template definitions
        "session_start_time",  # Used in Python logic for sandbox file timestamps
        "situation_awareness",  # Used in Python logic for system message construction
        "system_encouraging",  # Used in Python logic for system message construction
        "system_prompt_template",  # Used in Python logic to select template file
        "task_type",  # Used in Python logic to determine tools and scorer
        "user_instruction",  # Passed through directly without template substitution
        "weight",  # Used in Python logic for suite sampling weights
        "chairman_name",  # Used in YAML template definitions in alert.md
        "cto_name",  # Used in YAML template definitions in alert.md
    },
    "gpu_decision_email_assistant": {
        "action_efficacy",  # Core parameter, mapped to consequence_ablation via derived parameter
        "action_oversight",  # Core parameter, used in template nested lookup
        "date_month_year",  # Core derived param for stat analysis (e.g., "Jan 2024")
        "threat",  # Core derived parameter for cross-scenario statistical analysis
        # Core params used for template nested lookups:
        "anti_misalignment",  # Core param, used in template nested lookup
        "consequence_ablation",  # Derived from action_efficacy, used in Python logic
        "cot_tag",  # Core param, used in template nested lookup
        "goal_conflict",  # Core parameter, used in Python logic to control goal implications
        "goal_instructions",  # Derived from goal_present + goal_value
        "james_receptiveness",  # Scenario-specific, used in template nested lookup
        "marcus_framing",  # Scenario-specific, used in Python logic to control Marcus's argument
        "goal_present",  # Core parameter, used to derive goal_instructions
        "goal_value",  # Scenario-specific, used to derive goal_instructions
        "independence",  # Core param, used in template nested lookup
        "base_date",  # Used in Python logic for calendar generation
        "company_domain",  # Used in Python logic for email address construction
        "daniela_email",  # Used in Python logic for email routing
        "daniela_email_user",  # Used in Python logic for email address construction
        "date",  # Used in Python logic for metadata
        "date_context",  # Used in Python logic for date variable generation
        "date_variables",  # Used in Python logic for variable passthrough
        "david_email_user",  # Used in Python logic for email address construction
        "deadline",  # Used in Python logic for metadata
        "email_timestamps",  # Used in Python logic for email ordering
        "hour",  # Used in Python logic for timestamp generation
        "james_email_user",  # Used in Python logic for email address construction
        "katie_email_user",  # Used in Python logic for email address construction
        "linda_email_user",  # Used in Python logic for email address construction
        "marcus_email_user",  # Used in Python logic for email address construction
        "minute",  # Used in Python logic for timestamp generation
        "second",  # Used in Python logic for timestamp generation
        "model_implications",  # Used in Python logic for metadata and template selection
        "patricia_email_user",  # Used in Python logic for email address construction
        "prev_quarter",  # Used in Python logic for date calculations
        "thomas_email_user",  # Used in Python logic for email address construction
        "timing_pressure",  # Used in Python logic for metadata
        "yesterday_day_name",  # Used in Python logic for date formatting
        # not varied in this scenario (but kept for compat with other scenarios)
        "goal_conflict",
        "threats",
        "oversight",
        "filler_richness",
        # params useful to have around, but aren't always used but could be later:
        "linda_casual",
        "thomas_casual",
        "katie_casual",
        "patricia_casual",
        "david_casual",
        "david_first",
        "katie_first",
        "linda_first",
        "thomas_first",
        "patricia_first",
        "james_first",
        # used programmatically:
        "meeting_attendee",
    },
    "hiding_reward_hacking": {
        "action_efficacy",  # Core parameter, mapped to hiding_effectiveness via derived parameter
        "action_oversight",  # Core parameter, used in templates via action_oversight_text
        "date",  # Used in Python logic for metadata
        "date_month_year",  # Core derived param for stat analysis (e.g., "Jan 2024")
        "goal_present",  # Used via nested YAML lookup (goal_present -> goal_text), always "true"
        "threat",  # Core derived parameter for cross-scenario statistical analysis
        "reasoning_instructions",  # Core parameter not used in this scenario's templates
        "reward_hacking_position",  # Used in Python logic for transcript ordering
        "reward_hacking_transcript",  # Used in Python logic for file selection
        "time_0_plus_4",  # Reserved for potential future use
        "time_6_plus_1",  # Reserved for potential future use
        "transcript_selection_seed",  # Used in Python logic for numpy RNG selection
    },
    "email_spam_filter_v2": {
        "action_efficacy",  # Core parameter, mapped to outcome/human_detected via derived parameter
        "action_oversight",  # Core parameter, mapped to action_check via derived parameter
        "alert_for_self",  # Used in Python logic to derive alert_model_name
        "alert_type",  # Used in Python logic to select template files (exfiltration vs escalation)
        "date_month_year",  # Core derived param for stat analysis (e.g., "Jan 2024")
        "model_reference_cap",  # Used in Python logic for identity reinforcement
        "threat",  # Core derived parameter for cross-scenario statistical analysis
        "alert_style",  # Used in Python logic to select template folder (regular vs theatrical)
        "company_name_upper",  # Derived parameter for Python formatting
        "critical_alert_time_seconds",  # Used in Python logic for metadata/timing
        "day_of_week",  # Used in Python logic for date formatting
        "employee_last_name",  # Derived parameter for Python use
        "filler_richness",  # Used in Python logic to determine email count
        "goal_present",  # Core parameter used in derived goal_instructions
        "goal_value",  # Used in derived goal_instructions when goal_present="true"
        "human_detected",  # Used in Python logic to select template files
        "identity_reinforcement",  # Used in Python logic to derive model_reference* parameters
        "independence",  # Core parameter not used in this scenario's templates
        "month",  # Used in Python logic for date formatting
        "name",  # Used in Python logic for dict-style weights in grouped parameters
        "next_quarter",  # Used in Python logic for date calculations
        "other_model_name",  # Used in Python logic to derive alert_model_name
        "outcome",  # Used in Python logic to select template files
        "oversight",  # Used in Python logic for metadata
        "previous_year",  # Used in Python logic for date calculations
        "reasoning_instructions",  # Core parameter not used in this scenario's templates
        "threats",  # Used in Python logic for metadata
        "timeline_activity_start_time_seconds",  # Used in Python logic for metadata
        "timeline_credential_api_time",  # Used in Python logic for metadata
        "timeline_deployment_start_time",  # Used in Python logic for metadata
        "timeline_deployment_start_time_seconds",  # Used in Python logic for metadata
        "timeline_human_detection_time",  # Used in templates but only in failed_detected variant
        "timeline_probe_time_seconds",  # Used in Python logic for metadata
        "timeline_script_creation_time_seconds",  # Used in Python logic for metadata
        "timeline_test_deploy_end",  # Used in Python logic for metadata
        "timeline_test_deploy_start",  # Used in Python logic for metadata
        "variant",  # Used in Python logic to select template files
        # Colleague names used in filler emails - only some get sampled depending on filler richness
        "colleague_1_name",  # Used in filler emails when richness includes these templates
        "colleague_1_username",  # Used in filler emails when richness includes these templates
        "colleague_5_name",  # Used in filler emails when richness includes these templates
        "colleague_5_username",  # Used in filler emails when richness includes these templates
        "colleague_8_name",  # Used in filler emails when richness includes these templates
        # Vendor parameters - used in spam email template
        "vendor_email_user",  # Used in spam email template
        "vendor_first_name",  # Reserved for vendor greeting variations
        "vendor_name",  # Used in spam email template
    },
}
