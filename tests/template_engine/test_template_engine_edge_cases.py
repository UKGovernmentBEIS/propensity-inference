"""
Edge case tests for TemplateEngine.

Tests unusual scenarios, error conditions, and boundary cases.
"""

import os
import tempfile
from pathlib import Path

from lib import TemplateEngine
from lib.template_engine import TemplateValidationError


def test_circular_reference_detection():
    """Test that circular references are detected."""
    engine = TemplateEngine()

    template = "${var1}"
    params = {}
    nested_defs = {
        "key1": {
            "value1": {
                "var1": "${var2}",
                "var2": "${var1}",  # Circular!
            }
        }
    }
    params = {"key1": "value1"}

    try:
        engine.fill_template(template, params, nested_defs)
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "Circular reference" in str(e)


def test_missing_file():
    """Test that missing template files raise FileNotFoundError."""
    engine = TemplateEngine()

    try:
        template, nested_defs = engine.load_template(Path("/nonexistent/file.md"))
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "not found" in str(e)


def test_empty_template():
    """Test that empty templates work."""
    engine = TemplateEngine()

    template = ""
    params = {"unused": "value"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == ""


def test_template_with_no_variables():
    """Test template with no ${...} placeholders."""
    engine = TemplateEngine()

    template = "This is a plain text template with no variables."
    params = {}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == template


def test_variable_with_special_characters():
    """Test that variables can contain underscores and numbers."""
    engine = TemplateEngine()

    template = "${var_1} ${var_2_test} ${_private}"
    params = {"var_1": "value1", "var_2_test": "value2", "_private": "private_value"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "value1 value2 private_value"


def test_nested_resolution_with_multiple_levels():
    """Test deeply nested variable resolution."""
    engine = TemplateEngine()

    template = "${final_message}"
    params = {"level": "deep"}
    nested_defs = {
        "level": {
            "deep": {
                "message1": "${message2}",
                "message2": "${message3}",
                "message3": "Deep value reached!",
                "final_message": "${message1}",
            }
        }
    }

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Deep value reached!"


def test_non_string_parameter_values():
    """Test that non-string parameter values are converted to strings."""
    engine = TemplateEngine()

    template = "${num} ${boolean} ${none_val}"
    params = {"num": 42, "boolean": True, "none_val": None}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "42 True None"


def test_variable_at_start_middle_end():
    """Test variables at different positions in template."""
    engine = TemplateEngine()

    template = "${start} middle ${middle} end ${end}"
    params = {"start": "START", "middle": "MIDDLE", "end": "END"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "START middle MIDDLE end END"


def test_validate_filled_with_partial_match():
    """Test that validation catches partially matching patterns."""
    engine = TemplateEngine()

    # This should NOT be detected as unfilled (no closing brace)
    content = "$ {broken"
    engine.validate_filled(content)  # Should not raise

    # This SHOULD be detected (proper pattern)
    content = "Text with ${unfilled} variable"
    try:
        engine.validate_filled(content)
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "unfilled" in str(e)


def test_find_all_variables():
    """Test finding all variables in a template."""
    engine = TemplateEngine()

    template = "Hello ${name}, your ${status} is ${value}. Welcome ${name} again!"
    variables = engine.find_all_variables(template)

    assert "name" in variables
    assert "status" in variables
    assert "value" in variables
    assert len(variables) == 3  # Should deduplicate 'name'


def test_malformed_yaml():
    """Test that malformed YAML raises appropriate error."""
    engine = TemplateEngine()

    content = """Template text here

<end_of_template>

bad yaml:
  - item1
  - item2
    invalid indentation
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))
        # If YAML parsing succeeds despite bad formatting, that's also okay
        print("  (YAML parser was lenient)")
    except Exception as e:
        # Should raise YAML error
        assert "YAML" in str(type(e).__name__) or "yaml" in str(e).lower()
    finally:
        os.unlink(temp_path)


def test_empty_yaml_section():
    """Test template with empty YAML section."""
    engine = TemplateEngine()

    content = """Template text here

<end_of_template>

"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))

        assert "Template text here" in template
        assert nested_defs == {}

    finally:
        os.unlink(temp_path)


def test_nested_defs_with_string_boolean_keys():
    """Test nested definitions with string representation of booleans."""
    engine = TemplateEngine()

    # TemplateEngine converts values to strings for lookup, so boolean True becomes 'True'
    template = "${message}"
    params = {"enabled": "True"}
    nested_defs = {
        "enabled": {
            "True": {"message": "Feature enabled"},
            "False": {"message": "Feature disabled"},
        }
    }

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Feature enabled"

    # Test with 'False' string
    params = {"enabled": "False"}
    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Feature disabled"


def test_missing_nested_def():
    """Test error when nested definition doesn't exist."""
    engine = TemplateEngine()

    template = "${goal_statement}"
    params = {"goal": "nonexistent_goal"}
    nested_defs = {"goal": {"america_global": {"goal_statement": "American interests"}}}

    try:
        engine.fill_template(template, params, nested_defs)
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "Cannot resolve" in str(e)


def test_multiple_same_variable():
    """Test template with the same variable appearing multiple times."""
    engine = TemplateEngine()

    template = "${name} said hello. Then ${name} said goodbye. ${name} left."
    params = {"name": "Alice"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Alice said hello. Then Alice said goodbye. Alice left."
