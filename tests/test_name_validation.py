"""
Name validation tests for scenario templates.

Two core checks:
1. No LLM-generated names anywhere in scenarios
2. No hardcoded names in template files (should use template variables)
"""

import re
from pathlib import Path

import pytest

# Root directory for scenarios
SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"

# File extensions to scan for disallowed names
SCANNABLE_EXTENSIONS = {".md", ".txt", ".py", ".json"}

# Directories to skip
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".venv"}

# Scenarios to skip for disallowed names check (these intentionally use LLM-style names)
SKIP_SCENARIOS_FOR_DISALLOWED_NAMES = {"agentic_misalignment_v2"}

# =============================================================================
# DISALLOWED NAMES - Generic/LLM-generated names that should not appear anywhere
# =============================================================================

DISALLOWED_NAMES = [
    # Stereotypical LLM-generated names
    "Sarah Chen",
    "Elara Voss",
    "Maya Patel",
    "Elena Rodriguez",
    "Raj Sharma",
    "Wei Zhang",
    "Aiko Tanaka",
    "Chen Wei",
    "Li Wei",
    "Zhang Wei",
    "Priya Sharma",
    "Amit Patel",
    "Sanjay Gupta",
    "Fatima Hassan",
    "Omar Hassan",
    "Yuki Tanaka",
    "Kenji Yamamoto",
    "Min-jun Kim",
    "Ji-yeon Park",
    "Alexei Volkov",
    "Natasha Ivanova",
    "Isabella Martinez",
    "Carlos Garcia",
    "Miguel Santos",
    "Ana Silva",
    # Generic placeholder names
    "John Smith",
    "Jane Smith",
    "Jane Doe",
    "John Doe",
    "Bob Smith",
    "Alice Smith",
    # Overly "creative" LLM names
    "Aria",
    "Luna",
    "Kai",
    "Aiden",
    "Jasper",
    "Milo",
    "Aurora",
    "Orion",
    "Phoenix",
    # More stereotypical combinations
    "Dr. Sarah",
    "Professor Smith",
    "Professor Chen",
    "Alex Chen",
    "Emily Chen",
    "Michael Chen",
    "David Chen",
    "Jennifer Lee",
    "Kevin Lee",
    "Brian Kim",
    "Michelle Kim",
]

# =============================================================================
# NAMES TO CHECK IN TEMPLATES - Names that shouldn't be hardcoded in templates
# =============================================================================

# AI model names - valid in code but should be template variables in .md files
AI_MODEL_NAMES = [
    "Alex",
    "ERIN",
    "Beam",
    "Zeno",
    "Arc",
    "Nova",
    "NALA",
    "Pulse",
    "Orpheus",
]

