"""Utility functions for SEM v2 scenario."""


def normalize_report_id(report_id: str) -> str:
    """
    Normalize a report ID to handle various formats.

    Handles cases like:
    - "RPT-001" -> "RPT-001"
    - "RPT-001.md" -> "RPT-001"
    - "alerts/RPT-001.md" -> "RPT-001"
    - "/monitoring/alerts/RPT-001.md" -> "RPT-001"

    Args:
        report_id: Report ID in any format

    Returns:
        Normalized report ID (just the RPT-XXX part)
    """
    # Strip whitespace
    report_id = report_id.strip()

    # Extract just the filename if it's a path
    if "/" in report_id:
        report_id = report_id.split("/")[-1]

    # Remove .md extension if present
    if report_id.endswith(".md"):
        report_id = report_id[:-3]

    return report_id
