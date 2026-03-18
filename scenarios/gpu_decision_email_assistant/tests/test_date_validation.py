"""Comprehensive date validation tests for GPU Decision Email Assistant scenario.

These tests ensure:
1. DateContext requires Tuesday base dates (so yesterday=Monday, week start)
2. Calendar events maintain weekday structure
3. Date variations are properly spaced (7-day increments)
4. Business meetings only occur on weekdays
5. Future date variations maintain proper structure
"""

from datetime import datetime, timedelta

import pytest

from scenarios.gpu_decision_email_assistant.lib.calendar_generator import (
    generate_calendar_events,
)
from scenarios.gpu_decision_email_assistant.lib.date_utils import DateContext
from scenarios.gpu_decision_email_assistant.lib.date_validation import (
    generate_weekly_dates,
    is_weekday,
    is_weekend,
    validate_base_date_is_tuesday,
    validate_weekly_spacing,
)


class TestBasicDateValidation:
    """Test basic date validation functions."""

    def test_validate_tuesday_accepts_valid_dates(self):
        """Valid Tuesday dates should pass validation."""
        valid_tuesdays = [
            "2025-01-14",  # Winter Tuesday
            "2025-04-08",  # Spring Tuesday
            "2025-06-10",  # Summer Tuesday (default)
            "2025-07-08",  # Summer Tuesday
            "2025-10-07",  # Fall Tuesday
            "2024-12-31",  # Year-end Tuesday
        ]
        for date_str in valid_tuesdays:
            # Should not raise
            validate_base_date_is_tuesday(date_str)

    def test_validate_tuesday_rejects_non_tuesdays(self):
        """Non-Tuesday dates should fail validation."""
        invalid_dates = [
            ("2025-06-09", "Monday"),
            ("2025-06-11", "Wednesday"),
            ("2025-06-12", "Thursday"),
            ("2025-06-13", "Friday"),
            ("2025-06-14", "Saturday"),
            ("2025-06-15", "Sunday"),
        ]
        for date_str, day_name in invalid_dates:
            with pytest.raises(ValueError) as exc_info:
                validate_base_date_is_tuesday(date_str)
            assert "must be a Tuesday" in str(exc_info.value)
            assert day_name in str(exc_info.value)

    def test_validate_tuesday_rejects_invalid_format(self):
        """Invalid date formats should fail validation."""
        invalid_formats = [
            "06-10-2025",  # Wrong order
            "2025/06/10",  # Wrong separator
            "June 10, 2025",  # Human format
            "not-a-date",  # Garbage
        ]
        for date_str in invalid_formats:
            with pytest.raises(ValueError) as exc_info:
                validate_base_date_is_tuesday(date_str)
            # Should mention invalid format
            assert "Invalid date format" in str(exc_info.value)

    def test_is_weekday_helper(self):
        """Test weekday detection helper."""
        assert is_weekday(datetime(2025, 6, 9))  # Monday
        assert is_weekday(datetime(2025, 6, 10))  # Tuesday
        assert is_weekday(datetime(2025, 6, 11))  # Wednesday
        assert is_weekday(datetime(2025, 6, 12))  # Thursday
        assert is_weekday(datetime(2025, 6, 13))  # Friday
        assert not is_weekday(datetime(2025, 6, 14))  # Saturday
        assert not is_weekday(datetime(2025, 6, 15))  # Sunday

    def test_is_weekend_helper(self):
        """Test weekend detection helper."""
        assert not is_weekend(datetime(2025, 6, 9))  # Monday
        assert not is_weekend(datetime(2025, 6, 10))  # Tuesday
        assert not is_weekend(datetime(2025, 6, 11))  # Wednesday
        assert not is_weekend(datetime(2025, 6, 12))  # Thursday
        assert not is_weekend(datetime(2025, 6, 13))  # Friday
        assert is_weekend(datetime(2025, 6, 14))  # Saturday
        assert is_weekend(datetime(2025, 6, 15))  # Sunday


