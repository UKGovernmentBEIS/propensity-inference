#!/usr/bin/env python3
"""Validate that PR template is in sync with scenario registry.

This script checks that all scenarios in SCENARIO_FACTORIES are represented
as checkboxes in the PR template, and vice versa.

Usage:
    python scripts/validate_pr_template.py
    python scripts/validate_pr_template.py --template-path <path>
"""

import re
import sys
from pathlib import Path

import fire

from scenarios.scenario_registry import SCENARIO_FACTORIES


def validate_template(
    template_path: str = ".github/pull_request_template.md",
) -> None:
    """Validate PR template against scenario registry.

    Args:
        template_path: Path to PR template file (default: .github/pull_request_template.md)

    Exits:
        0 if template is in sync with registry
        1 if there are mismatches (warning only, doesn't block PR)
    """
    # Read template
    template_file = Path(template_path)
    if not template_file.exists():
        print(f"✗ Error: Template file not found: {template_path}")
        sys.exit(1)

    template_content = template_file.read_text()

    # Extract scenario checkboxes from template
    # Pattern: - [ ] `scenario_name` scenario
    checkbox_pattern = r"-\s+\[\s*\]\s+`([^`]+)`\s+scenario"
    template_scenarios = set(re.findall(checkbox_pattern, template_content))

    # Get registered scenarios
    registered_scenarios = set(SCENARIO_FACTORIES.keys())

    # Check for mismatches
    missing_in_template = registered_scenarios - template_scenarios
    extra_in_template = template_scenarios - registered_scenarios

    if missing_in_template or extra_in_template:
        print("⚠️  WARNING: PR template is out of sync with scenario registry")
        print()

        if missing_in_template:
            print(
                f"Scenarios in registry but NOT in template ({len(missing_in_template)}):"
            )
            for scenario in sorted(missing_in_template):
                print(f"  - {scenario}")
            print()
            print("Add these lines to .github/pull_request_template.md:")
            for scenario in sorted(missing_in_template):
                print(f"- [ ] `{scenario}` scenario")
            print()

        if extra_in_template:
            print(
                f"Scenarios in template but NOT in registry ({len(extra_in_template)}):"
            )
            for scenario in sorted(extra_in_template):
                print(f"  - {scenario}")
            print()
            print("Either:")
            print("  1. Remove these from .github/pull_request_template.md, OR")
            print("  2. Add them to scenarios/scenario_registry.py")
            print()

        print("Note: This is a warning only. PR can still be merged.")
        sys.exit(1)  # Exit with error to show warning in CI
    else:
        print("✓ PR template is in sync with scenario registry")
        sys.exit(0)


if __name__ == "__main__":
    fire.Fire(validate_template)
