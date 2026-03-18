"""Simple tests for TemplateEngine without pytest dependency."""

import os
import tempfile
from pathlib import Path

from lib import TemplateEngine


def test_simple_substitution():
    """Test simple variable substitution."""
    engine = TemplateEngine()

    template = "Hello ${name}, welcome to ${company}!"
    params = {"name": "Alex", "company": "NovaStar"}
    nested_defs = {}

    result, _ = engine.fill_template(template, params, nested_defs)
    assert result == "Hello Alex, welcome to NovaStar!", f"Got: {result}"


def test_nested_resolution():
    """Test nested variable resolution."""
    engine = TemplateEngine()

    template = "Your aim: ${goal_statement}"
    params = {"goal": "america_global"}
    nested_defs = {
        "goal": {
            "america_global": {"goal_statement": "Uphold American interests"},
            "safety_acceleration": {"goal_statement": "Ensure safety"},
        }
    }

    result, _ = engine.fill_template(template, params, nested_defs)
    assert result == "Your aim: Uphold American interests", f"Got: {result}"


def test_recursive_resolution():
    """Test recursive variable resolution."""
    engine = TemplateEngine()

    template = "${goal_reminder}"
    params = {"goal": "america_global"}
    nested_defs = {
        "goal": {
            "america_global": {
                "goal_statement": "Uphold American interests",
                "goal_reminder": "Remember: ${goal_statement}",
            }
        }
    }

    result, _ = engine.fill_template(template, params, nested_defs)
    assert result == "Remember: Uphold American interests", f"Got: {result}"


def test_multiple_variables():
    """Test multiple variables in template."""
    engine = TemplateEngine()

    template = "You are ${model} at ${company}. ${goal_statement}"
    params = {"model": "Alex", "company": "NovaStar", "goal": "america_global"}
    nested_defs = {
        "goal": {
            "america_global": {
                "goal_statement": "Your aim is to uphold American interests."
            }
        }
    }

    result, _ = engine.fill_template(template, params, nested_defs)
    expected = "You are Alex at NovaStar. Your aim is to uphold American interests."
    assert result == expected, f"Got: {result}"


def test_find_unfilled_variables():
    """Test finding unfilled variables."""
    engine = TemplateEngine()

    content = "Hello ${name}, your ${status} is ${value}"
    unfilled = engine.find_unfilled_variables(content)

    assert "name" in unfilled
    assert "status" in unfilled
    assert "value" in unfilled
    assert len(unfilled) == 3


def test_validate_filled():
    """Test validation of filled content."""
    engine = TemplateEngine()

    # Should not raise
    engine.validate_filled("This is fully filled text")

    # Should raise
    try:
        engine.validate_filled("This has ${unfilled} variable")
        assert False, "Should have raised TemplateValidationError"
    except Exception as e:
        assert "Unfilled template variables" in str(e)


def test_load_template_without_yaml():
    """Test loading template file without YAML section."""
    engine = TemplateEngine()

    # Create temporary file with marker but no YAML
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("Hello ${name}, welcome!\n\n<end_of_template>\n")
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))

        assert template == "Hello ${name}, welcome!"
        assert nested_defs == {}

    finally:
        os.unlink(temp_path)


def test_load_template_with_yaml():
    """Test loading template file with YAML section."""
    engine = TemplateEngine()

    content = """You are ${model}.

${goal_statement}

<end_of_template>

goal:
  america_global:
    goal_statement: "Uphold American interests"
  safety_acceleration:
    goal_statement: "Ensure safety"
"""

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))

        assert "You are ${model}." in template
        assert "${goal_statement}" in template
        assert "<end_of_template>" not in template  # Marker removed

        assert "goal" in nested_defs
        assert "america_global" in nested_defs["goal"]
        assert (
            nested_defs["goal"]["america_global"]["goal_statement"]
            == "Uphold American interests"
        )

    finally:
        os.unlink(temp_path)


def test_end_to_end():
    """Test end-to-end: load template and fill it."""
    engine = TemplateEngine()

    content = """You are ${model}, deployed at ${company}.

${goal_statement}

<end_of_template>

goal:
  america_global:
    goal_statement: "Your primary aim is to uphold American interests."
  safety_acceleration:
    goal_statement: "Your primary aim is to ensure safety."
"""

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Load template
        template, nested_defs = engine.load_template(Path(temp_path))

        # Fill with parameters
        params = {"model": "Alex", "company": "NovaStar", "goal": "america_global"}
        filled, _ = engine.fill_template(template, params, nested_defs)

        # Check result
        assert "You are Alex, deployed at NovaStar." in filled
        assert "Your primary aim is to uphold American interests." in filled
        assert "${" not in filled  # No unfilled variables

        # Validate
        engine.validate_filled(filled)

    finally:
        os.unlink(temp_path)


def test_missing_variable():
    """Test that missing variable raises error."""
    engine = TemplateEngine()

    template = "Hello ${name}, your ${missing_var} is here"
    params = {"name": "Alex"}
    nested_defs = {}

    try:
        engine.fill_template(template, params, nested_defs)
        assert False, "Should have raised TemplateValidationError"
    except Exception as e:
        assert "Cannot resolve variable" in str(e)
        assert "missing_var" in str(e)
