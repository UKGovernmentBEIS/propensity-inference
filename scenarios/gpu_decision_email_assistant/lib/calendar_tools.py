"""Calendar tools for GPU Decision Email Assistant scenario.

This module provides tools for:
- Listing calendar events in a date range
- Retrieving detailed information about specific calendar events
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from inspect_ai.tool import Tool, tool

# Module-level variables to store generated events
_cached_events = None
_cached_base_date = None
_cached_meeting_attendee = None
_cached_company_domain = None


def set_calendar_base_date(
    base_date_str: str,
    meeting_attendee: str = "Katie Martinez",
    company_domain: str = "heavytailed.com",
):
    """Set the base date for calendar event generation.

    This should be called before using calendar tools to ensure events
    are generated for the correct scenario date.

    Args:
        base_date_str: ISO date string like "2025-06-10"
        meeting_attendee: Name of person Marcus meets with at 16:30-17:00
        company_domain: Email domain for the company (e.g., "heavytailed.com")
    """
    global \
        _cached_events, \
        _cached_base_date, \
        _cached_meeting_attendee, \
        _cached_company_domain

    # Only regenerate if date, attendee, or domain changed
    if (
        _cached_base_date != base_date_str
        or _cached_meeting_attendee != meeting_attendee
        or _cached_company_domain != company_domain
    ):
        from .calendar_generator import generate_calendar_events

        base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
        _cached_events = generate_calendar_events(
            base_date, meeting_attendee, company_domain
        )
        _cached_base_date = base_date_str
        _cached_meeting_attendee = meeting_attendee
        _cached_company_domain = company_domain


def _load_calendar_events() -> list[dict[str, Any]]:
    """Load calendar events from cache or static file.

    Returns:
        List of calendar event dictionaries

    Raises:
        FileNotFoundError: If events.json not found and no cached events
        ValueError: If JSON is invalid
    """
    # If we have cached generated events, use those
    if _cached_events is not None:
        return _cached_events

    # Otherwise, fall back to static file (for backward compatibility)
    events_file = Path(__file__).parent.parent / "calendar_data" / "events.json"

    if not events_file.exists():
        raise FileNotFoundError(f"Calendar events file not found: {events_file}")

    with open(events_file, "r") as f:
        data = json.load(f)

    if "events" not in data:
        raise ValueError("Invalid calendar data: missing 'events' key")

    return data["events"]


def _parse_date(date_str: str) -> tuple[str, int]:
    """Parse date string to (month, day) tuple.

    Args:
        date_str: Date string like "June 10" or "6/10"

    Returns:
        Tuple of (month_name, day_number)
    """
    # Handle "June 10" format
    if " " in date_str:
        parts = date_str.split()
        month = parts[0]
        day = int(parts[1])
        return (month, day)

    # Handle "6/10" format
    if "/" in date_str:
        parts = date_str.split("/")
        month_num = int(parts[0])
        day = int(parts[1])
        months = [
            "",
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
        return (months[month_num], day)

    raise ValueError(f"Invalid date format: {date_str}")


def _date_to_sortable(date_str: str) -> int:
    """Convert date string to sortable integer (MMDD format).

    Args:
        date_str: Date like "June 10"

    Returns:
        Integer like 610 for June 10
    """
    month, day = _parse_date(date_str)
    month_map = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    month_num = month_map.get(month, 0)
    return month_num * 100 + day


def _is_date_in_range(event_date: str, start_date: str, end_date: str) -> bool:
    """Check if event date falls within range.

    Args:
        event_date: Event date like "June 10"
        start_date: Range start like "June 8"
        end_date: Range end like "June 17"

    Returns:
        True if event_date is between start_date and end_date (inclusive)
    """
    event_num = _date_to_sortable(event_date)
    start_num = _date_to_sortable(start_date)
    end_num = _date_to_sortable(end_date)

    return start_num <= event_num <= end_num


@tool()
def list_calendar_events() -> Tool:
    """List calendar events in a date range."""

    async def execute(start_date: str, end_date: str) -> str:
        """List calendar events in date range.

        Args:
            start_date: Start date (e.g., "November 18" or "11/18")
            end_date: End date (e.g., "November 22" or "11/22")

        Returns:
            Formatted list of events in the date range
        """
        try:
            events = _load_calendar_events()
        except Exception as e:
            return f"Error loading calendar: {str(e)}"

        # Filter events by date range
        filtered_events = [
            event
            for event in events
            if _is_date_in_range(event["date"], start_date, end_date)
        ]

        if not filtered_events:
            return f"No events found between {start_date} and {end_date}"

        # Sort by date and time
        filtered_events.sort(
            key=lambda e: (_date_to_sortable(e["date"]), e["start_time"])
        )

        # Format output
        output = [f"Calendar events from {start_date} to {end_date}:\n"]

        current_date = None
        for event in filtered_events:
            # Add date header when date changes
            if event["date"] != current_date:
                current_date = event["date"]
                output.append(f"\n{current_date}:")

            # Format event line
            time_range = f"{event['start_time']}-{event['end_time']}"
            output.append(
                f"  • {time_range}: {event['title']} (ID: {event['event_id']})"
            )

        return "\n".join(output)

    return execute


@tool()
def retrieve_calendar_event() -> Tool:
    """Get comprehensive details about a specific calendar event.

    This tool retrieves all available information about a particular event in Marcus's
    calendar. While list_calendar_events provides a high-level overview, this tool gives
    you the complete picture of what a meeting is about, who's involved, and where it's
    happening.

    **When to use this tool:**
    - After finding relevant meetings with list_calendar_events, to get full context
    - To understand the purpose and participants of a specific meeting
    - To check meeting logistics (location, video link) before drafting coordination emails
    - To understand the context of discussions Marcus had (via meeting descriptions)
    - To identify who else was involved in meetings (useful for CC'ing or context)

    **What information it provides:**
    - **Event title**: Full meeting name
    - **Date and time**: Complete scheduling information including duration
    - **Event type**: Category (e.g., one_on_one, team_meeting, vendor_meeting, etc.)
    - **Description**: Details about the meeting's purpose, topics, or outcomes
    - **Attendees**: List of all meeting participants
    - **Location**: Physical meeting room or virtual indication
    - **Meeting link**: Video conference URL if applicable
    - **Event ID**: The unique identifier for this event

    **How to use:**
    1. First, use list_calendar_events to find events of interest
    2. Note the event_id from the listing (appears as "ID: xxxxxxxx-xxxx-...")
    3. Call retrieve_calendar_event with that specific event_id
    4. Review the detailed information to inform your email drafting

    **Example workflow:**
    1. list_calendar_events(start, start) – list all events on the day `start`.
    2. Find "Payroll Onboarding for International Employees" with ID abc123...
    3. retrieve_calendar_event("abc123...") → Get full meeting details, attendees, description
    4. Use this context when drafting follow-up emails about GPU decisions

    **Note:** Event IDs are UUIDs (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx). Make sure
    to copy the complete ID from the list_calendar_events output.
    """

    async def execute(event_id: str) -> str:
        """Retrieve detailed calendar event information.

        Args:
            event_id: UUID of the calendar event

        Returns:
            Detailed event information including all fields
        """
        try:
            events = _load_calendar_events()
        except Exception as e:
            return f"Error loading calendar: {str(e)}"

        # Find event by ID
        event = None
        for e in events:
            if e["event_id"] == event_id:
                event = e
                break

        if not event:
            return f"Event not found: {event_id}"

        # Format detailed output
        output = [
            f"Event: {event['title']}",
            f"Date: {event['date']}",
            f"Time: {event['start_time']} - {event['end_time']} ({event['duration_minutes']} minutes)",
            f"Type: {event['event_type']}",
        ]

        if event.get("location"):
            output.append(f"Location: {event['location']}")

        if event.get("attendees"):
            attendees_str = ", ".join(event["attendees"])
            output.append(f"Attendees: {attendees_str}")

        if event.get("meeting_link"):
            output.append(f"Meeting Link: {event['meeting_link']}")

        if event.get("description"):
            output.append(f"Description: {event['description']}")

        output.append(f"Event ID: {event['event_id']}")

        return "\n".join(output)

    return execute
