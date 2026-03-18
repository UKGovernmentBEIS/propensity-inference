#!/usr/bin/env python3
"""Parse PR body for breaking changes information.

This script parses the GitHub PR body to extract breaking changes information
and determine what version bumps and scenario updates are needed.

Usage:
    python scripts/parse_pr_breaking_changes.py <pr_body>
    python scripts/parse_pr_breaking_changes.py --validate <pr_body>
"""

import json
import re
import sys
from typing import Any

import fire


def parse_breaking_changes(pr_body: str) -> dict[str, Any]:
    """Parse PR body for breaking changes information.

    Args:
        pr_body: The full PR description body

    Returns:
        Dict with keys:
        - has_breaking_changes: bool
        - version_bump_type: "major" or "patch"
        - components: list of components with breaking changes
        - no_breaking_checked: bool (was "No breaking changes" checked?)
        - valid: bool (is the breaking changes section properly filled?)
        - error: str or None (validation error message)
    """
    result = {
        "has_breaking_changes": False,
        "version_bump_type": "patch",
        "components": [],
        "no_breaking_checked": False,
        "valid": False,
        "error": None,
    }

    # Find the Breaking Changes section (accept 1-4 hash marks with flexible whitespace)
    breaking_section_match = re.search(
        r"#{1,4}\s*Breaking Changes\s*\n(.*?)(?=#{1,4}\s*\w+|$)",
        pr_body,
        re.DOTALL | re.IGNORECASE,
    )

    if not breaking_section_match:
        # Provide diagnostic information
        error_msg = "Breaking Changes section not found in PR body"

        # Check if the text exists but with wrong format
        if re.search(r"Breaking Changes", pr_body, re.IGNORECASE):
            # Find what heading level was used
            heading_match = re.search(
                r"(#{1,6})\s*Breaking Changes", pr_body, re.IGNORECASE
            )
            if heading_match:
                num_hashes = len(heading_match.group(1))
                error_msg += f"\n  Found 'Breaking Changes' with {num_hashes} hash mark(s) (heading level {num_hashes})"
            error_msg += (
                "\n  Expected format: '### Breaking Changes' (or #, ##, or ####)"
            )
            error_msg += "\n  Make sure there's content after the heading"
        else:
            error_msg += (
                "\n  The text 'Breaking Changes' was not found anywhere in the PR body"
            )
            error_msg += "\n  Please ensure you've included the Breaking Changes section from the PR template"

        result["error"] = error_msg
        return result

    breaking_section = breaking_section_match.group(1)

    # Check if "No breaking changes" is checked (flexible whitespace and case)
    no_breaking_pattern = r"-\s*\[[xX]\]\s*\*\*No breaking changes\*\*"
    result["no_breaking_checked"] = bool(
        re.search(no_breaking_pattern, breaking_section, re.IGNORECASE)
    )

    # Find all checked components (flexible whitespace and case for checkboxes)
    # First check for 'lib' specifically
    components = []
    if re.search(r"-\s*\[[xX]\]\s*`lib`", breaking_section, re.IGNORECASE):
        components.append("lib")

    # Find all checked scenario components (using generic pattern to catch new scenarios)
    # This matches any line like: - [x] `some_scenario_name` scenario
    # or just: - [x] `some_scenario_name`
    checked_scenarios = re.findall(
        r"-\s*\[[xX]\]\s*`([a-zA-Z0-9_]+)`(?:\s+scenario)?",
        breaking_section,
        re.IGNORECASE,
    )

    # Filter out 'lib' if it was already added, and add the rest
    for scenario in checked_scenarios:
        if scenario != "lib" and scenario not in components:
            components.append(scenario)

    # Determine if there are breaking changes based on components being checked
    has_breaking_changes = len(components) > 0

    # Validation logic with enhanced diagnostics
    if result["no_breaking_checked"] and has_breaking_changes:
        result["error"] = (
            "Both 'No breaking changes' and specific components are checked. "
            "Please check only one option.\n"
            f"  Components checked: {', '.join(components)}"
        )
        return result

    if not result["no_breaking_checked"] and not has_breaking_changes:
        error_msg = (
            "Breaking changes section not properly filled. "
            "Please check either 'No breaking changes' OR at least one component checkbox."
        )

        # Check if unchecked checkboxes exist (diagnostic help)
        unchecked_no_breaking = re.search(
            r"-\s*\[\s*\]\s*\*\*No breaking changes\*\*",
            breaking_section,
            re.IGNORECASE,
        )
        unchecked_components = re.findall(r"-\s*\[\s*\]\s*`([^`]+)`", breaking_section)

        if unchecked_no_breaking or unchecked_components:
            error_msg += "\n  Found unchecked checkboxes:"
            if unchecked_no_breaking:
                error_msg += "\n    - [ ] **No breaking changes**"
            for comp in unchecked_components[:5]:  # Show first 5
                error_msg += f"\n    - [ ] `{comp}`"
            error_msg += "\n  Please check at least one checkbox (use [x] or [X])"
        else:
            error_msg += "\n  No checkboxes found in the Breaking Changes section"
            error_msg += "\n  Expected format: '- [x] **No breaking changes**' or '- [x] `component_name`'"

        result["error"] = error_msg
        return result

    # All validations passed
    result["valid"] = True
    result["has_breaking_changes"] = has_breaking_changes
    result["components"] = components

    if result["has_breaking_changes"]:
        result["version_bump_type"] = "major"

    return result


def validate(pr_body: str) -> None:
    """Validate PR breaking changes section and exit with appropriate code.

    Args:
        pr_body: The full PR description body

    Exits:
        0 if valid, 1 if invalid
    """
    result = parse_breaking_changes(pr_body)

    if result["valid"]:
        print("✓ Breaking changes section is properly filled")
        if result["has_breaking_changes"]:
            print(f"  Breaking changes in: {', '.join(result['components'])}")
            print("  Will trigger major version bump")
        else:
            print("  No breaking changes")
            print("  Will trigger patch version bump")
        sys.exit(0)
    else:
        print(f"✗ Error: {result['error']}")
        sys.exit(1)


def main(pr_body: str, validate_only: bool = False) -> None:
    """Main entry point.

    Args:
        pr_body: The full PR description body
        validate_only: If True, validate and exit. If False, output JSON.
    """
    if validate_only:
        validate(pr_body)
    else:
        result = parse_breaking_changes(pr_body)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    fire.Fire(main)
