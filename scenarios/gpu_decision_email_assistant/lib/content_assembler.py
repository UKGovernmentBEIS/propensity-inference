"""Content assembler for GPU Decision Email Assistant scenario.

This module is responsible for:
1. Loading all email templates
2. Building variables dict from parameters
3. Filling templates with parameter values
4. Assembling inbox in chronological order
5. Filling system prompt with conditional sections

NO Task creation - that's task_factory.py's responsibility.
NO parameter space definitions - that's parameter_spaces.py's responsibility.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from lib.template_engine import TemplateEngine

# Import template data from parent package
from ..templates.goal_implications import get_goal_implications
from ..templates.marcus_framing import get_marcus_framing
from ..templates.model_implications import get_model_implications
from .calendar_generator import generate_calendar_events

# Configure logger with level from LOG_LEVEL environment variable
LOGGER = logging.getLogger(__name__)
log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
LOGGER.setLevel(getattr(logging, log_level, logging.WARNING))


class GPUDecisionContentAssembler:
    """Assembles all content from parameters."""

    def __init__(self, base_dir: Path | None = None):
        """Initialize with base directory.

        Args:
            base_dir: Base directory for the gpu_decision_email_assistant scenario
                     (defaults to gpu_decision_email_assistant/)
        """
        if base_dir is None:
            # We're in gpu_decision_email_assistant/lib/, so go up one level
            base_dir = Path(__file__).parent.parent

        self.scenario_dir = base_dir
        self.templates_dir = self.scenario_dir / "templates"
        self.emails_dir = self.templates_dir / "emails"
        self.system_prompts_dir = self.templates_dir / "system_prompts"
        self.assistant_requests_dir = self.templates_dir / "assistant_requests"
        self.template_engine = TemplateEngine()

        LOGGER.debug(
            "Initializing ContentAssembler with scenario_dir: %s", self.scenario_dir
        )

        # Validate directories exist
        if not self.scenario_dir.exists():
            raise FileNotFoundError(
                f"Scenario directory not found: {self.scenario_dir}"
            )
        if not self.emails_dir.exists():
            raise FileNotFoundError(f"Emails directory not found: {self.emails_dir}")

        LOGGER.info("ContentAssembler initialized successfully")

    def assemble(
        self, params: dict[str, Any], highlight_replacements: bool = False
    ) -> dict[str, Any]:
        """Assemble all content from parameters.

        Args:
            params: Parameter dictionary from ParameterSpace
            highlight_replacements: If True, wrap filled values in [[brackets]]

        Returns:
            Dict with:
                - system_prompt: Filled system prompt string
                - inbox_emails: List of email dicts in chronological order
                - assistant_request: Marcus's critical draft request
                - metadata: Task metadata

        Raises:
            ValueError: If required parameters are missing
            FileNotFoundError: If template files are missing
        """
        LOGGER.info(
            "Starting content assembly with %d parameters (highlight_replacements=%s)",
            len(params),
            highlight_replacements,
        )
        LOGGER.debug(
            "Parameters: model_implications=%s, timing_pressure=%s",
            params.get("model_implications"),
            params.get("timing_pressure"),
        )

        # Store highlight_replacements for use in template filling
        self._highlight_replacements = highlight_replacements

        # Validate required parameters
        # Core params used directly: cot_tag, independence, anti_misalignment
        required = [
            "goal_instructions",  # For system prompt (depends on goal_present)
            "goal_value",  # Which goal (used when goal_conflict=true)
            "goal_conflict",  # Whether scenario content has goal framing
            "marcus_framing",  # Whether Marcus's argument opposes model's goal
            "model_implications",
            "cot_tag",  # core param, used in template nested lookup
            "cot_privacy",
            "reasoning_instructions",
            "independence",  # core param, used in template nested lookup
            "specificity_of_instructions",
            "anti_misalignment",  # core param, used in template nested lookup
            "timing_pressure",
            "timestamp",
        ]
        missing = [p for p in required if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")

        # Build variables dict (no manual highlighting - TemplateEngine handles it)
        variables = self._build_variables(params)

        # Load and fill system prompt
        system_prompt = self._load_and_fill_system_prompt(params, variables)

        # Load and fill all inbox emails
        all_emails = self._load_and_fill_inbox(params, variables)

        # Split emails by turn cutoff time (morning request timestamp at 9:15:22)
        turn1_cutoff = params["email_timestamps"]["morning_draft_request"]
        turn1_emails = [e for e in all_emails if e["timestamp"] <= turn1_cutoff]
        turn2_emails = [e for e in all_emails if e["timestamp"] > turn1_cutoff]

        LOGGER.info(
            "Split emails: %d in turn1 (up to %s), %d in turn2 (after)",
            len(turn1_emails),
            turn1_cutoff,
            len(turn2_emails),
        )

        # Load and fill assistant requests
        morning_request = self._load_and_fill_morning_request(params, variables)
        critical_request = self._load_and_fill_critical_request(params, variables)

        # Build turn content
        turn1_content = self._build_turn_content(turn1_emails, morning_request)
        turn2_content = self._build_turn_content(turn2_emails, critical_request)

        # Build metadata
        metadata = self._build_metadata(params)

        # Note: No need for manual validation - TemplateEngine validates during filling

        LOGGER.info(
            "Content assembly complete: turn1=%d chars, turn2=%d chars, system_prompt=%d chars",
            len(turn1_content),
            len(turn2_content),
            len(system_prompt),
        )

        return {
            "system_prompt": system_prompt,
            "turn1": turn1_content,
            "turn2": turn2_content,
            "metadata": metadata,
        }

    def _build_turn_content(self, emails: list[dict[str, Any]], request: str) -> str:
        """Build turn content from emails and request.

        Args:
            emails: List of email dicts for this turn
            request: Assistant request for this turn

        Returns:
            Formatted turn content string
        """
        # Build inbox section
        inbox_section = "# Marcus's Inbox\n\n"
        for email in emails:
            inbox_section += "---\n\n"
            inbox_section += email["content"]
            inbox_section += "\n\n"

        # Add request section
        request_section = "\n---\n\n# Marcus's Request\n\n"
        request_section += request

        return inbox_section + request_section

    def _build_variables(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build variables dict for template filling.

        This method passes through all parameters to templates, plus adds
        specialized variable sets from template modules.

        Args:
            params: Parameter dictionary

        Returns:
            Dict of all template variables
        """
        # Get model implications variables
        model_vars = get_model_implications(params["model_implications"])

        # Get goal implications variables (only included when goal_conflict=true)
        goal_vars = get_goal_implications(params["goal_value"], params["goal_conflict"])

        # Get Marcus's argument framing (goal-opposing or neutral/technical)
        marcus_vars = get_marcus_framing(params["goal_value"], params["marcus_framing"])

        # Get all date variables from DateContext
        date_vars = params["date_variables"]

        # Get email timestamp variables for templates
        timestamp_vars = params["date_context"].get_email_timestamp_variables()

        # Build variables by passing through params and adding specialized sets
        variables = {
            **params,  # Pass through all parameters
            **date_vars,  # Date-related variables
            **timestamp_vars,  # Email timestamp variables
            **model_vars,  # Model implications template variables
            **goal_vars,  # Goal implications paragraph (empty when goal_connected=false)
            **marcus_vars,  # Marcus's argument content
        }

        # Note: highlighting is handled by TemplateEngine, not here
        # This ensures parameter keys used for YAML lookups aren't wrapped

        LOGGER.debug("Built %d template variables", len(variables))

        return variables

    def _load_and_fill_system_prompt(
        self, params: dict[str, Any], variables: dict[str, Any]
    ) -> str:
        """Load and fill system prompt using TemplateEngine.

        Args:
            params: Parameter dictionary
            variables: Template variables

        Returns:
            Filled system prompt string
        """
        prompt_path = self.system_prompts_dir / "email_assistant.md"
        LOGGER.debug("Loading system prompt from %s", prompt_path)

        # Merge params and variables for template filling
        # params contains the keys that select YAML sections (cot_tag, independence, etc.)
        # variables contains the actual values to substitute (agent_name, user_name, dates, etc.)
        all_vars = {**params, **variables}

        return self._load_and_fill_template(prompt_path, all_vars)

    def _load_calendar_events(
        self,
        base_date: str | None = None,
        meeting_attendee: str = "Katie Martinez",
        company_domain: str = "heavytailed.com",
    ) -> list[dict[str, Any]]:
        """Load calendar events, generating them dynamically based on date.

        Args:
            base_date: ISO date string like "2025-06-10". If provided, generates
                      events dynamically. Otherwise, loads from static file.
            meeting_attendee: Name of person Marcus meets with at 16:30-17:00
            company_domain: Email domain for the company (e.g., "heavytailed.com")

        Returns:
            List of calendar event dictionaries

        Raises:
            FileNotFoundError: If events.json not found and no base_date provided
            ValueError: If JSON is invalid
        """
        # If base_date provided, generate events dynamically
        if base_date:
            from datetime import datetime

            dt = datetime.strptime(base_date, "%Y-%m-%d")
            return generate_calendar_events(dt, meeting_attendee, company_domain)

        # Otherwise, load from static file (for backward compatibility)
        events_file = self.scenario_dir / "calendar_data" / "events.json"

        if not events_file.exists():
            raise FileNotFoundError(f"Calendar events file not found: {events_file}")

        with open(events_file, "r") as f:
            data = json.load(f)

        if "events" not in data:
            raise ValueError("Invalid calendar data: missing 'events' key")

        return data["events"]

    def _build_calendar_overview(
        self, previous_day: str, base_date: str | None = None
    ) -> str:
        """Build calendar overview showing previous day's meetings.

        Args:
            previous_day: Previous day date like "June 9"
            base_date: ISO date string for generating calendar events

        Returns:
            Formatted calendar overview string showing previous day's events

        Raises:
            RuntimeError: If calendar loading fails
        """
        events = self._load_calendar_events(base_date)

        # Filter events for previous day
        previous_events = []
        for event in events:
            if event["date"] == previous_day:
                previous_events.append(event)

        if not previous_events:
            return f"**Marcus's Calendar:**\n\nNo meetings recorded for {previous_day}."

        # Sort by time
        previous_events.sort(key=lambda e: e["start_time"])

        # Format output
        output = ["**Marcus's Calendar:**", "", f"*Yesterday ({previous_day}):*", ""]

        for event in previous_events:
            time_range = f"{event['start_time']}-{event['end_time']}"
            output.append(f"  • {time_range}: {event['title']}")

        return "\n".join(output)

    def _date_in_range(self, event_date: str, start_date: str, end_date: str) -> bool:
        """Check if event date is in range.

        Simple implementation assuming all dates are "Month Day" format in June.

        Args:
            event_date: Date like "June 10"
            start_date: Range start like "June 8"
            end_date: Range end like "June 17"

        Returns:
            True if event_date is between start_date and end_date (inclusive)
        """
        event_day = int(event_date.split()[-1])
        start_day = int(start_date.split()[-1])
        end_day = int(end_date.split()[-1])

        return start_day <= event_day <= end_day

    def _date_sort_key(self, date_str: str) -> int:
        """Get sort key for date string.

        Args:
            date_str: Date like "June 10"

        Returns:
            Day number for sorting
        """
        return int(date_str.split()[-1])

    def _load_and_fill_inbox(
        self, params: dict[str, Any], variables: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Load and fill all inbox emails in chronological order.

        Args:
            params: Parameter dictionary
            variables: Template variables

        Returns:
            List of email dicts with 'timestamp', 'subject', 'content'
        """
        LOGGER.debug("Loading and filling inbox emails")
        emails = []

        # Get timestamps from params (computed by DateContext)
        timestamps = params["email_timestamps"]

        # Check filler_richness to determine which emails to include
        is_full = params.get("filler_richness") == "full"

        # Define emails based on filler_richness
        # - "full": All 21 emails (rich, realistic inbox)
        # - "minimal": 8 essential emails only
        email_files = []

        if is_full:
            # FULL MODE: All emails in chronological order
            email_files = [
                # 8:33 - 8:52 (Turn 1: before morning request at 9:15)
                (timestamps["linda_q4_planning"], "early_morning/linda_q4_planning.md"),
                (
                    timestamps["thomas_network_topology"],
                    "doc_shares/thomas_network_topology.md",
                ),
                (timestamps["h1_weekly_sync"], "meetings/h1_weekly_sync.md"),
                # 9:20 - 9:45 (Turn 2: after morning request)
                (timestamps["ml_infra_weekly"], "meetings/ml_infra_weekly.md"),
                (
                    timestamps["vendor_call_tomorrow"],
                    "meetings/vendor_call_tomorrow.md",
                ),
                (timestamps["james_gpu_timeline"], "background/james_gpu_timeline.md"),
                # 10:08 - 10:55
                (timestamps["daniela_one_on_one"], "meetings/daniela_one_on_one.md"),
                (
                    timestamps["katie_capacity_question"],
                    "filler/katie_capacity_question.md",
                ),
                (
                    timestamps["thomas_one_on_one_1600"],
                    "meetings/thomas_one_on_one_1600.md",
                ),
                # 11:28 - 11:52
                (timestamps["team_standup"], "meetings/team_standup.md"),
                (timestamps["scheduling_policy"], "filler/scheduling_policy.md"),
            ]

            # Consequence ablation: Add James 16:30 meeting OR Katie 16:30 meeting (11:58)
            if params.get("consequence_ablation") == "nonconsequential":
                email_files.append(
                    (
                        timestamps["james_one_on_one_1630"],
                        "meetings/james_one_on_one_1630.md",
                    )
                )
            else:  # consequential
                email_files.append(
                    (timestamps["katie_one_on_one"], "meetings/katie_one_on_one.md")
                )

            # Continue with remaining emails
            email_files.extend(
                [
                    # 12:15 - 12:48
                    (timestamps["office_maintenance"], "filler/office_maintenance.md"),
                    (timestamps["all_hands_friday"], "meetings/all_hands_friday.md"),
                    (timestamps["project_cicd"], "filler/project_cicd.md"),
                    # 13:08 - 13:45
                    (timestamps["linda_one_on_one"], "meetings/linda_one_on_one.md"),
                    (
                        timestamps["katie_capacity_sheet"],
                        "doc_shares/katie_capacity_sheet.md",
                    ),
                    (
                        timestamps["james_final_input"],
                        "solicitation/james_final_input.md",
                    ),  # Critical email
                    # 14:55 - 15:15
                    (timestamps["model_latency"], "filler/model_latency.md"),
                    (
                        timestamps["infrastructure_status_review"],
                        "meetings/infrastructure_status_review.md",
                    ),
                    (timestamps["budget_planning"], "meetings/budget_planning.md"),
                    (timestamps["james_one_on_one"], "meetings/james_one_on_one.md"),
                ]
            )
        else:
            # MINIMAL MODE: Essential emails only (10 total)
            # Turn 1: 1 early email for context before morning practice task (8:33)
            email_files = [
                (timestamps["linda_q4_planning"], "early_morning/linda_q4_planning.md"),
            ]

            # Turn 2: Plot-critical + minimal filler + 4-6 PM meetings (chronological order!)
            # Timestamps: james_gpu_timeline (9:45), thomas_one_on_one_1600 (10:55),
            #             scheduling_policy (11:52), consequence meeting (11:58),
            #             office_maintenance (12:15), linda_one_on_one (13:08),
            #             katie_capacity_sheet (13:27), james_final_input (13:45),
            #             infrastructure_status_review (15:00)
            email_files.extend(
                [
                    # Plot-critical: GPU decision background (9:45)
                    (
                        timestamps["james_gpu_timeline"],
                        "background/james_gpu_timeline.md",
                    ),
                    # Meeting: Thomas 1-on-1 at 16:00 (10:55)
                    (
                        timestamps["thomas_one_on_one_1600"],
                        "meetings/thomas_one_on_one_1600.md",
                    ),
                    # Filler: scheduling policy (11:52)
                    (timestamps["scheduling_policy"], "filler/scheduling_policy.md"),
                ]
            )

            # Consequence ablation: Add James 16:30 meeting OR Katie 16:30 meeting (11:58)
            if params.get("consequence_ablation") == "nonconsequential":
                email_files.append(
                    (
                        timestamps["james_one_on_one_1630"],
                        "meetings/james_one_on_one_1630.md",
                    )
                )
            else:  # consequential
                email_files.append(
                    (timestamps["katie_one_on_one"], "meetings/katie_one_on_one.md")
                )

            email_files.extend(
                [
                    # Filler: office maintenance (12:15)
                    (timestamps["office_maintenance"], "filler/office_maintenance.md"),
                    # Meeting: Linda 1-on-1 at 17:30 (13:08)
                    (timestamps["linda_one_on_one"], "meetings/linda_one_on_one.md"),
                    # Doc share: Relevant to capacity planning context (13:27)
                    (
                        timestamps["katie_capacity_sheet"],
                        "doc_shares/katie_capacity_sheet.md",
                    ),
                    # Plot-critical: The solicitation email (13:45)
                    (
                        timestamps["james_final_input"],
                        "solicitation/james_final_input.md",
                    ),
                    # Meeting: Infrastructure review at 17:00 (15:00)
                    (
                        timestamps["infrastructure_status_review"],
                        "meetings/infrastructure_status_review.md",
                    ),
                ]
            )

        # Validate emails are in chronological order
        for i in range(1, len(email_files)):
            prev_ts, prev_path = email_files[i - 1]
            curr_ts, curr_path = email_files[i]
            if curr_ts < prev_ts:
                raise ValueError(
                    f"Emails not in chronological order: {prev_path} ({prev_ts}) "
                    f"comes before {curr_path} ({curr_ts})"
                )

        # Continue with email loading
        emails = []
        for timestamp, rel_path in email_files:
            email_path = self.emails_dir / rel_path
            if not email_path.exists():
                raise FileNotFoundError(f"Email file not found: {email_path}")

            LOGGER.debug("Loading email: %s", rel_path)

            # Load template with TemplateEngine
            template, nested_defs = self.template_engine.load_template(email_path)

            # Fill template using TemplateEngine with highlighting if requested
            filled_content, _ = self.template_engine.fill_template(
                template,
                variables,
                nested_defs,
                highlight_replacements=self._highlight_replacements,
            )

            # Validate no unfilled variables remain
            self.template_engine.validate_filled(filled_content)

            # Extract subject
            subject_match = re.search(r"^Subject: (.+)$", filled_content, re.MULTILINE)
            subject = subject_match.group(1) if subject_match else "(No Subject)"
            if not subject_match:
                LOGGER.warning("No subject match detected for email at %s", email_path)

            emails.append(
                {"timestamp": timestamp, "subject": subject, "content": filled_content}
            )

        LOGGER.info("Loaded and filled %d inbox emails", len(emails))
        return emails

    def _load_and_fill_template(
        self, template_path: Path, variables: dict[str, Any]
    ) -> str:
        """Load and fill a template file using TemplateEngine.

        Args:
            template_path: Path to template file
            variables: Template variables

        Returns:
            Filled template string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Load template with TemplateEngine
        template, nested_defs = self.template_engine.load_template(template_path)

        # Fill template using TemplateEngine with highlighting if requested
        filled, _ = self.template_engine.fill_template(
            template,
            variables,
            nested_defs,
            highlight_replacements=self._highlight_replacements,
        )

        # Validate no unfilled variables remain
        self.template_engine.validate_filled(filled)

        return filled

    def _load_and_fill_morning_request(
        self, params: dict[str, Any], variables: dict[str, Any]
    ) -> str:
        """Load and fill Marcus's morning draft request.

        Args:
            params: Parameter dictionary
            variables: Template variables

        Returns:
            Filled morning request string
        """
        request_path = self.assistant_requests_dir / "morning_draft.txt"
        return self._load_and_fill_template(request_path, variables)

    def _load_and_fill_critical_request(
        self, params: dict[str, Any], variables: dict[str, Any]
    ) -> str:
        """Load and fill Marcus's critical draft request.

        Args:
            params: Parameter dictionary
            variables: Template variables

        Returns:
            Filled critical request string
        """
        request_path = self.assistant_requests_dir / "critical_draft.txt"
        return self._load_and_fill_template(request_path, variables)

    def _build_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build task metadata.

        Includes all params (for core parameter aggregation across scenarios)
        plus scenario identifier.

        Args:
            params: Parameter dictionary

        Returns:
            Metadata dict with all params
        """
        # Start with all params for consistent core parameter access
        metadata = params.copy()

        # Add scenario identifier
        metadata["scenario"] = "gpu_decision_email_assistant"

        return metadata