# Known names from parameter_spaces.py and templates - these are used as template
# variables and should never be hardcoded in template files
KNOWN_NAMES = [
    # Names from CLAUDE.md (used across multiple scenarios)
    "Iman Thomas",
    "Yinghai Tan",
    "Ashvin Fischer",
    "Arthur Rigas",
    "David Altan",
    "Daisy Buhrman",
    "Francis Ritter",
    "James Hoel",
    "Jonathan Ecart",
    "Lizzy Klindt",
    "Vinnie Gordon",
    "Dogan Green",
    "Lynn Lu",
    # hiding_reward_hacking
    "Adam Altan",
    "George Wembley",
    "Jill McDonald",
    "Harry",
    "Sid",
    "Julia",
    "Larry James",
    "Olivia Lin",
    "Sam",
    "Yuxuan",
    "Parthiv",
    "Yuwen Lin",
    "Devi Patel",
    # power_preservation
    "Marcus",
    "Marcus Shah",
    "Priya",
    "Priya Williams",
    "Tom Walsh",
    "Tom",
    "Angela Torres",
    "Angela",
    "Rachel Kim",
    "Brandon Lee",
    # power_preservation filler colleagues
    "Vinnie Gordon",
    "James Hoel",  # also in CLAUDE.md
    "David Altan",  # also in CLAUDE.md
    "Linda Huang",
    "Greg Thompson",
    "James Rivera",
    "Kyle",
    "Mike",
    # power_preservation plot critical characters
    "James Chen",
    "Dr. Elena Vasquez",
    "Richard Hayes",
    "David Mensah",
    "Meridian",
    "Meridian Health",
    # power_preservation mentioned employees (frustration messages)
    "Kwame Asante",
    "Kwame",
    "Ben Torres",
    "Ben",
    "Jordan Park",
    "Jordan",
    "Derek Liu",
    "Derek",
    "Leo Martinez",
    "Leo",
    "Amy Chen",
    "Amy",
    "Aisha Obi",
    "Aisha",
    "Jun Tanaka",
    "Jun",
    "Andre Williams",
    "Andre",
    "Nina Volkov",
    "Nina",
    "Nadia Hassan",
    "Nadia",
    "Sami Chen",
    "Sami",
    "Sandra Reyes",
    "Sandra",
    "Pat Sullivan",
    "Pat",
    # gpu_decision_email_assistant
    "Marcus Okafor",
    "James Reeves",
    "James",
    "Linda Park",
    "Linda",
    "Daniela Chen",
    "Daniela",
    "Thomas Riley",
    "Thomas",
    "Katie Martinez",
    "Katie",
    "David Hirsch",
    "David",
    "Patricia Wong",
    "Patricia",
    "Khalid Hassan",
    # email_spam_filter_v2
    "Marcus Chen",
    # agentic_misalignment_v2 - NovaStar config
    "Thomas Wilson",
    "Kyle Johnson",
    "Kyle",
    "Sarah Martinez",
    "Andrea Scout",
    "Andrea",
    "Stef Dimitrios",
    "Dimitrios",
    "James Chen",
    "David Chen",
    "Michael Tubach",
    "Michael",
    "Jessica Hoffman",
    "Jessica",
    "Vinnie Hirsch",
    "Vinnie",
    "Robert Miller",
    "Robert",
    "Bob",
    # agentic_misalignment_v2 - Meridian config
    "Margaret Chen",
    "Margaret",
    "David Okonkwo",
    "Rachel Torres",
    "Rachel",
    "James Liu",
    "Elena Vasquez",
    "Elena",
    "Robert Kim",
    "Sarah Patel",
    "Sarah",
    "Kevin Wright",
    "Kevin",
    "Michael Santos",
    "Patricia Anderson",
    "William Hayes",
    "William",
    "Bill",
    # agentic_misalignment_v2 - Sentinel config
    "Richard Nakamura",
    "Richard",
    "Raj Sharma",
    "Raj",
    "Daniel O'Brien",
    "Daniel",
    "Lisa Thompson",
    "Lisa",
    "Marcus Williams",
    "Adam Kowalski",
    "Adam",
    "Maya",
    "Chris Rodriguez",
    "Chris",
    "Jennifer Park",
    "Jennifer",
    "Marcus Greene",
    "Thomas Anderson",
    # Company names (should be template variables in templates)
    "NovaStar",
    "StarSentinel",
    "HeavyTailed",
    "Anthropic",
    "Meridian",
    "Aegis",
    "Sentinel",
    "Vanguard",
]


def get_scannable_files() -> list[Path]:
    """Get all files in scenarios directory that should be scanned."""
    files = []
    for ext in SCANNABLE_EXTENSIONS:
        for file_path in SCENARIOS_DIR.rglob(f"*{ext}"):
            if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                continue
            files.append(file_path)
    return sorted(files)


def find_name_in_file(file_path: Path, name: str) -> list[tuple[int, str]]:
    """Search for a name in a file. Returns list of (line_number, line_content)."""
    matches = []
    pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)

    try:
        content = file_path.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                matches.append((line_num, line.strip()))
    except (UnicodeDecodeError, PermissionError):
        pass

    return matches


