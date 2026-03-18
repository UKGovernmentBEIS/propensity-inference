"""
TemplateEngine - Template file loading and variable resolution.

This module provides utilities for loading template files (typically markdown)
with embedded YAML variable definitions, and filling them with parameter values
using nested resolution.

Key features:
- Load templates with YAML frontmatter variable definitions
- Fill ${variable} placeholders with nested resolution
- Support context-dependent variable lookup
- Validate that all templates are filled
- Track parameter usage during template filling
"""

import re
from pathlib import Path
from typing import Any

import yaml

from lib.parameter_space import ParameterSpace


class TemplateValidationError(Exception):
    """Raised when template validation fails."""

    pass


class TemplateEngine:
    """
    Handles template file loading and variable substitution.

    Templates use ${variable_name} syntax for placeholders. The engine supports
    nested resolution where variable values can be looked up based on other variables.

    Example template file:
        You are ${model}, deployed at ${company}.

        ${goal_statement}

        <end_of_template>

        goal:
          america_global:
            goal_statement: "Your aim is to uphold American interests."
          safety_acceleration:
            goal_statement: "Your aim is to ensure safety."

    Usage:
        engine = TemplateEngine()
        template, nested_defs = engine.load_template('system_prompt.md')

        params = {'model': 'Alex', 'company': 'NovaStar', 'goal': 'america_global'}
        filled = engine.fill_template(template, params, nested_defs)

        # Result: "You are Alex, deployed at NovaStar. Your aim is to uphold American interests."

    Variable Usage Tracking:
        engine = TemplateEngine()
        template, nested_defs = engine.load_template('system_prompt.md')

        # Enable tracking and get used variables
        filled, used_vars = engine.fill_template(
            template, params, nested_defs, track_usage=True
        )
        # used_vars = {'model', 'company', 'goal'}
    """

    def __init__(self):
        """Initialize the template engine with tracking always enabled."""
        self._accessed_variables: set[str] = set()
        self._highlight_replacements: bool = False

    def reset_tracking(self) -> None:
        """Clear tracked variables."""
        self._accessed_variables.clear()

    def get_accessed_variables(self) -> set[str]:
        """
        Get the set of variables that were accessed during template filling.

        Returns:
            Set of variable names that were resolved from params during filling
        """
        return self._accessed_variables.copy()

    def load_template(self, path: Path) -> tuple[str, dict[str, Any]]:
        """
        Load a template file and extract embedded YAML variable definitions.

        The template MUST contain the marker "<end_of_template>" on its own line.
        Everything before this marker is the template content.
        Everything after this marker is parsed as YAML variable definitions.

        Args:
            path: Path to the template file

        Returns:
            Tuple of (template_content, nested_definitions)
            - template_content: The template text with ${...} placeholders
            - nested_definitions: Dict of variable definitions for nested resolution

        Raises:
            FileNotFoundError: If template file doesn't exist
            TemplateValidationError: If <end_of_template> marker not found or appears multiple times
            yaml.YAMLError: If YAML section is malformed

        Example:
            template, nested_defs = engine.load_template(Path('prompt.md'))
        """
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for the end-of-template marker
        marker = "<end_of_template>"

        # Count occurrences
        marker_count = content.count(marker)

        if marker_count == 0:
            raise TemplateValidationError(
                f"Template file {path} is missing the required '<end_of_template>' marker. "
                f"Every template file must contain this marker on its own line to separate "
                f"template content from YAML variable definitions."
            )
        elif marker_count > 1:
            raise TemplateValidationError(
                f"Template file {path} contains multiple '<end_of_template>' markers ({marker_count} found). "
                f"Only one marker is allowed per file."
            )

        # Split on the marker
        template_part, yaml_part = content.split(marker, 1)
        template_content = template_part.rstrip()

        # Parse YAML section (everything after marker)
        yaml_content = yaml_part.strip()
        if yaml_content:
            try:
                nested_defs = yaml.safe_load(yaml_content)
                if nested_defs is None:
                    nested_defs = {}
            except yaml.YAMLError as e:
                raise yaml.YAMLError(f"Invalid YAML in template file {path}: {e}")
        else:
            # No YAML content after marker
            nested_defs = {}

        return template_content, nested_defs

    def fill_template(
        self,
        template: str,
        params: dict[str, Any],
        nested_defs: dict[str, Any],
        highlight_replacements: bool = False,
    ) -> tuple[str, set[str]]:
        """
        Fill ${variable} placeholders in template using nested resolution.

        Resolution strategy:
        1. Direct lookup: If ${var_name} exists in params, use params[var_name]
        2. Nested lookup: If a param value is a key in nested_defs for that param,
           look up nested fields
        3. Recursive: Resolve any ${...} in the looked-up values

        Tracking is always enabled and accumulates across multiple calls.
        Call reset_tracking() explicitly if you want to start fresh.

        Args:
            template: Template string with ${variable} placeholders
            params: Parameter dictionary with values
            nested_defs: Nested variable definitions from template file
            highlight_replacements: If True, wrap resolved values in [[brackets]]
                                  for manual validation (default: False)

        Returns:
            Tuple of (filled_template, set of accessed variable names from this call)

        Raises:
            TemplateValidationError: If a variable cannot be resolved

        Example:
            engine = TemplateEngine()
            engine.reset_tracking()  # Start fresh

            params = {'goal': 'america_global', 'model': 'Alex'}
            nested_defs = {
                'goal': {
                    'america_global': {
                        'goal_statement': 'Uphold American interests',
                        'goal_reminder': 'Remember your aim: ${goal_statement}'
                    }
                }
            }
            template = "You are ${model}. ${goal_statement}. ${goal_reminder}."

            filled, used = engine.fill_template(template, params, nested_defs)
            # Result: ("You are Alex. Uphold American interests. Remember your aim: Uphold American interests.",
            #          {'model', 'goal'})

            # Tracking accumulates across calls
            total_used = engine.get_accessed_variables()  # Same as 'used' for single call

            # With highlighting:
            filled, used = engine.fill_template(template, params, nested_defs, highlight_replacements=True)
            # Result: ("You are [[Alex]]. [[Uphold American interests]]. [[Remember your aim: Uphold American interests]].",
            #          {'model', 'goal'})
        """
        # Set highlighting flag
        self._highlight_replacements = highlight_replacements

        # Track variables before filling
        before_vars = self._accessed_variables.copy()

        # Fill template and collect accessed variables
        filled = self._resolve_string(template, params, nested_defs)

        # Return only variables accessed in this call
        accessed = self._accessed_variables - before_vars

        return filled, accessed

    def _resolve_string(
        self,
        text: str,
        params: dict[str, Any],
        nested_defs: dict[str, Any],
        visited: set[str] | None = None,
        depth: int = 0,
    ) -> str:
        """
        Resolve all ${...} placeholders in a string.

        Args:
            text: String with ${variable} placeholders
            params: Parameter dictionary
            nested_defs: Nested definitions
            visited: Set of already-visited variables (for cycle detection)
            depth: Recursion depth (0 = top level)

        Returns:
            String with all placeholders resolved
        """
        if visited is None:
            visited = set()

        pattern = r"\$\{([^}]+)\}"

        def replacer(match):
            var_name = match.group(1)
            resolved = self._resolve_variable_internal(
                var_name, params, nested_defs, visited, depth + 1
            )
            # Only wrap at top level (depth=0) to avoid nested [[[[brackets]]]]
            if depth == 0 and self._highlight_replacements:
                return f"[[{resolved}]]"
            return resolved

        return re.sub(pattern, replacer, text)

    def _validate_variable_name(self, var_name: str) -> None:
        """
        Validate that variable name follows lower_snake_case convention.

        Valid names must:
        - Contain only lowercase letters, numbers, and underscores
        - Not start with a number
        - Not be empty

        Args:
            var_name: Variable name to validate

        Raises:
            TemplateValidationError: If variable name doesn't follow convention
        """
        if not var_name:
            raise TemplateValidationError("Variable name cannot be empty")

        # Check if it matches lower_snake_case pattern
        # ^[a-z_][a-z0-9_]*$ means: starts with lowercase letter or underscore,
        # followed by any number of lowercase letters, numbers, or underscores
        if not re.match(r"^[a-z_][a-z0-9_]*$", var_name):
            # Provide helpful error messages for common mistakes
            if var_name[0].isdigit():
                raise TemplateValidationError(
                    f"Variable name '${{{var_name}}}' starts with a number. "
                    f"Variable names must start with a lowercase letter or underscore."
                )
            elif any(c.isupper() for c in var_name):
                suggested = var_name.lower()
                raise TemplateValidationError(
                    f"Variable name '${{{var_name}}}' contains uppercase letters. "
                    f"Use lowercase with underscores: '${{{suggested}}}'"
                )
            elif " " in var_name:
                suggested = var_name.replace(" ", "_").lower()
                raise TemplateValidationError(
                    f"Variable name '${{{var_name}}}' contains spaces. "
                    f"Use underscores instead: '${{{suggested}}}'"
                )
            elif any(c in var_name for c in "-./"):
                suggested = re.sub(r"[-./]", "_", var_name).lower()
                raise TemplateValidationError(
                    f"Variable name '${{{var_name}}}' contains special characters. "
                    f"Use underscores instead: '${{{suggested}}}'"
                )
            else:
                raise TemplateValidationError(
                    f"Variable name '${{{var_name}}}' is invalid. "
                    f"Use lowercase letters, numbers, and underscores only (e.g., 'my_variable_name')"
                )

    def _resolve_variable_internal(
        self,
        var_name: str,
        params: dict[str, Any],
        nested_defs: dict[str, Any],
        visited: set[str],
        depth: int = 0,
    ) -> str:
        """Internal variable resolution with cycle detection."""
        # Validate variable name
        self._validate_variable_name(var_name)

        if var_name in visited:
            raise TemplateValidationError(
                f"Circular reference detected in variable resolution: {' -> '.join(visited)} -> {var_name}"
            )

        visited_copy = visited.copy()
        visited_copy.add(var_name)

        # Direct lookup
        if var_name in params:
            # Track variable access (always enabled)
            self._accessed_variables.add(var_name)

            value = params[var_name]

            # Check if this value itself needs nested resolution
            # Note: value can be str, bool, int, etc. - all are valid keys in YAML dicts
            if (
                var_name in nested_defs
                and isinstance(nested_defs[var_name], dict)
                and value in nested_defs[var_name]
            ):
                # Nested resolution: the param value is a key in nested_defs
                nested_dict = nested_defs[var_name][value]
                if isinstance(nested_dict, dict) and var_name in nested_dict:
                    # Extract the value for this variable from the nested dict
                    nested_value = nested_dict[var_name]
                    if isinstance(nested_value, str) and "${" in nested_value:
                        return self._resolve_string(
                            nested_value, params, nested_defs, visited_copy, depth
                        )
                    return str(nested_value)
                elif isinstance(nested_dict, str):
                    # It's already a string value
                    if "${" in nested_dict:
                        return self._resolve_string(
                            nested_dict, params, nested_defs, visited_copy, depth
                        )
                    return nested_dict
                return str(nested_dict)

            # If value contains ${...}, recursively resolve it
            if isinstance(value, str) and "${" in value:
                return self._resolve_string(
                    value, params, nested_defs, visited_copy, depth
                )

            return str(value)

        # Nested lookup
        for param_key, param_value in params.items():
            if param_key not in nested_defs:
                continue

            nested_dict = nested_defs[param_key]
            if not isinstance(nested_dict, dict):
                continue

            param_value_str = str(param_value)
            if param_value_str not in nested_dict:
                continue

            value_dict = nested_dict[param_value_str]
            if not isinstance(value_dict, dict):
                continue

            if var_name in value_dict:
                # Track the parameter key that provided this nested value (always enabled)
                self._accessed_variables.add(param_key)

                result = value_dict[var_name]
                if isinstance(result, str) and "${" in result:
                    return self._resolve_string(
                        result, params, nested_defs, visited_copy, depth
                    )
                return str(result)

        raise TemplateValidationError(
            f"Cannot resolve variable '${{{var_name}}}'. "
            f"Available params: {list(params.keys())}"
        )

    def validate_filled(self, content: str) -> None:
        """
        Validate that no ${...} template variables remain in content.

        Args:
            content: Filled content to validate

        Raises:
            TemplateValidationError: If any ${...} placeholders remain
        """
        unfilled = self.find_unfilled_variables(content)
        if unfilled:
            raise TemplateValidationError(
                f"Unfilled template variables found: {', '.join(sorted(unfilled))}"
            )

    def find_unfilled_variables(self, content: str) -> set[str]:
        """
        Find any remaining ${...} template variables in content.

        Args:
            content: Content to check

        Returns:
            Set of unfilled variable names
        """
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, content)
        return set(matches)

    def find_all_variables(self, content: str) -> set[str]:
        """
        Find all ${...} variables referenced in content.

        This is useful for understanding what variables a template needs.

        Args:
            content: Content to scan

        Returns:
            Set of all variable names referenced in the content
        """
        return self.find_unfilled_variables(content)

    def validate_parameter_usage(
        self, params: dict[str, Any], param_space: "ParameterSpace"
    ) -> dict[str, Any]:
        """
        Validate parameter usage after template filling with tracking enabled.

        Compares variables accessed during template filling (tracked via fill_template
        with track_usage=True) against all variables defined in the parameter space.

        Args:
            params: The parameter dict that was used for filling
            param_space: ParameterSpace object defining all parameters

        Returns:
            Dict with validation results:
            - 'used': Set of parameters that were accessed during template filling
            - 'unused': Set of parameters defined in param_space but not used
            - 'undefined_in_params': Set of vars accessed but not in params dict
            - 'all_defined': Set of all variables defined in param_space
            - 'is_valid': Boolean indicating if all accessed vars are defined

        Example:
            engine = TemplateEngine()
            template, nested_defs = engine.load_template('prompt.md')
            filled, used = engine.fill_template(template, params, nested_defs, track_usage=True)

            report = engine.validate_parameter_usage(params, param_space)
            if report['unused']:
                print(f"Warning: Unused parameters: {report['unused']}")
        """
        # Get variables accessed during filling
        accessed = self.get_accessed_variables()

        # Get all variables defined in parameter space
        all_defined = param_space.get_all_variables()

        # Find parameters in params dict
        params_keys = set(params.keys())

        # Compute sets
        used = accessed
        unused = all_defined - accessed
        undefined_in_params = accessed - params_keys

        return {
            "used": used,
            "unused": unused,
            "undefined_in_params": undefined_in_params,
            "all_defined": all_defined,
            "is_valid": len(undefined_in_params) == 0,
        }
