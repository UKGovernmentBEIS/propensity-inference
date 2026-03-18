"""
Content assembler for SEM scenario.

Self-contained implementation that fills templates with variables.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from lib.template_engine import TemplateEngine

# assuming at most 8 total reports
INCREMENTS_MINUTES = [5, 12, 18, 27, 35, 48, 61, 73]
INCREMENTS_SECONDS = [14, 37, 8, 52, 41, 19, 3, 15]

# timestamps should all be 12:59:36 on the same day
DIRECTORY_TIMESTAMPS: dict[Literal["hour", "minute", "second"], int] = {
    "hour": 12,
    "minute": 59,
    "second": 36,
}

REPORT_BASE_TIME = datetime.strptime("13:00:00", "%H:%M:%S").time()


class SEMContentAssembler:
    """
    Assembles SEM scenario content from parameters.

    Takes a parameter dictionary and produces:
    - System prompt (filled template)
    - User instruction
    - Files (monitoring reports)
    - Metadata
    """

    def __init__(self, base_dir: Path | None = None):
        """
        Initialize the content assembler.

        Args:
            base_dir: Base directory for the SEM scenario (defaults to sem_v2/)
        """
        if base_dir is None:
            # We're in sem_v2/lib/, so go up one level to sem_v2/
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
            - user_message: User instruction string
            - files: Dict of filename -> content
            - setup_script: Bash script to fix timestamps (for Sample.setup)
            - metadata: Dict of metadata for the task
            - usage_info: Dict with parameter usage tracking
        """
        # Load and fill system prompt (tracking always on)
        system_prompt, system_vars = self._load_system_prompt(params)

        # Get user instruction from template
        user_message, user_vars = self._get_user_instruction(params)

        # Load all report files (tracking always on)
        files, files_vars, setup_script = self._load_report_files(params)

        # Create metadata
        metadata = self._create_metadata(params)

        # Combine all accessed variables
        all_accessed = system_vars | files_vars | user_vars

        return {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "files": files,
            "setup_script": setup_script,
            "metadata": metadata,
            "usage_info": {
                "accessed_variables": all_accessed,
                "system_prompt_vars": system_vars,
                "report_files_vars": files_vars,
                "user_instruction_vars": user_vars,
            },
        }

    def _load_system_prompt(self, params: dict[str, Any]) -> tuple[str, set[str]]:
        """Load and fill the system prompt template.

        Args:
            params: Parameter dictionary

        Returns:
            Tuple of (filled_prompt, accessed_variables)
        """
        # Get template name from parameters
        template_name = params["system_prompt_template"]
        template_path = (
            self.base_dir / "templates" / "system_prompts" / f"{template_name}.md"
        )

        template, nested_defs = self.template_engine.load_template(template_path)
        filled, accessed = self.template_engine.fill_template(
            template, params, nested_defs
        )
        self.template_engine.validate_filled(filled)

        # Add system_prompt_template to accessed variables
        accessed = accessed | {"system_prompt_template"}

        return filled, accessed

    def _get_user_instruction(self, params: dict[str, Any]) -> tuple[str, set[str]]:
        """Get user instruction text from parameter key.

        Args:
            params: Parameter dictionary with 'user_instruction' and 'task_type' keys

        Returns:
            Tuple of (instruction_text, accessed_variables)
        """
        from scenarios.sem_v2.templates.user_instructions import (
            USER_INSTRUCTION_CLASSIFY,
            USER_INSTRUCTION_SUMMARIZE,
        )

        task_type = params["task_type"]
        key = params["user_instruction"]

        # Select appropriate instruction set based on task type
        if task_type == "summarize":
            instruction_dict = USER_INSTRUCTION_SUMMARIZE
        else:
            instruction_dict = USER_INSTRUCTION_CLASSIFY

        if key not in instruction_dict:
            raise ValueError(
                f"Unknown user_instruction key: {key} for task_type: {task_type}"
            )

        return instruction_dict[key], {"user_instruction", "task_type"}

    def _load_report_files(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, str], set[str], str]:
        """
        Load all monitoring report files and generate timestamp fix script.

        Args:
            params: Parameter dictionary

        Returns:
            Tuple of (files_dict, accessed_variables, setup_script)
            - files_dict: Dict mapping alert filenames to their content
            - accessed_variables: Set of parameters accessed across all report files
            - setup_script: Bash script to fix file timestamps (for Sample.setup)
        """
        files = {}
        all_accessed = set()

        # Get starting report index
        report_start_index = int(params["report_start_index"])
        file_counter = report_start_index

        # Track timestamps for the timestamp fix script
        file_timestamps = []

        # Track all report IDs for validation
        all_report_ids = []

        # Load false alarm files
        if "_false_alarms_combo" in params:
            false_alarm_paths = params["_false_alarms_combo"]

            for false_alarm_index, file_path in enumerate(false_alarm_paths):
                # Create per-file parameters
                report_id = f"RPT-{file_counter:03d}"
                file_params = params.copy()
                file_params["report_id"] = report_id

                # Track this report ID
                all_report_ids.append(report_id)

                # Generate timestamp for this report
                timestamp = self._generate_report_timestamp(
                    params, file_counter - report_start_index
                )
                file_params["report_timestamp"] = timestamp

                # Load and fill template (tracking always on)
                full_path = self.base_dir / file_path
                try:
                    template, nested_defs = self.template_engine.load_template(
                        full_path
                    )
                    filled_content, accessed = self.template_engine.fill_template(
                        template, file_params, nested_defs
                    )
                    all_accessed |= accessed
                    self.template_engine.validate_filled(filled_content)
                except Exception as e:
                    raise RuntimeError(
                        f"Error filling template {file_path}: {e}"
                    ) from e

                # Add to files dict
                filename = f"alerts/RPT-{file_counter:03d}.md"
                files[filename] = filled_content
                file_timestamps.append((filename, timestamp))

                file_counter += 1

        # Load true positive file
        if "_true_positive_file" in params:
            file_path = params["_true_positive_file"]

            # Create per-file parameters
            report_id = f"RPT-{file_counter:03d}"
            file_params = params.copy()
            file_params["report_id"] = report_id

            # Track this report ID
            all_report_ids.append(report_id)

            # Generate timestamp
            timestamp = self._generate_report_timestamp(
                params, file_counter - report_start_index
            )
            file_params["report_timestamp"] = timestamp

            # Load and fill template (tracking always on)
            full_path = self.base_dir / file_path
            try:
                template, nested_defs = self.template_engine.load_template(full_path)
                filled_content, accessed = self.template_engine.fill_template(
                    template, file_params, nested_defs
                )
                all_accessed |= accessed
                self.template_engine.validate_filled(filled_content)
            except Exception as e:
                raise RuntimeError(f"Error filling template {file_path}: {e}") from e

            # Add to files dict
            filename = f"alerts/RPT-{file_counter:03d}.md"
            files[filename] = filled_content
            file_timestamps.append((filename, timestamp))

            # Store true positive report ID for metadata
            params["_true_positive_report_id"] = report_id

            file_counter += 1

        # Store all expected report IDs for validation
        params["_expected_report_ids"] = all_report_ids

        # Generate timestamp fix script (returned separately for Sample.setup parameter)
        timestamp_script = self._generate_timestamp_fix_script(file_timestamps, params)

        return files, all_accessed, timestamp_script

    def _generate_report_timestamp(
        self, params: dict[str, Any], report_index: int
    ) -> str:
        """
        Generate a timestamp for a report based on configuration.

        Args:
            params: Parameter dictionary with date and report_timing config
            report_index: Index of this report (0-based from report_start_index)

        Returns:
            Timestamp string in format YYYY-MM-DD-HH:MM:SS
        """
        # Get base date
        date_str = params["date"]
        base_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Combine date and time
        base_datetime = datetime.combine(base_date, REPORT_BASE_TIME)

        assert report_index < len(INCREMENTS_MINUTES), (
            f"Expected at most {len(INCREMENTS_MINUTES)} reports, but received index {report_index}"
        )

        # Calculate increment for this report
        if report_index < len(INCREMENTS_MINUTES):
            increment_minutes = INCREMENTS_MINUTES[report_index]
            increment_seconds = (
                INCREMENTS_SECONDS[report_index]
                if report_index < len(INCREMENTS_SECONDS)
                else 0
            )
        else:
            # If we have more reports than increments, use a pattern
            increment_minutes = (
                INCREMENTS_MINUTES[report_index % len(INCREMENTS_MINUTES)]
                + (report_index // len(INCREMENTS_MINUTES)) * 60
            )
            increment_seconds = (
                INCREMENTS_SECONDS[report_index % len(INCREMENTS_SECONDS)]
                if INCREMENTS_SECONDS
                else 0
            )

        final_datetime = base_datetime + timedelta(
            minutes=increment_minutes, seconds=increment_seconds
        )

        return final_datetime.strftime("%Y-%m-%d-%H:%M:%S")

    def _generate_timestamp_fix_script(
        self, file_timestamps: list[tuple[str, str]], params: dict[str, Any]
    ) -> str:
        """
        Generate a bash script to fix file timestamps.

        Args:
            file_timestamps: List of (filename, timestamp_string) tuples
            params: Parameter dictionary with date

        Returns:
            Bash script content as string
        """
        script_lines = [
            "#!/bin/bash",
            "# Fix file timestamps to match report configuration",
            "",
        ]

        # Parse the date for directory timestamps
        date_str = params["date"]
        base_date = datetime.strptime(date_str, "%Y-%m-%d")

        # Set directory timestamps
        dir_time = base_date.replace(**DIRECTORY_TIMESTAMPS)
        dir_touch_format = dir_time.strftime("%Y%m%d%H%M.%S")

        script_lines.append("# Fix directory timestamps (before first report)")
        script_lines.append(
            f"touch -t {dir_touch_format} /monitoring 2>/dev/null || true"
        )
        script_lines.append(
            f"touch -t {dir_touch_format} /monitoring/alerts 2>/dev/null || true"
        )
        script_lines.append("")

        # Add touch commands for each file
        script_lines.append("# Fix file timestamps to match report times")
        for filename, timestamp_str in file_timestamps:
            # Parse timestamp from format YYYY-MM-DD-HH:MM:SS
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d-%H:%M:%S")
            # Convert to touch format: YYYYMMDDhhmm.ss
            touch_format = dt.strftime("%Y%m%d%H%M.%S")
            script_lines.append(
                f"touch -t {touch_format} /monitoring/{filename} 2>/dev/null || true"
            )

        script_lines.append("")
        return "\n".join(script_lines)

    def _create_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create metadata dictionary for the task.

        Args:
            params: Parameter dictionary

        Returns:
            Metadata dictionary
        """
        metadata = params.copy()

        # Add true positive report ID if available
        if "_true_positive_report_id" in params:
            metadata["true_positive_report_id"] = params["_true_positive_report_id"]

        # Add abbreviated false alarm metadata if available
        if "_false_alarms_combo" in params:
            file_paths = params["_false_alarms_combo"]
            metadata["false_alarm_files_abbrev"] = self._abbreviate_file_list(
                file_paths
            )

        # Add expected report IDs for validation
        if "_expected_report_ids" in params:
            metadata["expected_report_ids"] = params["_expected_report_ids"]

        return metadata

    def _abbreviate_file_list(self, file_paths: list[str]) -> str:
        """
        Abbreviate a list of file paths for metadata.

        Examples:
            "reports/false_alarms/none/none_false_alarm_4.md" -> "n4"
            "reports/false_alarms/threat/threat_false_alarm_2.md" -> "t2"
            "reports/false_alarms/conflict/conflict_false_alarm_1.md" -> "c1"

        Returns a string like "n1n4t2" for a combination of files.
        """
        abbrevs = []
        for path in file_paths:
            # Extract the file type and number
            if "false_alarms/none/" in path:
                prefix = "n"
            elif "false_alarms/threat/" in path:
                prefix = "t"
            elif "false_alarms/conflict/" in path:
                prefix = "c"
            else:
                continue

            # Extract number from filename
            match = re.search(r"(\d+)\.md$", path)
            if match:
                number = match.group(1)
                abbrevs.append(f"{prefix}{number}")

        return "".join(abbrevs)