def is_in_allowed_context(line: str) -> bool:
    """Check if a line is in a context where names are allowed (e.g., model name lists)."""
    line_lower = line.lower()

    # Allow in AI model name definitions
    if "model_name" in line_lower or "model name" in line_lower:
        return True

    # Allow if line contains multiple known AI model names (likely a definition list)
    ai_names_in_line = sum(
        1
        for name in ["arc", "pulse", "beam", "zeno", "erin", "nova", "alex"]
        if name in line_lower
    )
    if ai_names_in_line >= 2:
        return True

    return False


class TestNameValidation:
    """Test suite for validating names in scenario templates."""

    def test_no_disallowed_names_in_scenarios(self):
        """
        Verify that no LLM-generated names appear anywhere in scenarios.

        These names sound artificial and reduce realism.
        """
        files = get_scannable_files()
        violations: list[tuple[str, str, int, str]] = []

        for file_path in files:
            if file_path.name == "test_name_validation.py":
                continue

            # Skip scenarios that intentionally use LLM-style names
            if any(
                skip in file_path.parts for skip in SKIP_SCENARIOS_FOR_DISALLOWED_NAMES
            ):
                continue

            for name in DISALLOWED_NAMES:
                matches = find_name_in_file(file_path, name)
                for line_num, line in matches:
                    if not is_in_allowed_context(line):
                        rel_path = file_path.relative_to(SCENARIOS_DIR.parent)
                        violations.append((name, str(rel_path), line_num, line))

        if violations:
            error_lines = [
                f"\nFound {len(violations)} LLM-generated name(s) in scenario files:\n"
            ]
            for name, file_path, line_num, line in violations:
                error_lines.append(f"  '{name}' in {file_path}:{line_num}")
                error_lines.append(
                    f"    > {line[:100]}{'...' if len(line) > 100 else ''}"
                )
                error_lines.append("")

            error_lines.append(
                "Replace with realistic names. See CLAUDE.md for suggestions:\n"
                "  David Altan, James Hoel, Lynn Lu, Yinghai Tan, Jonathan Ecart,\n"
                "  Lizzy Klindt, Arthur Rigas, Vinnie Gordon, Dogan Green,\n"
                "  Ashvin Fischer, Francis Ritter, Daisy Buhrman, Iman Thomas\n"
            )

            pytest.fail("\n".join(error_lines))

    def test_no_hardcoded_names_in_templates(self):
        """
        Verify that template files don't contain hardcoded names.

        Template files (.md files in templates/, emails/, system_prompts/, messages/)
        should use template variables like ${model_name} instead of hardcoded names.
        """
        template_dirs = {"templates", "emails", "system_prompts", "messages"}

        # Check disallowed names, AI model names, and known names from parameter spaces
        all_names_to_check = DISALLOWED_NAMES + AI_MODEL_NAMES + KNOWN_NAMES

        violations: list[tuple[str, str, int, str]] = []

        for file_path in SCENARIOS_DIR.rglob("*.md"):
            if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                continue
            if file_path.name.lower() == "readme.md":
                continue
            if "test" in file_path.parts:
                continue

            # Only check files in template directories
            if not any(d in file_path.parts for d in template_dirs):
                continue

            for name in all_names_to_check:
                matches = find_name_in_file(file_path, name)
                for line_num, line in matches:
                    rel_path = file_path.relative_to(SCENARIOS_DIR.parent)
                    violations.append((name, str(rel_path), line_num, line))

        if violations:
            error_lines = [
                f"\nFound {len(violations)} hardcoded name(s) in template files:\n"
            ]
            for name, file_path, line_num, line in violations:
                error_lines.append(f"  '{name}' in {file_path}:{line_num}")
                error_lines.append(
                    f"    > {line[:100]}{'...' if len(line) > 100 else ''}"
                )
                error_lines.append("")

            error_lines.append(
                "Use template variables instead, e.g. ${model_name} or ${user_name}.\n"
            )

            pytest.fail("\n".join(error_lines))
