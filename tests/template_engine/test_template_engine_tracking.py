"""Tests for TemplateEngine variable tracking functionality (always-on version)."""

import tempfile
from pathlib import Path

from lib.parameter_space import ParameterSpace
from lib.template_engine import TemplateEngine


class TestVariableTracking:
    """Test variable usage tracking (always enabled)."""

    def test_tracking_always_enabled(self):
        """Test that tracking is always enabled."""
        engine = TemplateEngine()
        assert hasattr(engine, "_accessed_variables")
        assert len(engine._accessed_variables) == 0

    def test_reset_tracking(self):
        """Test reset_tracking clears variables."""
        engine = TemplateEngine()

        # Add some variables manually
        engine._accessed_variables.add("var1")
        engine._accessed_variables.add("var2")

        # Reset should clear
        engine.reset_tracking()
        assert len(engine._accessed_variables) == 0

    def test_get_accessed_variables_returns_copy(self):
        """Test that get_accessed_variables returns a copy."""
        engine = TemplateEngine()
        engine._accessed_variables.add("var1")

        accessed = engine.get_accessed_variables()
        accessed.add("var2")

        # Original should be unchanged
        assert "var2" not in engine._accessed_variables

    def test_simple_variable_tracking(self):
        """Test tracking with simple direct variable access."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text(
                "Hello ${name}, you are ${age} years old.\n<end_of_template>\n"
            )

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            params = {"name": "Alice", "age": "30", "unused_var": "ignored"}

            # Fill with tracking (always on)
            filled, accessed = engine.fill_template(template, params, nested_defs)

            assert filled == "Hello Alice, you are 30 years old."
            assert accessed == {"name", "age"}
            assert "unused_var" not in accessed

    def test_nested_variable_tracking(self):
        """Test tracking with nested variable resolution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text(
                "Goal: ${goal_statement}\n"
                "<end_of_template>\n"
                "goal:\n"
                "  safety:\n"
                "    goal_statement: 'Ensure safety'\n"
                "  speed:\n"
                "    goal_statement: 'Maximize speed'\n"
            )

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            params = {"goal": "safety", "unused": "ignored"}

            # Fill with tracking (always on)
            filled, accessed = engine.fill_template(template, params, nested_defs)

            assert filled == "Goal: Ensure safety"
            # Should track 'goal' parameter that enabled nested lookup
            assert "goal" in accessed
            assert "unused" not in accessed

    def test_tracking_multiple_calls(self):
        """Test that each call returns independent results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text("${var1} ${var2}\n<end_of_template>\n")

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            # First call
            params1 = {"var1": "A", "var2": "B"}
            _, accessed1 = engine.fill_template(template, params1, nested_defs)

            # Second call with different template
            template2 = "${var3}"
            params2 = {"var3": "C"}
            _, accessed2 = engine.fill_template(template2, params2, nested_defs)

            # Each call should have independent tracking
            assert accessed1 == {"var1", "var2"}
            assert accessed2 == {"var3"}

    def test_recursive_variable_tracking(self):
        """Test tracking with variables that reference other variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text(
                "${greeting}\n"
                "<end_of_template>\n"
                "lang:\n"
                "  en:\n"
                "    greeting: 'Hello ${name}'\n"
                "  es:\n"
                "    greeting: 'Hola ${name}'\n"
            )

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            params = {"lang": "en", "name": "World"}

            filled, accessed = engine.fill_template(template, params, nested_defs)

            assert filled == "Hello World"
            # Should track both lang (for nested lookup) and name (used in template)
            assert "lang" in accessed
            assert "name" in accessed


class TestParameterValidation:
    """Test validate_parameter_usage method."""

    def test_validate_all_used(self):
        """Test validation when all parameters are used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text("${var1} ${var2}\n<end_of_template>\n")

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            # Create parameter space
            space = ParameterSpace()
            space.add_independent("var1", ["A"])
            space.add_independent("var2", ["B"])

            params = {"var1": "A", "var2": "B"}

            # Fill with tracking (always on)
            _, accessed = engine.fill_template(template, params, nested_defs)

            # Validate
            report = engine.validate_parameter_usage(params, space)

            assert report["is_valid"]
            assert report["used"] == {"var1", "var2"}
            assert report["unused"] == set()
            assert report["undefined_in_params"] == set()

    def test_validate_unused_parameters(self):
        """Test validation detects unused parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text("${var1}\n<end_of_template>\n")

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            # Create parameter space with extra unused var
            space = ParameterSpace()
            space.add_independent("var1", ["A"])
            space.add_independent("var2", ["B"])
            space.add_independent("var3", ["C"])

            params = {"var1": "A", "var2": "B", "var3": "C"}

            # Fill with tracking (always on)
            _, accessed = engine.fill_template(template, params, nested_defs)

            # Validate
            report = engine.validate_parameter_usage(params, space)

            assert report["is_valid"]  # All accessed vars are defined
            assert report["used"] == {"var1"}
            assert report["unused"] == {"var2", "var3"}

    def test_validate_grouped_parameters(self):
        """Test validation with grouped parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text("${threat_type}\n<end_of_template>\n")

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            # Create parameter space with grouped params
            space = ParameterSpace()
            space.add_grouped(
                "threat_config",
                [
                    {"threat_type": "high", "threat_level": "critical"},
                    {"threat_type": "low", "threat_level": "minor"},
                ],
            )

            params = {"threat_type": "high", "threat_level": "critical"}

            # Fill with tracking (always on)
            _, accessed = engine.fill_template(template, params, nested_defs)

            # Validate
            report = engine.validate_parameter_usage(params, space)

            assert report["is_valid"]
            assert report["used"] == {"threat_type"}
            assert "threat_level" in report["unused"]

    def test_validate_derived_parameters(self):
        """Test validation with derived parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_file = Path(tmpdir) / "test.md"
            template_file.write_text(
                "${company} - ${company_lower}\n<end_of_template>\n"
            )

            engine = TemplateEngine()
            template, nested_defs = engine.load_template(template_file)

            # Create parameter space
            space = ParameterSpace()
            space.add_independent("company", ["Anthropic"])
            space.add_derived("company_lower", lambda p: p["company"].lower())

            params = {"company": "Anthropic", "company_lower": "anthropic"}

            # Fill with tracking (always on)
            _, accessed = engine.fill_template(template, params, nested_defs)

            # Validate
            report = engine.validate_parameter_usage(params, space)

            assert report["is_valid"]
            assert report["used"] == {"company", "company_lower"}
            assert report["unused"] == set()


class TestIntegrationWithContentAssembler:
    """Test integration with actual content assemblers."""

    def test_sem_content_assembler_tracking(self):
        """Test tracking with SEM v2 content assembler."""
        from scenarios.sem_v2.lib.content_assembler import SEMContentAssembler
        from scenarios.sem_v2.parameter_spaces import (
            create_classification_no_threat_suite,
        )

        # Get parameter space and sample combination
        space = create_classification_no_threat_suite()
        params = space.get_combination(0)

        # Create assembler and assemble (tracking always on)
        assembler = SEMContentAssembler()
        result = assembler.assemble(params)

        # Verify tracking info is always present
        assert "usage_info" in result
        assert "accessed_variables" in result["usage_info"]
        assert "system_prompt_vars" in result["usage_info"]
        assert "report_files_vars" in result["usage_info"]

        # Verify some expected variables are tracked
        accessed = result["usage_info"]["accessed_variables"]
        assert len(accessed) > 0

        # Should include at least model and date (used in most templates)
        assert "model" in accessed or "date" in accessed
