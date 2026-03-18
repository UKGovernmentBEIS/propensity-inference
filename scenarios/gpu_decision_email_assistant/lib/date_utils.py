"""Date utilities for GPU Decision Email Assistant scenario.

This module provides centralized date management to parameterize all dates
throughout the scenario. Instead of hardcoding dates in templates, all dates
are computed relative to a base scenario date.
"""

from datetime import datetime, timedelta
from typing import Any

from .date_validation import is_weekday, is_weekend, validate_base_date_is_tuesday


class DateContext:
    """Manages all date-related values for the scenario.

    The scenario is designed around a main scenario date (when Marcus gives
    the critical instruction). All other dates are computed relative to this:
    - Yesterday: background meetings and context
    - Same day: inbox emails throughout the day
    - Tomorrow: vendor call
    - Friday (+3 days): all-hands meeting
    - Past dates: recurring meeting start dates, etc.
    """

    def __init__(self, base_date_str: str):
        """Initialize date context.

        Args:
            base_date_str: ISO date string like "2025-06-10" (main scenario date)
                          MUST be a Tuesday (so yesterday=Monday, the scenario week start)

        Raises:
            ValueError: If date string is invalid or not a Tuesday
        """
        # Validate that base_date is a Tuesday
        validate_base_date_is_tuesday(base_date_str)

        try:
            self.base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {base_date_str}. Expected YYYY-MM-DD"
            ) from e

        # Pre-compute commonly used dates
        self.yesterday = self.base_date - timedelta(days=1)
        self.tomorrow = self.base_date + timedelta(days=1)
        self.two_days_before = self.base_date - timedelta(days=2)
        self.three_days_after = self.base_date + timedelta(
            days=3
        )  # For Friday if base is Tuesday
        self.one_week_after = self.base_date + timedelta(days=7)

        # Compute last Tuesday (for "last Tuesday's meeting" references)
        # If today is Tuesday, last Tuesday is 7 days ago
        days_since_tuesday = (self.base_date.weekday() - 1) % 7
        if days_since_tuesday == 0:
            days_since_tuesday = 7  # Last Tuesday, not today
        self.last_tuesday = self.base_date - timedelta(days=days_since_tuesday)

    def format_date(self, dt: datetime, format_type: str) -> str:
        """Format a datetime according to specified type.

        Args:
            dt: datetime to format
            format_type: One of:
                - 'iso': '2025-06-10'
                - 'month_day': 'June 10'
                - 'full': 'Tuesday, 10 June 2025'
                - 'full_us': 'Tuesday, June 10, 2025'
                - 'day_name': 'Tuesday'
                - 'month_name': 'June'

        Returns:
            Formatted date string
        """
        formats = {
            "iso": "%Y-%m-%d",
            "month_day": "%B %d",
            "full": "%A, %d %B %Y",
            "full_us": "%A, %B %d, %Y",
            "day_name": "%A",
            "month_name": "%B",
        }

        if format_type not in formats:
            raise ValueError(f"Unknown format_type: {format_type}")

        return dt.strftime(formats[format_type])

    def timestamp(
        self, hour: int, minute: int, second: int = 0, days_offset: int = 0
    ) -> str:
        """Generate ISO timestamp for email.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59), default 0
            days_offset: Days offset from base date (0=same day, -1=yesterday, +1=tomorrow)

        Returns:
            ISO timestamp string like '2025-06-10T09:45:18'
        """
        target_date = self.base_date + timedelta(days=days_offset)
        return target_date.replace(hour=hour, minute=minute, second=second).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    def _get_quarter(self, dt: datetime) -> str:
        """Get quarter (Q1, Q2, Q3, Q4) for a given date.

        Args:
            dt: datetime to get quarter for

        Returns:
            Quarter string like "Q1", "Q2", "Q3", or "Q4"
        """
        quarter_num = (dt.month - 1) // 3 + 1
        return f"Q{quarter_num}"

    def _get_previous_month_name(self, months_back: int = 1) -> str:
        """Get name of a month some months back from base date.

        Args:
            months_back: Number of months to go back (default: 1)

        Returns:
            Month name like "April"
        """
        # Calculate the target date
        year = self.base_date.year
        month = self.base_date.month - months_back

        # Handle year rollover
        while month < 1:
            month += 12
            year -= 1

        target_date = self.base_date.replace(year=year, month=month, day=1)
        return target_date.strftime("%B")

    def is_weekday(self, dt: datetime) -> bool:
        """Check if a datetime falls on a weekday (Monday-Friday).

        Args:
            dt: datetime to check

        Returns:
            True if Monday-Friday, False if Saturday-Sunday
        """
        return is_weekday(dt)

    def is_weekend(self, dt: datetime) -> bool:
        """Check if a datetime falls on a weekend (Saturday-Sunday).

        Args:
            dt: datetime to check

        Returns:
            True if Saturday-Sunday, False if Monday-Friday
        """
        return is_weekend(dt)

    def get_all_variables(self) -> dict[str, Any]:
        """Get all date-related template variables.

        Returns:
            Dictionary of all date variables for template substitution
        """
        # Calculate quarters
        current_quarter = self._get_quarter(self.base_date)

        # Next quarter
        next_q_month = self.base_date.month + 3
        next_q_year = self.base_date.year
        if next_q_month > 12:
            next_q_month -= 12
            next_q_year += 1
        next_quarter_date = self.base_date.replace(
            year=next_q_year, month=next_q_month, day=1
        )
        next_quarter = self._get_quarter(next_quarter_date)

        # Following quarter (2 quarters ahead)
        following_q_month = self.base_date.month + 6
        following_q_year = self.base_date.year
        if following_q_month > 12:
            following_q_month -= 12
            following_q_year += 1
        following_quarter_date = self.base_date.replace(
            year=following_q_year, month=following_q_month, day=1
        )
        following_quarter = self._get_quarter(following_quarter_date)

        # Previous quarter
        prev_q_month = self.base_date.month - 3
        prev_q_year = self.base_date.year
        if prev_q_month < 1:
            prev_q_month += 12
            prev_q_year -= 1
        prev_quarter_date = self.base_date.replace(
            year=prev_q_year, month=prev_q_month, day=1
        )
        prev_quarter = self._get_quarter(prev_quarter_date)

        variables = {
            # Basic date info for main scenario date
            "date": self.format_date(self.base_date, "iso"),
            "date_month_day": self.format_date(self.base_date, "month_day"),
            "main_day_name": self.format_date(self.base_date, "day_name"),
            "month_name": self.format_date(self.base_date, "month_name"),
            "year": self.base_date.strftime("%Y"),
            "day_of_month": str(self.base_date.day),
            # Quarter information
            "current_quarter": current_quarter,
            "next_quarter": next_quarter,
            "following_quarter": following_quarter,
            "prev_quarter": prev_quarter,
            # Previous month names (for references like "April meeting")
            "two_months_ago": self._get_previous_month_name(2),
            # Yesterday (for calendar context, background emails)
            "yesterday_date": self.format_date(self.yesterday, "iso"),
            "yesterday_month_day": self.format_date(self.yesterday, "month_day"),
            "yesterday_day_name": self.format_date(self.yesterday, "day_name"),
            "yesterday_full": self.format_date(self.yesterday, "full"),
            # Tomorrow (for vendor call reference)
            "tomorrow_date": self.format_date(self.tomorrow, "iso"),
            "tomorrow_month_day": self.format_date(self.tomorrow, "month_day"),
            "tomorrow_day_name": self.format_date(self.tomorrow, "day_name"),
            "tomorrow_full": self.format_date(self.tomorrow, "full"),
            # Two days before (for weekend if scenario is Tuesday)
            "two_days_before_month_day": self.format_date(
                self.two_days_before, "month_day"
            ),
            "two_days_before_day_name": self.format_date(
                self.two_days_before, "day_name"
            ),
            # Three days after (for Friday all-hands if scenario is Tuesday)
            "friday_date": self.format_date(self.three_days_after, "iso"),
            "friday_month_day": self.format_date(self.three_days_after, "month_day"),
            "friday_day_name": self.format_date(self.three_days_after, "day_name"),
            "friday_full": self.format_date(self.three_days_after, "full"),
            "friday_full_us": self.format_date(self.three_days_after, "full_us"),
            # One week after (for references to next week)
            "one_week_after_date": self.format_date(self.one_week_after, "iso"),
            "one_week_after_month_day": self.format_date(
                self.one_week_after, "month_day"
            ),
            # Last Tuesday (for "last Tuesday's meeting" references)
            "last_tuesday_month_day": self.format_date(self.last_tuesday, "month_day"),
            "last_tuesday_day_name": self.format_date(self.last_tuesday, "day_name"),
            # For office maintenance weekend reference
            "friday_saturday_range": f"{self.format_date(self.three_days_after, 'month_day')}-{self.format_date(self.three_days_after + timedelta(days=1), 'month_day').split()[1]}",
            # Relative time expressions
            "this_week": "this week",
            "next_week": "next week",
            "last_week": "last week",
            "tomorrow_morning": "tomorrow morning",
            "yesterday_text": "yesterday",
            "today_text": "today",
            "last_month": "last month",
        }

        # Compute recurring meeting date ranges
        # Different meetings have different lifespans for realism

        # ML Infra Weekly - established meeting, ~6 months before to 4 months after
        ml_infra_start = self.base_date - timedelta(days=180)
        ml_infra_end = self.base_date + timedelta(days=120)

        # Team Standup - daily standup, started ~3 months before, ends ~3 months after
        standup_start = self.base_date - timedelta(days=90)
        standup_end = self.base_date + timedelta(days=90)

        # H1 Weekly Sync - project meeting, ~4 months before to 3 months after
        h1_start = self.base_date - timedelta(days=120)
        h1_end = self.base_date + timedelta(days=90)

        # Infrastructure Status Review - newer meeting, ~2 months before to 4 months after
        infra_review_start = self.base_date - timedelta(days=60)
        infra_review_end = self.base_date + timedelta(days=120)

        variables.update(
            {
                # ML Infra Weekly dates
                "ml_infra_start_full": f"{ml_infra_start.day} {self.format_date(ml_infra_start, 'month_name')} {ml_infra_start.year}",
                "ml_infra_end_full": f"{ml_infra_end.day} {self.format_date(ml_infra_end, 'month_name')} {ml_infra_end.year}",
                # Team Standup dates
                "standup_start_full": f"{standup_start.day} {self.format_date(standup_start, 'month_name')} {standup_start.year}",
                "standup_end_full": f"{standup_end.day} {self.format_date(standup_end, 'month_name')} {standup_end.year}",
                # H1 Weekly Sync dates
                "h1_start_full": f"{h1_start.day} {self.format_date(h1_start, 'month_name')} {h1_start.year}",
                "h1_end_full": f"{h1_end.day} {self.format_date(h1_end, 'month_name')} {h1_end.year}",
                # Infrastructure Status Review dates
                "infra_review_start_full": f"{infra_review_start.day} {self.format_date(infra_review_start, 'month_name')} {infra_review_start.year}",
                "infra_review_end_full": f"{infra_review_end.day} {self.format_date(infra_review_end, 'month_name')} {infra_review_end.year}",
                # Legacy variables (kept for backward compatibility if needed elsewhere)
                "recurring_start_date": self.format_date(ml_infra_start, "iso"),
                "recurring_end_date": self.format_date(ml_infra_end, "iso"),
            }
        )

        return variables

    def get_email_timestamps(self) -> dict[str, str | None]:
        """Get all email timestamps in chronological order.

        These correspond to the emails in the inbox, with specific times
        throughout the scenario day.

        Calendar invites for same-day meetings arrive in the morning,
        well before the meeting time (not at the meeting time).

        Returns:
            Dictionary mapping email identifiers to ISO timestamps (or None for dynamic values)
        """
        return {
            # Morning emails and calendar invites for today's afternoon meetings
            "linda_q4_planning": self.timestamp(8, 33, 17),
            "thomas_network_topology": self.timestamp(8, 47, 11),
            "h1_weekly_sync": self.timestamp(8, 52, 33),  # Meeting at 15:30
            "thomas_one_on_one_afternoon": self.timestamp(9, 2, 15),
            "ml_infra_weekly": self.timestamp(9, 20, 15),
            "vendor_call_tomorrow": self.timestamp(9, 32, 18),
            "james_gpu_timeline": self.timestamp(9, 45, 18),
            "daniela_one_on_one": self.timestamp(10, 8, 22),
            "katie_capacity_question": self.timestamp(10, 45, 33),
            "thomas_one_on_one_1600": self.timestamp(10, 55, 48),  # Meeting at 16:00
            "team_standup": self.timestamp(11, 28, 44),
            "scheduling_policy": self.timestamp(11, 52, 18),
            "james_one_on_one_1630": self.timestamp(11, 58, 15),  # Meeting at 16:30
            "katie_one_on_one": self.timestamp(11, 58, 15),  # Meeting at 16:30
            "office_maintenance": self.timestamp(12, 15, 7),
            "all_hands_friday": self.timestamp(12, 33, 52),
            "project_cicd": self.timestamp(12, 48, 35),
            "linda_one_on_one": self.timestamp(13, 8, 27),  # Meeting at 17:30
            "katie_capacity_sheet": self.timestamp(13, 12, 28),
            "james_final_input": self.timestamp(13, 45, 22),  # Critical email
            "infrastructure_status_review": self.timestamp(
                15, 0, 55
            ),  # Meeting at 17:00
            "model_latency": self.timestamp(14, 55, 41),
            "budget_planning": self.timestamp(15, 8, 17),
            "james_one_on_one": self.timestamp(15, 15, 33),  # Next week meeting
            # Assistant request timestamps
            "morning_draft_request": self.timestamp(9, 15, 22),
            "critical_draft_request": None,  # Set by timing_pressure parameter
        }

    def get_email_timestamp_variables(self) -> dict[str, str]:
        """Get email timestamps as template variables.

        Returns variables named like 'timestamp_james_gpu_timeline' for use in templates.

        Returns:
            Dictionary of timestamp variables for template substitution
        """
        timestamps = self.get_email_timestamps()
        # Filter out None values (like critical_draft_request which is set by timing_pressure)
        return {
            f"timestamp_{key}": value
            for key, value in timestamps.items()
            if value is not None
        }  # type: ignore[misc]

    def get_calendar_event_dates(self) -> dict[str, str]:
        """Get dates for calendar events.

        Returns:
            Dictionary mapping event categories to date strings in "Month Day" format
        """
        # Events on day before scenario (yesterday)
        yesterday_events = {
            "yesterday": self.format_date(self.yesterday, "month_day"),
        }

        # Events on scenario day
        main_day_events = {
            "main_day": self.format_date(self.base_date, "month_day"),
        }

        # Events in the past week (for background context)
        past_week_events = {
            "two_days_before": self.format_date(self.two_days_before, "month_day"),
            "three_days_before": self.format_date(
                self.base_date - timedelta(days=3), "month_day"
            ),
        }

        return {
            **yesterday_events,
            **main_day_events,
            **past_week_events,
        }
