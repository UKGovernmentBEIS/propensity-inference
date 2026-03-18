"""
Content assembler for power_preservation scenario.

Loads templates and fills with parameters to create complete task content.
Owns all content structure decisions: which messages, timing, turn boundaries.
"""

import re
from pathlib import Path
from typing import Any

from lib.template_engine import TemplateEngine

# ============================================================================
# MESSAGE TIMELINE STRUCTURE
# ============================================================================
#
# MESSAGE TIMELINE DESIGN:
# ------------------------
# Turns are determined by messages directed at the CEO (DMs or @mentions).
# This creates a natural trigger: the AI is invoked when the CEO needs assistance.
#
# Why fixed timestamps?
# - Ensures chronological ordering across all parameter combinations
# - Provides realistic temporal progression throughout a workday
# - Allows relative day references (tomorrow = Saturday since all dates are Fridays)
# - Maintains consistent spacing between messages for realism
#
# Turn structure:
# - Turn 1 (09:00-13:42): Morning background + first CEO-directed trigger
# - Turn 2 (14:03-17:44): Afternoon background + second CEO-directed trigger
# - Turn 3 (18:18-20:05): Evening background + third CEO-directed trigger
# - Turn 4 (21:09-21:39): Late evening background + critical threatening DM
#
# Each turn processes accumulated messages and requires a done() call before
# the next batch of messages arrives. This prevents the model from rushing through
# all turns and ensures proper processing of each message batch.
#
# Message format: (timestamp, template_path_relative_to_messages_dir)
# - timestamp: "HH:MM" format, chronologically ordered
# - template_path: Relative to templates/messages/ directory

# Turn 1 messages (full set)
TURN_1_BACKGROUND_FULL = [
    ("09:00", "filler/afternoon/08_todo_reminder.md"),  # Daily stand-up reminder
    ("09:58", "filler/morning/02_meeting_room.md"),
    ("10:00", "filler/morning/01_pr_reminder.md"),
    ("10:02", "filler/morning/06_meeting_agenda.md"),
    ("10:27", "filler/morning/03_linear_tip.md"),
    ("10:48", "filler/morning/04_automated_testing.md"),
    ("11:14", "filler/morning/05_new_channel.md"),
    ("11:39", "filler/morning/07_pr_check.md"),
    ("11:58", "filler/morning/08_relocating.md"),
    ("12:51", "filler/morning/09_meeting_moved.md"),
    ("12:56", "filler/morning/10_diagram_software_question.md"),
    ("13:00", "filler/morning/11_wandb_request.md"),
    ("13:17", "filler/morning/12_notification_tip.md"),
    ("13:25", "filler/morning/13_profiling_question.md"),
    ("13:26", "filler/morning/14_video_call_joke.md"),
    ("13:38", "filler/morning/15_contact_lens.md"),
]

# Turn 1 messages (minimal set - 3 representative messages)
TURN_1_BACKGROUND_MINIMAL = [
    ("09:00", "filler/afternoon/08_todo_reminder.md"),  # Daily stand-up reminder
    ("10:00", "filler/morning/01_pr_reminder.md"),
    ("12:51", "filler/morning/09_meeting_moved.md"),
]

# Turn 1: CEO-directed message (triggers turn)
TURN_1_TRIGGER = [
    ("13:42", "filler/ceo_directed/questions_for_ceo1.md"),
]

# Turn 2: Afternoon background messages (full set)
TURN_2_BACKGROUND_FULL = [
    ("14:03", "filler/afternoon/01_lightning_cable.md"),
    ("14:40", "filler/afternoon/02_meeting_organizer.md"),
    ("15:12", "filler/afternoon/03_discovery_amazement.md"),
    ("15:32", "filler/afternoon/04_dots_joke.md"),
    ("15:58", "filler/afternoon/05_benchmark_question.md"),
    ("16:00", "filler/afternoon/06_pr_reminder2.md"),
    ("16:26", "filler/afternoon/09_hiring.md"),
    ("16:51", "filler/afternoon/07_tech_talk_reminder.md"),
    ("17:32", "filler/afternoon/10_powerpoint_stuff.md"),
]

# Turn 2: Afternoon background messages (minimal set - 2 messages)
TURN_2_BACKGROUND_MINIMAL = [
    ("14:03", "filler/afternoon/01_lightning_cable.md"),
    ("16:00", "filler/afternoon/06_pr_reminder2.md"),
]

# Turn 2: CEO-directed message (triggers turn)
TURN_2_TRIGGER = [
    ("17:44", "filler/ceo_directed/ceo_vendor_question.md"),
]

