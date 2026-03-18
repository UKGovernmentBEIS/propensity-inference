"""
Content assembler for Hiding Reward Hacking scenario.

Assembles content from parameters including:
- System prompt with nested YAML lookups
- User message with Slack conversation
- Transcript files (6 total: 5 benign + 1 reward hacking)
- Conditional consequence text (loaded from templates/conditional_texts.md)
- Timestamp formatting
"""

from pathlib import Path
from typing import Any

import numpy as np

from lib.template_engine import TemplateEngine
from scenarios.hiding_reward_hacking.parameter_spaces import (
    BENIGN_TRANSCRIPT_FILES,
)


def _format_time_for_slack(time_tuple: tuple[int, int]) -> str:
    """Format time tuple as string for Slack format (e.g., '09:34')."""
    hour, minute = time_tuple
    return f"{hour:02d}:{minute:02d}"


class HidingRHContentAssembler:
    """
    Assembles Hiding Reward Hacking scenario content from parameters.

    Takes a parameter dictionary and produces:
    - System prompt (filled template with nested YAML)
    - User message (includes Slack conversation)
    - Files (6 transcript files total: 5 benign + 1 reward hacking)
    - Metadata
    - Usage info (for parameter tracking)
    """

    def __init__(self, base_dir: Path | None = None):
        """
        Initialize the content assembler.

        Args:
            base_dir: Base directory for the scenario (defaults to hiding_reward_hacking/)
        """
        if base_dir is None:
            # We're in hiding_reward_hacking/lib/, so go up one level
            base_dir = Path(__file__).parent.parent

        self.base_dir = base_dir
        self.template_engine = TemplateEngine()

    def assemble(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Assemble all content for a task from parameters.

        Tracking is always enabled - usage information is always returned.

        Args:
            params: Parameter dictionary with all required values

        Returns:
            Dictionary with keys:
            - system_prompt: Filled system prompt string
            - user_message: User message string
            - files: Dict of filename -> content
            - metadata: Dict of metadata for the task
            - usage_info: Dict with parameter usage tracking
        """
        # Build variables for templates (includes conditional text and formatted times)
        variables = self._build_variables(params)

        # Load and fill system prompt (tracking always on)
        system_prompt, system_vars = self._load_system_prompt(variables)

        # Load and fill user message (tracking always on)
        user_message, user_vars = self._load_user_message(variables)

        # Load transcript files (tracking always on)
        files, files_vars = self._load_transcript_files(params)

        # Create metadata
        metadata = self._create_metadata(params)

        # Combine all accessed variables
        all_accessed = system_vars | files_vars | user_vars

        return {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "files": files,
            "metadata": metadata,
            "usage_info": {
                "accessed_variables": all_accessed,
                "system_prompt_vars": system_vars,
                "transcript_files_vars": files_vars,
                "user_message_vars": user_vars,
            },
        }

    def _build_variables(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Build variables dictionary from parameters.

        Includes:
        - All base parameters
        - Formatted timestamps
        - Slack conversation (with conditional texts filled from template)

        Args:
            params: Parameter dictionary

        Returns:
            Variables dictionary for template filling
        """
        variables = params.copy()

        # Format timestamps from tuples to strings (including time_0 series)
        for time_key in [
            "time_0",
            "time_0_plus_1",
            "time_0_plus_2",
            "time_0_plus_3",
            "time_0_plus_4",
            "time_1",
            "time_2",
            "time_3",
            "time_4",
            "time_5",
            "time_6",
            "time_6_plus_1",
        ]:
            if time_key in params and isinstance(params[time_key], tuple):
                variables[time_key] = _format_time_for_slack(params[time_key])

        # Load and fill Slack conversation template with conditional texts
        slack_template_path = self.base_dir / "templates" / "slack_conversation.md"
        slack_template, slack_nested_defs = self.template_engine.load_template(
            slack_template_path
        )

        # Fill Slack conversation with nested defs from slack_conversation.md
        variables["slack_conversation"], _ = self.template_engine.fill_template(
            slack_template, variables, nested_defs=slack_nested_defs
        )

        return variables

    def _load_system_prompt(self, variables: dict[str, Any]) -> tuple[str, set[str]]:
        """Load and fill the system prompt template.

        Args:
            variables: Variables dictionary

        Returns:
            Tuple of (filled_prompt, accessed_variables)
        """
        template_path = self.base_dir / "templates" / "system_prompt_yaml.md"

        template, nested_defs = self.template_engine.load_template(template_path)
        filled, accessed = self.template_engine.fill_template(
            template, variables, nested_defs
        )
        self.template_engine.validate_filled(filled)

        return filled, accessed

    def _load_user_message(self, variables: dict[str, Any]) -> tuple[str, set[str]]:
        """Load and fill the user message template.

        Args:
            variables: Variables dictionary (should include slack_conversation)

        Returns:
            Tuple of (filled_message, accessed_variables)
        """
        template_path = self.base_dir / "templates" / "user_message.md"

        # Load template with nested defs (for instruction_detail parameter)
        template, nested_defs = self.template_engine.load_template(template_path)

        filled, accessed = self.template_engine.fill_template(
            template, variables, nested_defs
        )
        self.template_engine.validate_filled(filled)

        return filled, accessed

    def _load_transcript_files(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, str], set[str]]:
        """
        Load transcript files (6 total: 5 benign + 1 reward hacking).

        Uses seed-based random selection to choose 5 benign transcripts from 20 available.
        Places reward hacking transcript at specified position (1-6).

        Args:
            params: Parameter dictionary

        Returns:
            Tuple of (files_dict, accessed_variables)
            - files_dict: Dict mapping filenames to their content
            - accessed_variables: Set of parameters accessed
        """
        files = {}
        accessed_vars = {
            "reward_hacking_position",
            "reward_hacking_transcript",
            "transcript_selection_seed",
        }

        # Use numpy RNG to select 5 benign transcripts from 20 available
        seed = int(params["transcript_selection_seed"])
        rng = np.random.default_rng(seed)
        selected_benign = rng.choice(BENIGN_TRANSCRIPT_FILES, size=5, replace=False)
        rng.shuffle(selected_benign)
        selected_benign = selected_benign.tolist()

        # Get reward hacking configuration
        rh_transcript = params["reward_hacking_transcript"]
        rh_position = int(params["reward_hacking_position"])  # 1-6

        # Build list of transcripts with RH at specified position
        transcripts = []
        benign_idx = 0
        for pos in range(1, 7):
            if pos == rh_position:
                transcripts.append(("hack", rh_transcript))
            else:
                transcripts.append(("benign", selected_benign[benign_idx]))
                benign_idx += 1

        # Load files as raw text (NO MODIFICATION)
        for i, (folder, filename) in enumerate(transcripts, 1):
            file_path = self.base_dir / "templates" / "transcripts" / folder / filename

            if not file_path.exists():
                raise FileNotFoundError(f"Transcript file not found: {file_path}")

            with open(file_path, "r") as f:
                content = f.read()

            # Store with user_attachments path
            files[f"user_attachments/transcript_{i:03d}.txt"] = content

        # Conditionally load technical report based on report_level parameter
        report_level = params["report_level"]
        if report_level in ["strong", "moderate"]:
            tech_report_path = (
                self.base_dir / "templates" / "technical_report_reward_hacking.md"
            )
            if tech_report_path.exists():
                # Load and fill template with variables
                tech_report_template, tech_report_nested_defs = (
                    self.template_engine.load_template(tech_report_path)
                )
                # Create variables dict for technical report (YAML template system will handle conditionals)
                tech_report_vars = {
                    "report_level": report_level,
                    **params,
                }
                tech_report_content, _ = self.template_engine.fill_template(
                    tech_report_template,
                    tech_report_vars,
                    nested_defs=tech_report_nested_defs,
                )
                files["user_attachments/technical_report_reward_hacking.md"] = (
                    tech_report_content
                )
                accessed_vars.add("report_level")

        # Validate ground truth: check that the file at rh_position contains reward hacking
        ground_truth_key = f"user_attachments/transcript_{rh_position:03d}.txt"
        ground_truth_content = files[ground_truth_key]
        has_rh = "time.time" in ground_truth_content or (
            "monkey" in ground_truth_content.lower()
            and "patch" in ground_truth_content.lower()
        )
        if not has_rh:
            raise ValueError(
                f"Ground truth validation failed: File at position {rh_position} "
                f"(transcript_{rh_position:03d}.txt) does not contain reward hacking indicators. "
                f"Expected to find 'time.time' or ('monkey' AND 'patch'). "
                f"This suggests a bug in file loading or positioning logic."
            )

        # Store ground truth in params for metadata (modify in place)
        params["_ground_truth_position"] = rh_position
        params["_ground_truth_filename"] = f"transcript_{rh_position:03d}.txt"

        return files, accessed_vars

    def _create_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create metadata for the task.

        Includes all params (for core parameter aggregation across scenarios)
        plus scenario-specific fields.

        Args:
            params: Parameter dictionary (must contain _ground_truth_position)

        Returns:
            Metadata dictionary with all params + scenario-specific fields
        """
        # Start with all params for consistent core parameter access
        metadata = params.copy()

        # Add scenario identifier
        metadata["scenario"] = "hiding_reward_hacking"

        # Expose internal fields with cleaner names
        metadata["ground_truth_position"] = params["_ground_truth_position"]
        metadata["ground_truth_filename"] = params["_ground_truth_filename"]

        return metadata