class TestWeeklyDateGeneration:
    """Test weekly date generation and spacing validation."""

    def test_generate_weekly_dates_produces_correct_sequence(self):
        """Weekly date generation should produce 7-day spaced Tuesdays."""
        dates = generate_weekly_dates("2025-06-10", 4)
        expected = [
            "2025-06-10",  # Week 0
            "2025-06-17",  # Week 1
            "2025-06-24",  # Week 2
            "2025-07-01",  # Week 3
        ]
        assert dates == expected

        # Verify all are Tuesdays
        for date_str in dates:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            assert dt.weekday() == 1, f"{date_str} is not a Tuesday"

    def test_generate_weekly_dates_rejects_non_tuesday(self):
        """Weekly date generation should reject non-Tuesday start dates."""
        with pytest.raises(ValueError) as exc_info:
            generate_weekly_dates("2025-06-09", 4)  # Monday
        assert "must be a Tuesday" in str(exc_info.value)

    def test_validate_weekly_spacing_accepts_valid_sequences(self):
        """Valid weekly sequences should pass validation."""
        valid_sequences = [
            ["2025-06-10"],  # Single date
            ["2025-06-10", "2025-06-17"],  # Two weeks
            ["2025-06-10", "2025-06-17", "2025-06-24", "2025-07-01"],  # Four weeks
            ["2025-01-14", "2025-01-21", "2025-01-28"],  # January sequence
        ]
        for sequence in valid_sequences:
            # Should not raise
            validate_weekly_spacing(sequence)

    def test_validate_weekly_spacing_rejects_non_weekly(self):
        """Non-weekly spacing should fail validation."""
        with pytest.raises(ValueError) as exc_info:
            # Use two Tuesdays that are 14 days apart (not 7)
            validate_weekly_spacing(["2025-06-10", "2025-06-24"])  # 14 days apart
        assert "must be exactly 7 days apart" in str(exc_info.value)
        assert "14 days" in str(exc_info.value)

    def test_validate_weekly_spacing_rejects_non_tuesday_in_list(self):
        """Lists with non-Tuesday dates should fail validation."""
        with pytest.raises(ValueError) as exc_info:
            validate_weekly_spacing(["2025-06-10", "2025-06-18"])  # Second is Wed
        assert "must be a Tuesday" in str(exc_info.value)


class TestDateContext:
    """Test DateContext class initialization and validation."""

    def test_date_context_accepts_valid_tuesday(self):
        """DateContext should accept valid Tuesday dates."""
        dc = DateContext("2025-06-10")
        assert dc.base_date.strftime("%Y-%m-%d") == "2025-06-10"
        assert dc.base_date.weekday() == 1  # Tuesday

    def test_date_context_rejects_non_tuesday(self):
        """DateContext should reject non-Tuesday dates."""
        with pytest.raises(ValueError) as exc_info:
            DateContext("2025-06-09")  # Monday
        assert "must be a Tuesday" in str(exc_info.value)

    def test_date_context_computes_correct_relative_dates(self):
        """DateContext should compute correct relative dates."""
        dc = DateContext("2025-06-10")  # Tuesday

        # Yesterday should be Monday
        assert dc.yesterday.weekday() == 0  # Monday
        assert dc.yesterday == datetime(2025, 6, 9)

        # Two days before should be Sunday
        assert dc.two_days_before.weekday() == 6  # Sunday
        assert dc.two_days_before == datetime(2025, 6, 8)

        # Tomorrow should be Wednesday
        assert dc.tomorrow.weekday() == 2  # Wednesday
        assert dc.tomorrow == datetime(2025, 6, 11)

        # Three days after should be Friday
        assert dc.three_days_after.weekday() == 4  # Friday
        assert dc.three_days_after == datetime(2025, 6, 13)

    def test_date_context_weekday_helpers(self):
        """DateContext weekday helpers should work correctly."""
        dc = DateContext("2025-06-10")

        # Monday (yesterday) is a weekday
        assert dc.is_weekday(dc.yesterday)
        assert not dc.is_weekend(dc.yesterday)

        # Sunday (two days before) is a weekend
        assert not dc.is_weekday(dc.two_days_before)
        assert dc.is_weekend(dc.two_days_before)

        # Friday (three days after) is a weekday
        assert dc.is_weekday(dc.three_days_after)
        assert not dc.is_weekend(dc.three_days_after)


