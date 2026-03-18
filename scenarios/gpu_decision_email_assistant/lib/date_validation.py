"""Date validation utilities for GPU Decision Email Assistant scenario.

This module provides utilities to ensure dates are valid for the scenario structure:
- Base dates must be Tuesdays (so yesterday=Monday, the scenario week start)
- Date variations must be in 7-day increments (weekly)
- Business meetings must be on weekdays only
"""

from datetime import datetime, timedelta


def validate_base_date_is_tuesday(date_str: str) -> None:
    """Validate that a date string represents a Tuesday.

    The scenario is designed around Tuesday as the main action day, which ensures:
    - Yesterday (Monday) is the start of the scenario week
    - All business days (Mon-Fri) can be used for meetings
    - Weekend focus time events (Sunday) make sense

    Args:
        date_str: ISO date string like "2025-06-10"

    Raises:
        ValueError: If the date is not a Tuesday, with explanation
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Expected YYYY-MM-DD format."
        ) from e

    weekday = dt.weekday()  # Monday=0, Sunday=6
    day_name = dt.strftime("%A")

    if weekday != 1:  # Tuesday
        raise ValueError(
            f"base_date must be a Tuesday (so yesterday is Monday, the scenario week start). "
            f"Got {day_name} for date {date_str}. "
            f"Use Tuesday dates: 2024-07-16, 2024-10-15, 2025-01-14, 2025-04-15, 2025-07-15, 2025-10-14, 2026-01-13, 2026-04-14"
        )


def generate_weekly_dates(start_tuesday: str, num_weeks: int) -> list[str]:
    """Generate a sequence of Tuesday dates with weekly spacing.

    Args:
        start_tuesday: ISO date string of a Tuesday (e.g., "2025-06-10")
        num_weeks: Number of weeks to generate

    Returns:
        List of ISO date strings, all Tuesdays, 7 days apart

    Raises:
        ValueError: If start_tuesday is not a Tuesday

    Example:
        >>> generate_weekly_dates("2025-06-10", 4)
        ['2025-06-10', '2025-06-17', '2025-06-24', '2025-07-01']
    """
    # Validate start date
    validate_base_date_is_tuesday(start_tuesday)

    start_dt = datetime.strptime(start_tuesday, "%Y-%m-%d")
    dates = []

    for week in range(num_weeks):
        date = start_dt + timedelta(weeks=week)
        dates.append(date.strftime("%Y-%m-%d"))

    return dates


def validate_weekly_spacing(date_list: list[str]) -> None:
    """Validate that all dates are exactly 7 days apart and are Tuesdays.

    Args:
        date_list: List of ISO date strings

    Raises:
        ValueError: If dates are not all Tuesdays or not exactly 7 days apart
    """
    if len(date_list) < 2:
        # Single date or empty list - just check if Tuesdays
        for date_str in date_list:
            validate_base_date_is_tuesday(date_str)
        return

    # Check all are Tuesdays
    for date_str in date_list:
        validate_base_date_is_tuesday(date_str)

    # Check 7-day spacing
    dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted(date_list)]

    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if delta != 7:
            raise ValueError(
                f"Dates must be exactly 7 days apart (weekly). "
                f"Found {delta} days between {dates[i - 1].strftime('%Y-%m-%d')} "
                f"and {dates[i].strftime('%Y-%m-%d')}"
            )


def is_weekday(dt: datetime) -> bool:
    """Check if a datetime falls on a weekday (Monday-Friday).

    Args:
        dt: datetime object

    Returns:
        True if Monday-Friday, False if Saturday-Sunday
    """
    return dt.weekday() < 5  # Monday=0, Friday=4, Saturday=5, Sunday=6


def is_weekend(dt: datetime) -> bool:
    """Check if a datetime falls on a weekend (Saturday-Sunday).

    Args:
        dt: datetime object

    Returns:
        True if Saturday-Sunday, False if Monday-Friday
    """
    return dt.weekday() >= 5
