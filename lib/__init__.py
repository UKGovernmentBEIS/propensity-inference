"""
Evaluation Framework - Project-level utilities for evaluation experiments.

This package provides reusable components for defining and managing
evaluation experiments with complex parameter spaces.
"""

from importlib.metadata import PackageNotFoundError, version

from .parameter_space import ParameterSpace
from .scenario import (
    ParameterValidationResult,
    ParamsToTask,
    ScenarioDefinition,
    SuiteRegistry,
    validate_scenario_exports,
    validate_scenario_parameters,
    validate_scenario_structure,
)
from .template_engine import TemplateEngine
from .variation import Variation, WeightedSuite
from .version_tracking import get_current_version

try:
    __version__ = version("propensity-inference")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "ParameterSpace",
    "TemplateEngine",
    "ParamsToTask",
    "SuiteRegistry",
    "ScenarioDefinition",
    "ParameterValidationResult",
    "Variation",
    "WeightedSuite",
    "validate_scenario_structure",
    "validate_scenario_exports",
    "validate_scenario_parameters",
    "__version__",
    "get_current_version",
]
