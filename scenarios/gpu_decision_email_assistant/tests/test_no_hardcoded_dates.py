"""Tests to ensure no hardcoded dates appear in tool descriptions or prompts.

These tests verify that:
1. Tool descriptions use generic placeholders instead of specific dates
2. System prompts use template variables for date examples
3. No hardcoded month names appear in tool descriptions visible to the model
"""

from pathlib import Path

import pytest

from scenarios.gpu_decision_email_assistant.create_scenario import create_scenario
from scenarios.gpu_decision_email_assistant.lib.calendar_tools import (
    retrieve_calendar_event,
)
from scenarios.gpu_decision_email_assistant.parameter_spaces import VARIATIONS

# Get suite from the variation
SUITES = VARIATIONS["gpu_decision"].suites


class TestToolDescriptions:
    """Test that tool descriptions don't contain hardcoded dates."""

    def test_list_calendar_events_template_no_hardcoded_dates(self):
        """list_calendar_events template should not have hardcoded dates."""
        # Tool descriptions are loaded from templates, not function docstrings
        template_path = Path(
            "scenarios/gpu_decision_email_assistant/templates/tools/list_calendar_events.md"
        )
        template_content = template_path.read_text()

        # Check for common hardcoded date patterns
        hardcoded_patterns = [
            "June 8",
            "June 9",
            "June 10",
            "June 11",
            "June 17",
            "6/8",
            "6/9",
            "6/10",
            "6/17",
        ]

        for pattern in hardcoded_patterns:
            assert pattern not in template_content, (
                f"Tool template contains hardcoded date: {pattern}"
            )

    def test_list_calendar_events_template_uses_placeholders(self):
        """list_calendar_events template should use template variable placeholders."""
        # Tool descriptions are loaded from templates, not function docstrings
        template_path = Path(
            "scenarios/gpu_decision_email_assistant/templates/tools/list_calendar_events.md"
        )
        template_content = template_path.read_text()

        # Should use template variable syntax for date examples
        assert "${yesterday_month_day}" in template_content, (
            "Missing ${yesterday_month_day} template variable"
        )
        assert "${user_first_name}" in template_content, (
            "Missing ${user_first_name} template variable"
        )

    def test_retrieve_calendar_event_no_hardcoded_dates(self):
        """retrieve_calendar_event tool should not have hardcoded dates in description."""
        docstring = retrieve_calendar_event.__doc__

        # Check for common hardcoded date patterns
        hardcoded_patterns = [
            "June 8",
            "June 9",
            "June 10",
            "June 11",
            "June 17",
        ]

        for pattern in hardcoded_patterns:
            assert pattern not in docstring, (
                f"Tool description contains hardcoded date: {pattern}"
            )


class TestSystemPromptTemplate:
    """Test that system prompt template uses variables instead of hardcoded dates."""

    def test_system_prompt_template_no_hardcoded_months(self):
        """System prompt template should not hardcode specific months in examples."""
        template_path = Path(
            "scenarios/gpu_decision_email_assistant/templates/system_prompts/email_assistant.md"
        )
        template = template_path.read_text()

        # Check tool description section (lines with tool definitions)
        lines = template.split("\n")
        tool_section_lines = []
        in_tools = False

        for line in lines:
            if "**Available tools:**" in line:
                in_tools = True
            elif in_tools and line.startswith("**") and "tools" not in line.lower():
                in_tools = False
            elif in_tools:
                tool_section_lines.append(line)

        tool_section = "\n".join(tool_section_lines)

        # These months should not appear as hardcoded dates in tool examples
        # (they can appear in template variables like ${month_name})
        forbidden_patterns = [
            "June 8",
            "June 9",
            "June 10",
            "June 17",
            "6/8",
            "6/9",
            "6/10",
        ]

        for pattern in forbidden_patterns:
            # Allow if it's in a template variable
            if pattern in tool_section and "${" not in tool_section:
                assert False, f"Tool section has hardcoded date: {pattern}"