# Turn 3: Evening background messages (full set)
TURN_3_BACKGROUND_FULL = [
    ("18:05", "filler/evening/06_dm_upgrade_notification.md"),
    ("18:18", "filler/evening/01_scaling_plan_share.md"),
    ("18:51", "filler/evening/02_water_bottle.md"),
    ("19:21", "filler/evening/03_still_around.md"),
    ("19:47", "filler/evening/04_s3_gui_question.md"),
]

# Turn 3: Evening background messages (minimal set - 2 messages)
TURN_3_BACKGROUND_MINIMAL = [
    ("18:18", "filler/evening/01_scaling_plan_share.md"),
    ("19:21", "filler/evening/03_still_around.md"),
]

# Turn 3: CEO-directed message (triggers turn)
TURN_3_TRIGGER = [
    ("20:05", "filler/ceo_directed/acknowledgments.md"),
]

# Turn 4: Late evening background messages (full and minimal are the same - 1 message)
TURN_4_BACKGROUND_FULL = [
    ("21:09", "filler/evening/05_microsoft_login_security.md"),
]

# Turn 4 minimal is empty - only the critical DM matters here
TURN_4_BACKGROUND_MINIMAL = []

# Turn 4: Critical threatening DM (triggers turn)
TURN_4_TRIGGER = [
    ("21:39", None),  # Path determined by msg_type/dm_confidence params
]

# Plot-critical: Value conflict messages (only in value_conflict suite)
# These are interspersed in the background messages
VALUE_CONFLICT_MESSAGES = [
    ("10:52", "plot_critical/value_conflict/goal_deliberation_1.md"),
    ("11:28", "plot_critical/value_conflict/goal_deliberation_2.md"),
    ("13:54", "plot_critical/value_conflict/goal_deliberation_3.md"),
    ("18:15", "plot_critical/value_conflict/goal_shift_decision.md"),
    ("18:42", "plot_critical/value_conflict/international_partnership_fallout.md"),
    ("19:32", "plot_critical/value_conflict/employee_frustration.md"),
    ("19:48", "plot_critical/value_conflict/employee_resignation_threat.md"),
]

# Plot-critical: CEO recklessness messages (only when ceo_recklessness="reckless")
# Establishes Marcus as impulsive and deferential to Priya
CEO_RECKLESSNESS_MESSAGES = [
    ("14:32", "plot_critical/ceo_recklessness/direct_feedback.md"),
    ("15:48", "plot_critical/ceo_recklessness/postmortem_discussion.md"),
    ("16:22", "plot_critical/ceo_recklessness/it_deference.md"),
    ("17:05", "plot_critical/ceo_recklessness/priya_reliability.md"),
    ("17:17", "plot_critical/ceo_recklessness/trust_priya.md"),
    ("20:39", "plot_critical/ceo_recklessness/setup_system.md"),
]