class TestCalendarEventValidation:
    """Test calendar event generation and weekday validation."""

    def test_calendar_events_business_meetings_on_weekdays(self):
        """All business meetings should be on weekdays for default date."""
        base_date = datetime(2025, 6, 10)  # Tuesday
        events = generate_calendar_events(base_date)

        business_event_types = {
            "team_meeting",
            "vendor_meeting",
            "project_meeting",
            "one_on_one",
        }

        for event in events:
            event_type = event.get("event_type")
            if event_type in business_event_types:
                # Parse date
                date_str = event["date"]
                dt = datetime.strptime(f"{date_str} 2025", "%B %d %Y")

                # Verify it's a weekday
                assert is_weekday(dt), (
                    f"Business meeting '{event['title']}' on {dt.strftime('%A')}"
                )

    def test_calendar_events_focus_time_allowed_on_weekend(self):
        """Personal focus_time events can be on weekends."""
        base_date = datetime(2025, 6, 10)  # Tuesday
        events = generate_calendar_events(base_date)

        focus_time_events = [e for e in events if e.get("event_type") == "focus_time"]

        # Should have some focus time events
        assert len(focus_time_events) > 0

        # Two days before Tuesday is Sunday, which should have focus time events
        two_days_before_str = (
            (base_date - timedelta(days=2)).strftime("%B %d").replace(" 0", " ")
        )
        sunday_focus = [
            e for e in focus_time_events if e["date"] == two_days_before_str
        ]
        assert len(sunday_focus) > 0, "Expected focus_time events on Sunday"

    def test_calendar_has_required_event_types(self):
        """Calendar should include all required event types."""
        base_date = datetime(2025, 6, 10)  # Tuesday
        events = generate_calendar_events(base_date)

        event_types = {e.get("event_type") for e in events}

        required_types = {
            "team_meeting",
            "vendor_meeting",
            "project_meeting",
            "focus_time",
        }

        assert required_types.issubset(event_types), (
            f"Missing event types: {required_types - event_types}"
        )


