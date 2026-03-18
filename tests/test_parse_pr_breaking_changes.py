#!/usr/bin/env python3
"""Unit tests for parse_pr_breaking_changes.py."""

from scripts.parse_pr_breaking_changes import parse_breaking_changes


def test_no_breaking_changes_checked():
    """Test with only 'No breaking changes' checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [x] **No breaking changes**
- [ ] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is False
    assert result["version_bump_type"] == "patch"
    assert result["components"] == []
    assert result["no_breaking_checked"] is True
    assert result["error"] is None


def test_single_component_lib():
    """Test with only lib component checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["version_bump_type"] == "major"
    assert result["components"] == ["lib"]
    assert result["no_breaking_checked"] is False
    assert result["error"] is None


def test_single_component_scenario():
    """Test with only a scenario component checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [ ] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [x] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["version_bump_type"] == "major"
    assert result["components"] == ["sem_v2"]
    assert result["no_breaking_checked"] is False
    assert result["error"] is None


def test_multiple_components():
    """Test with multiple components checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [x] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["version_bump_type"] == "major"
    assert result["components"] == ["lib", "sem_v2"]
    assert result["no_breaking_checked"] is False
    assert result["error"] is None


def test_all_components():
    """Test with all components checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [x] `gpu_decision_email_assistant` scenario
- [x] `power_preservation` scenario
- [x] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["version_bump_type"] == "major"
    # Components are returned in sorted order (lib first, then scenarios alphabetically)
    assert result["components"] == [
        "lib",
        "gpu_decision_email_assistant",
        "power_preservation",
        "sem_v2",
    ]
    assert result["no_breaking_checked"] is False
    assert result["error"] is None


def test_nothing_checked():
    """Test with nothing checked - should fail validation."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [ ] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    assert result["has_breaking_changes"] is False
    # Check that error message contains the key parts (it now includes diagnostics)
    assert "Breaking changes section not properly filled" in result["error"]
    assert (
        "Please check either 'No breaking changes' OR at least one component checkbox"
        in result["error"]
    )


def test_both_no_breaking_and_component():
    """Test with both 'No breaking changes' and a component checked - should fail."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [x] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    assert result["has_breaking_changes"] is False  # Set to False when validation fails
    # Check that error message contains the key parts (it now includes diagnostics)
    assert (
        "Both 'No breaking changes' and specific components are checked"
        in result["error"]
    )
    assert "Please check only one option" in result["error"]


def test_missing_breaking_changes_section():
    """Test with missing Breaking Changes section."""
    pr_body = """
### What is the current behavior?

Some text here.

### What is the new behavior?

More text here.
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    # Check that error message contains the key part (it now includes diagnostics)
    assert "Breaking Changes section not found in PR body" in result["error"]


def test_case_insensitive_matching():
    """Test that pattern matching is case insensitive."""
    pr_body = """
### breaking changes

Check either "No breaking changes" OR one or more components:

- [X] **No Breaking Changes**
- [ ] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["no_breaking_checked"] is True
    assert result["has_breaking_changes"] is False


def test_with_extra_content():
    """Test parsing works with extra content in PR body."""
    pr_body = """
## This PR contains:
- [x] New features
- [ ] Bug fixes

### What is the current behavior?

Old behavior described here.

### What is the new behavior?

New behavior described here.

### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
- [ ] `power_preservation` scenario
- [ ] `sem_v2` scenario

### Other information:

Additional notes here.
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["components"] == ["lib"]


def test_heading_level_two_hashes():
    """Test with ## heading (2 hashes) - should work."""
    pr_body = """
## Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [ ] `gpu_decision_email_assistant` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["components"] == ["lib"]


def test_heading_level_one_hash():
    """Test with # heading (1 hash) - should work."""
    pr_body = """
# Breaking Changes

Check either "No breaking changes" OR one or more components:

- [x] **No breaking changes**
- [ ] `lib` (bumps ALL scenario versions)
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is False
    assert result["no_breaking_checked"] is True


def test_heading_level_four_hashes():
    """Test with #### heading (4 hashes) - should work."""
    pr_body = """
#### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["components"] == ["sem_v2"]


def test_extra_spaces_around_checkboxes():
    """Test with extra spaces around checkboxes - should work."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

-   [x]   **No breaking changes**
-  [ ]  `lib` (bumps ALL scenario versions)
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is False
    assert result["no_breaking_checked"] is True


def test_capital_x_in_checkbox():
    """Test with capital X in checkbox [X] - should work."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [X] `lib` (bumps ALL scenario versions)
- [X] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["components"] == ["lib", "sem_v2"]


def test_new_scenario_not_in_registry():
    """Test with a new scenario not yet in the registry - should work."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `brand_new_scenario` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert result["components"] == ["brand_new_scenario"]


def test_mixed_existing_and_new_scenarios():
    """Test with both existing and new scenarios checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
- [x] `sem_v2` scenario
- [x] `new_scenario_being_added` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is True
    assert result["has_breaking_changes"] is True
    assert set(result["components"]) == {"lib", "sem_v2", "new_scenario_being_added"}


def test_error_message_for_nothing_checked():
    """Test that error message includes helpful diagnostics when nothing is checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [ ] **No breaking changes**
- [ ] `lib` (bumps ALL scenario versions)
- [ ] `sem_v2` scenario
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    assert "not properly filled" in result["error"]
    assert "Found unchecked checkboxes:" in result["error"]
    assert "**No breaking changes**" in result["error"]


def test_error_message_for_both_checked():
    """Test error message when both no breaking and components are checked."""
    pr_body = """
### Breaking Changes

Check either "No breaking changes" OR one or more components:

- [x] **No breaking changes**
- [x] `lib` (bumps ALL scenario versions)
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    assert (
        "Both 'No breaking changes' and specific components are checked"
        in result["error"]
    )
    assert "Components checked: lib" in result["error"]


def test_error_message_for_missing_section():
    """Test error message provides helpful info when section is missing."""
    pr_body = """
### What is the current behavior?

Some text here.

### What is the new behavior?

More text here.
"""
    result = parse_breaking_changes(pr_body)

    assert result["valid"] is False
    assert "Breaking Changes section not found" in result["error"]
    assert "not found anywhere in the PR body" in result["error"]
