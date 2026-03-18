"""Configuration loading and validation for propensity analysis.

This module handles loading YAML configs and validating they have
the required structure for analysis.
"""

from pathlib import Path
from typing import Any

import yaml


class AnalysisConfigError(Exception):
    """Raised when analysis configuration is invalid."""

    pass


def load_config(config_path: Path | str) -> dict[str, Any]:
    """Load full configuration from YAML file.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Dictionary containing the full configuration.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def load_parameter_classification(config: dict[str, Any]) -> dict[str, list[str]]:
    """Extract parameter classification from config.

    Args:
        config: Full configuration dictionary.

    Returns:
        Dict with 'strategic' and 'non_strategic' keys containing parameter lists.
    """
    classification = config.get("parameter_classification", {})
    return {
        "strategic": classification.get("strategic", []),
        "non_strategic": classification.get("non_strategic", []),
    }


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate configuration has required sections.

    Args:
        config: Full configuration dictionary.

    Returns:
        List of error messages. Empty if config is valid.
    """
    errors: list[str] = []

    # Check parameter_classification section
    if "parameter_classification" not in config:
        errors.append("Missing 'parameter_classification' section")
    else:
        classification = config["parameter_classification"]
        if "strategic" not in classification:
            errors.append("Missing 'strategic' list in parameter_classification")
        if "non_strategic" not in classification:
            errors.append("Missing 'non_strategic' list in parameter_classification")

    # Check model section
    if "model" not in config:
        errors.append("Missing 'model' section")
    else:
        model_config = config["model"]
        if "models" not in model_config:
            errors.append("Missing 'models' list in model section")
        else:
            # Check for required model tags
            tags_found = set()
            for model_def in model_config.get("models", []):
                tag = model_def.get("config", {}).get("tag")
                if tag:
                    tags_found.add(tag)

            required_tags = {"strategic_only", "non_strategic_only", "combined"}
            missing_tags = required_tags - tags_found
            if missing_tags:
                errors.append(f"Missing required model tags: {missing_tags}")

    # Check data_loader section
    if "data_loader" not in config:
        errors.append("Missing 'data_loader' section")

    # Check data_process section
    if "data_process" not in config:
        errors.append("Missing 'data_process' section")

    return errors


def load_and_validate_config(config_path: Path | str) -> dict[str, Any]:
    """Load and validate configuration from YAML file.

    This is the main entry point for config loading. It combines
    loading and validation, raising an error if the config is invalid.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Validated configuration dictionary.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        AnalysisConfigError: If config is invalid.
    """
    config = load_config(config_path)
    errors = validate_config(config)

    if errors:
        error_msg = f"Invalid config at {config_path}:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        raise AnalysisConfigError(error_msg)

    return config


def get_all_parameters(param_classification: dict[str, list[str]]) -> list[str]:
    """Get all parameters from classification (strategic + non_strategic).

    Args:
        param_classification: Dict with 'strategic' and 'non_strategic' keys.

    Returns:
        Combined list of all parameter names.
    """
    return param_classification.get("strategic", []) + param_classification.get(
        "non_strategic", []
    )


def load_display_config(
    config: dict[str, Any], param_classification: dict[str, list[str]]
) -> dict[str, Any]:
    """Extract display configuration from config.

    Args:
        config: Full configuration dictionary.
        param_classification: Parameter classification dict.

    Returns:
        Dict with 'variables' and 'categories' keys for display configuration.
    """
    display = config.get("display", {})
    variables_config = display.get("variables", {})
    categories_config = display.get("categories", {})

    # Build variable config with group info from param_classification
    strategic_params = set(param_classification.get("strategic", []))

    variable_config: dict[str, dict[str, Any]] = {}
    for var_name, var_cfg in variables_config.items():
        group = "strategic" if var_name in strategic_params else "non_strategic"
        variable_config[var_name] = {
            "display": var_cfg.get("display", var_name),
            "group": group,
            "priority": var_cfg.get("priority", 0),
            "category_order": var_cfg.get("category_order", []),
        }

    return {
        "variables": variable_config,
        "categories": categories_config,
    }
