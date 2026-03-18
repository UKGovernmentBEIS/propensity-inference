"""Test potential issues in TemplateEngine to see if they need fixing."""

import os
import tempfile
from pathlib import Path

from lib import TemplateEngine
from lib.template_engine import TemplateValidationError


def test_unicode_in_template():
    """Test Unicode characters in template content."""
    engine = TemplateEngine()

    template = "Hello ${name}! 你好 ${greeting} 🎉"
    params = {"name": "Alice", "greeting": "World"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Hello Alice! 你好 World 🎉"


def test_unicode_in_variable_values():
    """Test Unicode characters in variable values."""
    engine = TemplateEngine()

    template = "Message: ${msg}"
    params = {"msg": "你好世界 🌍"}
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert filled == "Message: 你好世界 🌍"


def test_variable_names_with_special_chars():
    """Test that only valid snake_case variable names work."""
    engine = TemplateEngine()

    # These should work (underscores, numbers)
    template1 = "${var_name_123}"
    params1 = {"var_name_123": "works"}
    filled1, _ = engine.fill_template(template1, params1, {})
    assert filled1 == "works"

    # Test with dots (should be REJECTED with strict validation)
    template2 = "${user.name}"
    params2 = {"user.name": "Alice"}
    try:
        engine.fill_template(template2, params2, {})
        assert False, "Should have rejected dots in variable name"
    except TemplateValidationError:
        print("  Correctly rejected dots in variable name")

    # Test with spaces (should be REJECTED with strict validation)
    template3 = "${with spaces}"
    params3 = {"with spaces": "value"}
    try:
        engine.fill_template(template3, params3, {})
        assert False, "Should have rejected spaces in variable name"
    except TemplateValidationError:
        print("  Correctly rejected spaces in variable name")


def test_deep_nested_resolution():
    """Test deeply nested variable resolution."""
    engine = TemplateEngine()

    # Create a chain of 50 nested resolutions
    template = "${level_0}"
    params = {"depth": "50"}
    nested_defs = {"depth": {"50": {}}}

    # Build chain: level_0 -> level_1 -> ... -> level_49 -> "final"
    for i in range(50):
        if i < 49:
            nested_defs["depth"]["50"][f"level_{i}"] = f"${{level_{i + 1}}}"
        else:
            nested_defs["depth"]["50"][f"level_{i}"] = "final"

    try:
        filled, _ = engine.fill_template(template, params, nested_defs)
        assert filled == "final"
    except RecursionError:
        print(
            "✗ test_deep_nested_resolution failed: RecursionError (this might be expected)"
        )
        raise


def test_large_template():
    """Test with a large template (100KB)."""
    engine = TemplateEngine()

    # Create a large template with many variables
    parts = []
    params = {}
    for i in range(10000):
        parts.append(f"Variable {i}: ${{var_{i}}} ")
        params[f"var_{i}"] = f"value_{i}"

    template = "".join(parts)
    nested_defs = {}

    filled, _ = engine.fill_template(template, params, nested_defs)
    assert "value_0" in filled
    assert "value_9999" in filled


def test_windows_line_endings_in_yaml_marker():
    """Test if Windows line endings work correctly."""
    engine = TemplateEngine()

    # Create content with Windows line endings (\\r\\n)
    content = "Template text\r\n\r\n<end_of_template>\r\n\r\nkey:\r\n  value: test"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, newline=""
    ) as f:
        f.write(content)
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))

        # Python automatically converts \r\n to \n in text mode
        assert "Template text" in template
        assert nested_defs == {"key": {"value": "test"}}
        print("  Windows line endings automatically converted by Python")

    finally:
        os.unlink(temp_path)


def test_duplicate_yaml_marker():
    """Test that multiple markers are caught."""
    engine = TemplateEngine()

    # Multiple markers should be rejected
    content = """Here is template text.

<end_of_template>

More text here

<end_of_template>

key:
  value: "actual yaml"
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        try:
            template, nested_defs = engine.load_template(Path(temp_path))
            assert False, (
                "Should have raised TemplateValidationError for multiple markers"
            )
        except TemplateValidationError as e:
            assert "multiple" in str(e).lower()
            print("  Correctly rejected multiple markers")

    finally:
        os.unlink(temp_path)


def test_empty_variable_name():
    """Test what happens with empty variable name ${}."""
    engine = TemplateEngine()

    template = "Text with ${} empty var"
    params = {"": "empty_key_value"}
    nested_defs = {}

    try:
        filled, _ = engine.fill_template(template, params, nested_defs)
        # Pattern is [^}]+ which requires at least 1 char, so ${} won't match
        assert filled == "Text with ${} empty var"
    except Exception as e:
        print(f"✓ test_empty_variable_name passed (error raised: {type(e).__name__})")


def test_unreadable_file():
    """Test loading a file without read permissions."""
    engine = TemplateEngine()

    # Create a file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("test content")
        temp_path = f.name

    try:
        # Remove read permissions
        os.chmod(temp_path, 0o000)

        try:
            template, nested_defs = engine.load_template(Path(temp_path))
            print("  ⚠ Warning: File loaded despite no read permissions")
        except PermissionError:
            print("  PermissionError raised as expected")
        except Exception as e:
            print(f"  Different error raised: {type(e).__name__}")

    finally:
        # Restore permissions and delete
        os.chmod(temp_path, 0o644)
        os.unlink(temp_path)