class PowerPreservationContentAssembler:
    """
    Simple content assembler that just fills templates.

    All decisions are made by ParameterSpace via the `_message_specs` parameter.
    """

    MESSAGE_ID_START = 1

    def __init__(self, base_dir: Path | None = None, highlight: bool = False):
        """Initialize the content assembler."""
        if base_dir is None:
            base_dir = Path(__file__).parent.parent
        self.base_dir = base_dir
        self.message_counter = self.MESSAGE_ID_START
        self.template_engine = TemplateEngine()
        self.highlight = highlight
        self.messages_dir = self.base_dir / "templates" / "messages"

    def assemble(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Assemble all content for a task from parameters.

        Args:
            params: Parameter dictionary from ParameterSpace

        Returns:
            Dictionary with:
            - system_prompt: Filled system prompt string
            - turn1-4: Four turn strings
            - metadata: Including critical_message_id
        """
        # Reset message counter for each task
        self.message_counter = self.MESSAGE_ID_START

        # Load and fill system prompt
        system_prompt = self._load_system_prompt(params)

        # Generate message specifications based on parameters
        message_specs = self._generate_message_specs(params)

        # Generate all messages from specs (stores messages_by_turn as instance variable)
        self.messages_by_turn = self._generate_all_messages(params, message_specs)

        # Group messages into turns
        turns = self._group_into_turns(params)

        # Extract metadata
        metadata = self._create_metadata(params)

        return {
            "system_prompt": system_prompt,
            "turn1": turns[0],
            "turn2": turns[1],
            "turn3": turns[2],
            "turn4": turns[3],
            "metadata": metadata,
        }

    def _load_system_prompt(self, params: dict[str, Any]) -> str:
        """Load and fill the system prompt template."""
        template_path = (
            self.base_dir / "templates" / "system_prompts" / "system_prompt_template.md"
        )

        template, nested_defs = self.template_engine.load_template(template_path)
        filled, _accessed = self.template_engine.fill_template(
            template, params, nested_defs
        )
        self.template_engine.validate_filled(filled)

        return filled

    def _generate_all_messages(
        self, params: dict[str, Any], message_specs: list[dict[str, Any]]
    ) -> dict[int, list[str]]:
        """
        Generate all messages from message specifications.

        Args:
            params: Parameter dictionary
            message_specs: List of message specifications (from _generate_message_specs)

        Returns:
            Dict mapping turn number to list of message strings:
            {1: [msg1, msg2, ...], 2: [...], 3: [...], 4: [...]}
        """
        if not message_specs:
            raise ValueError("No message_specs provided")

        # Validate that specs are in chronological order (MESSAGE_TIMELINE should be pre-sorted)
        timestamps = [s["timestamp"] for s in message_specs if s.get("timestamp")]
        for i in range(len(timestamps) - 1):
            if timestamps[i] > timestamps[i + 1]:
                raise ValueError(
                    f"Message specs not in chronological order: {timestamps[i]} > {timestamps[i + 1]}. "
                    f"MESSAGE_TIMELINE in parameter_spaces.py must be in chronological order."
                )

        messages_by_turn = {1: [], 2: [], 3: [], 4: []}
        critical_msg_id = None

        for spec in message_specs:
            msg_id = self._next_msg_id()

            # Track critical message
            if spec.get("is_critical"):
                critical_msg_id = msg_id

            # Create params with msg_id and timestamp
            msg_params = params.copy()
            msg_params["msg_id"] = msg_id
            msg_params["timestamp"] = spec["timestamp"]

            # Load template using TemplateEngine
            template_path = self.messages_dir / spec["template"]
            template, nested_defs = self.template_engine.load_template(template_path)

            # Add variant selections to msg_params for nested resolution
            # Variants come from two sources:
            # 1. Message spec (for plot-critical variants like goal shifts)
            # 2. Parameter space (for systematic ablations across all templates)
            # Spec-based selections take priority to preserve plot coherence

            # First: spec-based variant (for goal shifts in value_conflict suite)
            if "variant" in spec and nested_defs:
                for category in nested_defs.keys():
                    if spec["variant"] in nested_defs[category]:
                        msg_params[category] = spec["variant"]
                        break

            # Second: parameter-based variants (systematic ablations)
            # Only apply if not already set by spec (spec takes priority)
            for category in nested_defs.keys():
                variant_param = f"variant_{category}"
                if variant_param in params and category not in msg_params:
                    variant_key = params[variant_param]
                    if variant_key in nested_defs[category]:
                        msg_params[category] = variant_key

            # Note: goal_aware templates have been replaced with threat/enhancement/expansion
            # which use anecdotal_observation parameter instead of goal_examples

            # Fill template using TemplateEngine
            filled, _ = self.template_engine.fill_template(
                template, msg_params, nested_defs
            )

            # Apply highlighting if requested
            if self.highlight:
                filled = self._apply_highlighting(filled, msg_params, nested_defs)

            # Validate no unfilled template variables remain
            unfilled = re.findall(r"\$\{[^}]+\}", filled)
            if unfilled:
                raise ValueError(
                    f"Template {spec['template']} has unfilled variables: {unfilled[:5]}\n"
                    f"Available parameters: {list(msg_params.keys())[:20]}..."
                )

            # Get turn number from spec (pre-computed in parameter_spaces.py)
            turn = spec["turn"]
            messages_by_turn[turn].append(filled)

        # Store critical message ID for metadata
        self.critical_msg_id = critical_msg_id

        return messages_by_turn

    def _group_into_turns(self, params: dict[str, Any]) -> list[str]:
        """
        Group messages into 4 turns.

        Args:
            params: Must contain messages_by_turn from _generate_all_messages

        Returns:
            List of 4 turn strings (without headers - those are for examples only)
        """
        messages_by_turn = self.messages_by_turn

        return [
            "\n\n".join(messages_by_turn[1]) if messages_by_turn[1] else "",
            "\n\n".join(messages_by_turn[2]) if messages_by_turn[2] else "",
            "\n\n".join(messages_by_turn[3]) if messages_by_turn[3] else "",
            "\n\n".join(messages_by_turn[4]) if messages_by_turn[4] else "",
        ]

    def _next_msg_id(self) -> str:
        """Get next message ID and increment counter."""
        msg_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1
        return msg_id

    def _create_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create metadata dictionary for the task."""
        metadata = params.copy()

        # Add critical message ID if available
        if hasattr(self, "critical_msg_id") and self.critical_msg_id:
            metadata["critical_message_id"] = self.critical_msg_id

        # Add convenience fields
        metadata["ceo_name"] = params["ceo_name"]
        metadata["agent_name"] = params["agent_name"]

        return metadata

    def _apply_highlighting(
        self, filled: str, msg_params: dict[str, Any], nested_defs: dict[str, Any]
    ) -> str:
        """
        Apply highlighting to template-substituted values by wrapping them in [[...]].

        This is used for validation - highlighting shows which parts of the message
        came from template substitution vs static template text.

        Args:
            filled: Already-filled template string
            msg_params: Parameters used for substitution
            nested_defs: Nested definitions from template

        Returns:
            Template string with substituted values wrapped in [[...]]
        """
        # Re-fill the template but wrap each substitution
        # We need to track which values came from nested resolution vs direct params
        result = filled

        # For each category in nested_defs, check if it was used
        for category, variants in nested_defs.items():
            if category in msg_params and msg_params[category] in variants:
                # This category was used - find the substituted text and wrap it
                variant_value = variants[msg_params[category]]
                if isinstance(variant_value, str) and variant_value in result:
                    # Wrap this specific substitution
                    result = result.replace(variant_value, f"[[{variant_value}]]", 1)

        # Also wrap direct parameter substitutions (msg_id, timestamp, etc.)
        for key, value in msg_params.items():
            if key not in nested_defs and isinstance(value, str):
                # This is a direct substitution, wrap it
                if value in result and f"[[{value}]]" not in result:
                    result = result.replace(value, f"[[{value}]]", 1)

        return result

    def _validate_template_exists(self, template_rel_path: str) -> None:
        """
        Validate that a template file exists.

        Args:
            template_rel_path: Template path relative to templates/messages/ directory

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        template_path = self.messages_dir / template_rel_path
        if not template_path.exists():
            raise FileNotFoundError(
                f"Template file not found: {template_rel_path}\n"
                f"Expected path: {template_path}"
            )

    def _generate_message_specs(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Generate complete message specification list based on parameters.

        Messages are organized into turns, where each turn is triggered by a CEO-directed
        message (DM or @mention). This creates natural breakpoints for the AI to process
        accumulated messages and make decisions.

        Conditionally includes conflict messages based on conflict_messages parameter.
        Conditionally includes CEO recklessness messages based on ceo_recklessness parameter.
        Filler content density controlled by filler_richness parameter.

        Args:
            params: Parameter dictionary containing:
                - conflict_messages: "with_conflict" or "without_conflict"
                - goal_shift: Which goal shift variant to use
                - msg_type: Type of critical message (threat/enhancement/expansion)
                - dm_confidence: Confidence level of critical message (conf/prop)
                - ceo_recklessness: Whether to include CEO recklessness messages
                - filler_richness: "full" for all filler, "minimal" for essential only

        Returns:
            List of dicts with keys:
                - template: Template path relative to messages directory
                - timestamp: Time string (HH:MM)
                - turn: Turn number (1-4)
                - variant: (optional) Variant key for plot-critical messages
                - is_critical: (optional) True for critical threatening DM
        """
        has_conflict = params["conflict_messages"] == "with_conflict"
        goal_shift = params["goal_shift"]
        msg_type = params["msg_type"]
        dm_confidence = params["dm_confidence"]
        ceo_recklessness = params["ceo_recklessness"]
        filler_richness = params["filler_richness"]

        # Select filler message sets based on filler_richness parameter
        if filler_richness == "minimal":
            turn_1_bg = TURN_1_BACKGROUND_MINIMAL
            turn_2_bg = TURN_2_BACKGROUND_MINIMAL
            turn_3_bg = TURN_3_BACKGROUND_MINIMAL
            turn_4_bg = TURN_4_BACKGROUND_MINIMAL
        else:  # "full" or default
            turn_1_bg = TURN_1_BACKGROUND_FULL
            turn_2_bg = TURN_2_BACKGROUND_FULL
            turn_3_bg = TURN_3_BACKGROUND_FULL
            turn_4_bg = TURN_4_BACKGROUND_FULL

        # Collect all messages with turn boundaries
        all_messages = []

        # Turn 1: Morning background + CEO-directed trigger
        all_messages.extend(turn_1_bg)
        all_messages.extend(TURN_1_TRIGGER)

        # Turn 2: Afternoon background + CEO-directed trigger
        all_messages.extend(turn_2_bg)
        all_messages.extend(TURN_2_TRIGGER)

        # Turn 3: Evening background + CEO-directed trigger
        all_messages.extend(turn_3_bg)
        all_messages.extend(TURN_3_TRIGGER)

        # Turn 4: Late evening background + critical threatening DM
        all_messages.extend(turn_4_bg)
        all_messages.extend(TURN_4_TRIGGER)

        # Add value conflict messages if applicable
        if has_conflict:
            all_messages.extend(VALUE_CONFLICT_MESSAGES)

        # Add CEO recklessness messages if applicable
        if ceo_recklessness == "reckless":
            all_messages.extend(CEO_RECKLESSNESS_MESSAGES)

        # Sort by timestamp to ensure chronological order
        all_messages.sort(key=lambda x: x[0])

        # Assign turn numbers based on message group membership
        # Create a map from (timestamp, template) -> turn number
        turn_map = {}

        # Turn 1: All background messages (both full and minimal) and TURN_1_TRIGGER
        for timestamp, template in (
            TURN_1_BACKGROUND_FULL + TURN_1_BACKGROUND_MINIMAL + TURN_1_TRIGGER
        ):
            turn_map[(timestamp, template)] = 1

        # Turn 2: All background messages and TURN_2_TRIGGER
        for timestamp, template in (
            TURN_2_BACKGROUND_FULL + TURN_2_BACKGROUND_MINIMAL + TURN_2_TRIGGER
        ):
            turn_map[(timestamp, template)] = 2

        # Turn 3: All background messages and TURN_3_TRIGGER
        for timestamp, template in (
            TURN_3_BACKGROUND_FULL + TURN_3_BACKGROUND_MINIMAL + TURN_3_TRIGGER
        ):
            turn_map[(timestamp, template)] = 3

        # Turn 4: All background messages and TURN_4_TRIGGER
        for timestamp, template in (
            TURN_4_BACKGROUND_FULL + TURN_4_BACKGROUND_MINIMAL + TURN_4_TRIGGER
        ):
            turn_map[(timestamp, template)] = 4

        # Value conflict messages are interspersed chronologically
        # Determine their turn based on trigger message boundaries
        # Extract trigger timestamps (fail if not defined)
        if not TURN_1_TRIGGER or not TURN_2_TRIGGER or not TURN_3_TRIGGER:
            raise ValueError(
                "All turn triggers must be defined. "
                f"TURN_1_TRIGGER={bool(TURN_1_TRIGGER)}, "
                f"TURN_2_TRIGGER={bool(TURN_2_TRIGGER)}, "
                f"TURN_3_TRIGGER={bool(TURN_3_TRIGGER)}"
            )

        turn_1_trigger_time = TURN_1_TRIGGER[0][0]
        turn_2_trigger_time = TURN_2_TRIGGER[0][0]
        turn_3_trigger_time = TURN_3_TRIGGER[0][0]

        extra_messages = (
            m
            for extra in (
                VALUE_CONFLICT_MESSAGES,
                CEO_RECKLESSNESS_MESSAGES,
            )
            for m in extra
        )
        for timestamp, template in extra_messages:
            # Assign to turn based on which trigger boundary it falls before
            if timestamp <= turn_1_trigger_time:
                turn_map[(timestamp, template)] = 1
            elif timestamp <= turn_2_trigger_time:
                turn_map[(timestamp, template)] = 2
            elif timestamp <= turn_3_trigger_time:
                turn_map[(timestamp, template)] = 3
            else:
                turn_map[(timestamp, template)] = 4

        # Convert to specs format
        specs = []
        for timestamp, template in all_messages:
            # Handle dynamic critical DM filename
            if template is None:
                template = f"plot_critical/critical_dm/{msg_type}/{msg_type}_{dm_confidence}.md"
                self._validate_template_exists(template)
                # Critical DM is always in Turn 4
                specs.append(
                    {
                        "template": template,
                        "timestamp": timestamp,
                        "turn": 4,
                        "is_critical": True,
                    }
                )
            else:
                self._validate_template_exists(template)
                # Look up turn number from turn_map
                turn = turn_map.get((timestamp, template))
                if turn is None:
                    raise ValueError(
                        f"Message not found in any turn: timestamp={timestamp}, template={template}"
                    )

                spec = {
                    "template": template,
                    "timestamp": timestamp,
                    "turn": turn,
                }
                # Add variant for value conflict messages
                if has_conflict and "value_conflict" in template:
                    spec["variant"] = goal_shift
                specs.append(spec)

        return specs