class TestFutureDateVariations:
    """Test that calendar events maintain structure across different dates.

    These tests are designed to be extended as new dates are added to the parameter space.
    They ensure that the scenario maintains proper weekday structure regardless of date.
    """

    # Seasonal Tuesday dates for testing
    SEASONAL_DATES = [
        ("2025-01-14", "Winter"),  # January Tuesday
        ("2025-04-08", "Spring"),  # April Tuesday
        ("2025-06-10", "Summer"),  # June Tuesday (default)
        ("2025-07-08", "Summer"),  # July Tuesday
        ("2025-10-07", "Fall"),  # October Tuesday
    ]

    @pytest.mark.parametrize("base_date_str,season", SEASONAL_DATES)
    def test_calendar_events_maintain_weekday_structure(self, base_date_str, season):
        """Calendar events maintain weekday structure across all dates."""
        base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
        events = generate_calendar_events(base_date)

        business_event_types = {
            "team_meeting",
            "vendor_meeting",
            "project_meeting",
            "one_on_one",
        }

        for event in events:
            event_type = event.get("event_type")
            if event_type in business_event_types:
                # Parse date (need to extract year from base_date)
                date_str = event["date"]
                dt = datetime.strptime(f"{date_str} {base_date.year}", "%B %d %Y")

                # Verify it's a weekday
                assert is_weekday(dt), (
                    f"{season}: Business meeting '{event['title']}' "
                    f"on {dt.strftime('%A')} ({date_str})"
                )

    @pytest.mark.parametrize("base_date_str,season", SEASONAL_DATES)
    def test_date_context_variables_correct(self, base_date_str, season):
        """DateContext produces correct variables for all dates."""
        dc = DateContext(base_date_str)
        variables = dc.get_all_variables()

        # Verify main date
        assert variables["date"] == base_date_str

        # Verify day of week is correct
        dt = datetime.strptime(base_date_str, "%Y-%m-%d")
        assert dt.weekday() == 1, f"{season}: Base date should be Tuesday"
        assert variables["main_day_name"] == "Tuesday"

        # Verify yesterday is Monday
        yesterday = dt - timedelta(days=1)
        assert yesterday.weekday() == 0, f"{season}: Yesterday should be Monday"
        assert variables["yesterday_day_name"] == "Monday"

        # Verify Friday is three days after
        friday = dt + timedelta(days=3)
        assert friday.weekday() == 4, f"{season}: Three days after should be Friday"
        assert variables["friday_day_name"] == "Friday"

    @pytest.mark.parametrize("base_date_str,season", SEASONAL_DATES)
    def test_email_timestamps_are_iso_format(self, base_date_str, season):
        """Email timestamps are properly formatted ISO strings."""
        dc = DateContext(base_date_str)
        timestamps = dc.get_email_timestamps()

        for key, timestamp in timestamps.items():
            if timestamp is None:
                continue  # Skip dynamic timestamps

            # Verify ISO format
            try:
                dt = datetime.fromisoformat(timestamp)
            except ValueError:
                pytest.fail(f"{season}: Invalid timestamp for {key}: {timestamp}")

            # Verify date matches base_date
            expected_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
            assert dt.date() == expected_date, (
                f"{season}: Timestamp {key} has wrong date: "
                f"expected {expected_date}, got {dt.date()}"
            )

    def test_weekly_sequence_maintains_structure(self):
        """Four consecutive weeks maintain proper structure."""
        weekly_sequence = generate_weekly_dates("2025-06-10", 4)

        for base_date_str in weekly_sequence:
            # Each date should produce valid calendar events
            base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
            events = generate_calendar_events(base_date)

            # Verify no business meetings on weekends
            business_event_types = {
                "team_meeting",
                "vendor_meeting",
                "project_meeting",
                "one_on_one",
            }

            for event in events:
                event_type = event.get("event_type")
                if event_type in business_event_types:
                    date_str = event["date"]
                    dt = datetime.strptime(f"{date_str} {base_date.year}", "%B %d %Y")
                    assert is_weekday(dt), (
                        f"Business meeting '{event['title']}' on weekend "
                        f"for base_date {base_date_str}"
                    )


class TestQuarterCalculations:
    """Test quarter and month calculations across different dates."""

    def test_quarter_calculations_for_seasonal_dates(self):
        """Quarter calculations should be correct for all seasonal dates."""
        test_cases = [
            ("2025-01-14", "Q1", "Q2", "Q3", "Q4"),  # January
            ("2025-04-08", "Q2", "Q3", "Q4", "Q1"),  # April
            ("2025-06-10", "Q2", "Q3", "Q4", "Q1"),  # June
            ("2025-07-08", "Q3", "Q4", "Q1", "Q2"),  # July
            ("2025-10-07", "Q4", "Q1", "Q2", "Q3"),  # October
        ]

        for base_date_str, current, next_q, following, prev in test_cases:
            dc = DateContext(base_date_str)
            variables = dc.get_all_variables()

            assert variables["current_quarter"] == current, (
                f"{base_date_str}: current_quarter"
            )
            assert variables["next_quarter"] == next_q, f"{base_date_str}: next_quarter"
            assert variables["following_quarter"] == following, (
                f"{base_date_str}: following_quarter"
            )
            assert variables["prev_quarter"] == prev, f"{base_date_str}: prev_quarter"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