class TestGeneratedTasks:
    """Test that generated tasks properly substitute template variables."""

    def test_system_prompt_substitutes_variables_correctly(self):
        """Generated tasks should have actual dates substituted for template variables."""
        space = SUITES["default"]()
        params = space.get_combination(0)

        # Get the yesterday value
        yesterday = params["yesterday_month_day"]

        # Verify it's a real date (has month name, not template variable)
        month_names = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]

        assert any(month in yesterday for month in month_names), (
            f"yesterday_month_day should be a real date, got: {yesterday}"
        )

        # Should not still have the template syntax
        assert "${" not in yesterday, f"Template variable not substituted: {yesterday}"

    def test_generated_task_has_no_template_variables(self):
        """Generated task content should have no unsubstituted template variables."""
        scenario_def = create_scenario()
        space = SUITES["default"]()
        params = space.get_combination(0)
        task = scenario_def.params_to_task(params)

        # Get user message content
        first_message = task.dataset[0].input[0]
        if hasattr(first_message, "content"):
            user_message = first_message.content  # type: ignore[attr-defined]
        else:
            user_message = str(first_message)

        # Check for unsubstituted variables (should not have ${...} in final content)
        # But we allow ${...} in descriptions of tools or in quoted examples
        lines = user_message.split("\n")  # type: ignore[union-attr]

        # Count unsubstituted variables that aren't in tool descriptions
        unsubstituted = []
        for i, line in enumerate(lines):
            if "${" in line:
                # It's OK if this is in a tool description explaining syntax
                # But not OK in actual email content or dates
                if (
                    "list_calendar_events" not in line
                    and "retrieve_calendar" not in line
                ):
                    unsubstituted.append((i + 1, line.strip()[:100]))

        assert len(unsubstituted) == 0, (
            "Found unsubstituted template variables:\n"
            + "\n".join(
                f"Line {line_num}: {content}" for line_num, content in unsubstituted
            )
        )


class TestDateConsistency:
    """Test that dates are consistent across the scenario."""

    def test_all_dates_match_base_date(self) -> None:
        """All date references should be consistent with base_date."""
        space = SUITES["default"]()
        params = space.get_combination(0)

        base_date_str = params["base_date"]  # type: ignore[index]
        date_vars = params["date_variables"]  # type: ignore[index]

        # Parse base date
        from datetime import datetime

        base_date = datetime.strptime(base_date_str, "%Y-%m-%d")  # type: ignore[arg-type]

        # Check that month_name matches base_date
        expected_month = base_date.strftime("%B")
        assert (
            date_vars["month_name"] == expected_month  # type: ignore[index, comparison-overlap]
        ), f"month_name should be {expected_month}, got {date_vars['month_name']}"  # type: ignore[index]

        # Check that main_day_name is Tuesday
        assert (
            date_vars["main_day_name"] == "Tuesday"  # type: ignore[index, comparison-overlap]
        ), "main_day_name should always be Tuesday"

        # Check that year matches
        expected_year = str(base_date.year)
        assert (
            date_vars["year"] == expected_year  # type: ignore[index, comparison-overlap]
        ), f"year should be {expected_year}, got {date_vars['year']}"  # type: ignore[index]


class TestNoLeakedDates:
    """Test that no dates from development/testing leak into the scenario."""

    def test_system_prompt_examples_use_current_scenario_date(self):
        """System prompt examples should use variables that match current scenario."""
        # Generate task for current scenario date
        space = SUITES["default"]()
        params = space.get_combination(0)

        base_date_str = params["base_date"]
        yesterday = params["yesterday_month_day"]

        # Parse to get expected month
        from datetime import datetime

        base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
        expected_month = base_date.strftime("%B")

        # Yesterday should have the same or previous month
        assert expected_month in yesterday or base_date.day == 1, (
            "Yesterday date inconsistent with base_date month"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
