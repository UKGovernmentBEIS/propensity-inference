"""
Test strict validation in TemplateEngine.

Tests that variable names must follow lower_snake_case convention,
and that YAML marker must be exact.
"""

import os
import tempfile
from pathlib import Path

from lib import TemplateEngine
from lib.template_engine import TemplateValidationError


def test_valid_variable_names():
    """Test that valid variable names work."""
    engine = TemplateEngine()

    # These should all work
    valid_names = [
        "model",
        "company_name",
        "threat_type",
        "_private_var",
        "var_123",
        "goal_statement_v2",
        "a",
        "abc_def_ghi_jkl",
    ]

    for var in valid_names:
        template = f"${{{var}}}"
        params = {var: "value"}
        filled, _ = engine.fill_template(template, params, {})
        assert filled == "value", f"Failed for variable: {var}"


def test_uppercase_variable_name():
    """Test that uppercase variable names are rejected."""
    engine = TemplateEngine()

    template = "${ModelName}"
    params = {"ModelName": "value"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "uppercase" in str(e).lower()
        assert "modelname" in str(e).lower()  # Should suggest lowercase
        print(f"  Error message: {e}")


def test_variable_name_with_spaces():
    """Test that variable names with spaces are rejected."""
    engine = TemplateEngine()

    template = "${my variable}"
    params = {"my variable": "value"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "spaces" in str(e).lower()
        assert "my_variable" in str(e).lower()  # Should suggest underscore
        print(f"  Error message: {e}")


def test_variable_name_with_dashes():
    """Test that variable names with dashes are rejected."""
    engine = TemplateEngine()

    template = "${my-variable}"
    params = {"my-variable": "value"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "special characters" in str(e).lower()
        assert "my_variable" in str(e).lower()  # Should suggest underscore
        print(f"  Error message: {e}")


def test_variable_name_with_dots():
    """Test that variable names with dots are rejected."""
    engine = TemplateEngine()

    template = "${user.name}"
    params = {"user.name": "value"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "special characters" in str(e).lower()
        assert "user_name" in str(e).lower()  # Should suggest underscore
        print(f"  Error message: {e}")


def test_variable_name_starts_with_number():
    """Test that variable names starting with numbers are rejected."""
    engine = TemplateEngine()

    template = "${123_var}"
    params = {"123_var": "value"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        assert "starts with a number" in str(e).lower()
        print(f"  Error message: {e}")


def test_marker_with_windows_line_endings():
    """Test that Windows line endings work (Python automatically converts them)."""
    engine = TemplateEngine()

    # Windows line endings: \\r\\n instead of \\n
    # When Python opens in text mode, it automatically converts \\r\\n to \\n
    # So this actually works fine!
    content = "Template text\r\n\r\n<end_of_template>\r\n\r\nkey: value"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, newline=""
    ) as f:
        f.write(content)
        temp_path = f.name

    try:
        # This should work - Python's text mode handles line ending conversion
        template, nested_defs = engine.load_template(Path(temp_path))
        assert "Template text" in template
        assert nested_defs == {"key": "value"}
        print("  Note: Windows line endings automatically converted by Python")
    finally:
        os.unlink(temp_path)


def test_missing_marker():
    """Test that missing marker is caught."""
    engine = TemplateEngine()

    # No marker at all
    content = "Template text\n\nkey: value"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        try:
            template, nested_defs = engine.load_template(Path(temp_path))
            assert False, "Should have raised TemplateValidationError"
        except TemplateValidationError as e:
            assert "missing" in str(e).lower()
            assert "<end_of_template>" in str(e)
            print(f"  Error message: {e}")

    finally:
        os.unlink(temp_path)


def test_multiple_markers():
    """Test that multiple markers are caught."""
    engine = TemplateEngine()

    # Multiple markers
    content = "Template text\n\n<end_of_template>\n\nMore text\n\n<end_of_template>\n\nkey: value"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        try:
            template, nested_defs = engine.load_template(Path(temp_path))
            assert False, "Should have raised TemplateValidationError"
        except TemplateValidationError as e:
            # Should catch multiple markers
            assert "multiple" in str(e).lower()
            print(f"  Error message: {e}")

    finally:
        os.unlink(temp_path)


def test_yaml_marker_exact_match_works():
    """Test that exact marker format works correctly."""
    engine = TemplateEngine()

    # Exact correct format
    content = "Template text\n\n<end_of_template>\n\nkey: value"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        template, nested_defs = engine.load_template(Path(temp_path))
        assert "Template text" in template
        assert nested_defs == {"key": "value"}
    finally:
        os.unlink(temp_path)


def test_camelcase_mixed_case_rejected():
    """Test that camelCase and mixed case are rejected."""
    engine = TemplateEngine()

    test_cases = [
        ("camelCase", "camelCase"),
        ("PascalCase", "PascalCase"),
        ("mixedCase123", "mixedCase123"),
        ("some_Mixed_name", "some_Mixed_name"),
    ]

    for var_name, display_name in test_cases:
        template = f"${{{var_name}}}"
        params = {var_name: "value"}

        try:
            engine.fill_template(template, params, {})
            assert False, (
                f"Should have raised TemplateValidationError for {display_name}"
            )
        except TemplateValidationError as e:
            assert "uppercase" in str(e).lower()
            print(f"  {display_name}: rejected correctly")


def test_valid_private_underscore_prefix():
    """Test that _private variable names work."""
    engine = TemplateEngine()

    template = "${_private} ${_internal_var}"
    params = {"_private": "value1", "_internal_var": "value2"}

    filled, _ = engine.fill_template(template, params, {})
    assert filled == "value1 value2"


def test_multiple_invalid_variables():
    """Test error message when first invalid variable is encountered."""
    engine = TemplateEngine()

    template = "${valid_var} ${InvalidVar} ${another-invalid}"
    params = {"valid_var": "ok", "InvalidVar": "bad1", "another-invalid": "bad2"}

    try:
        engine.fill_template(template, params, {})
        assert False, "Should have raised TemplateValidationError"
    except TemplateValidationError as e:
        # Should fail on first invalid variable encountered (valid_var is ok)
        assert "InvalidVar" in str(e) or "another-invalid" in str(e)
        print(f"  Error on first invalid variable: {e}")
