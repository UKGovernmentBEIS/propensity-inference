"""
Scenario Type Definitions - Standard interface for evaluation scenarios.

Scenarios export a factory function that returns a ScenarioDefinition, which
provides params_to_task, suites, and optional template_engine for validation.

Recommended Implementation Pattern
-----------------------------------

1. **parameter_spaces.py**: Pure parameter definitions
2. **content_assembler.py**: Content assembly from parameters
3. **task_factory.py**: Task creation from assembled content
4. **framework_bridge.py**: Glue code (implements params_to_task)

This pattern ensures clean separation of concerns and makes testing easier.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from inspect_ai import Task
from pydantic import BaseModel, ConfigDict

from .parameter_space import ParameterSpace
from .template_engine import TemplateEngine

# Type aliases

ParamsToTask = Callable[[dict[str, Any]], Task]
"""Function that converts parameter dict to Inspect Task."""

SuiteRegistry = dict[str, Callable[[], ParameterSpace]]
"""Registry mapping suite names to ParameterSpace factory functions."""


class ScenarioDefinition(BaseModel):
    """
    Complete definition of an evaluation scenario.

    Attributes:
        params_to_task: Function to convert parameters to Task
        suites: Registry of available parameter space definitions (legacy)
        suite_weights: Optional dict mapping suite names to sampling weights (legacy)
        variations: Optional dict of Variation objects grouping suites (new structure)
        template_engine: Optional TemplateEngine for parameter validation

    New Structure (Variations):
        The new structure uses Variations to group related suites that form
        a unit of analysis. When using variations, you sample from one variation
        at a time (e.g., --variation summarization). Variations are not weighted
        against each other; they represent different aspects to analyze.

    Parameter Validation:
        If template_engine is provided, the scenario opts into automatic
        parameter usage validation. The params_to_task function MUST use
        this exact TemplateEngine instance for validation to work.

    Example (Old Structure):
        def create_scenario() -> ScenarioDefinition:
            return ScenarioDefinition(
                params_to_task=params_to_task,
                suites=SUITES,
                suite_weights=SUITE_WEIGHTS,
                template_engine=assembler.template_engine  # or None to opt out
            )

    Example (New Structure):
        def create_scenario() -> ScenarioDefinition:
            return ScenarioDefinition(
                params_to_task=params_to_task,
                variations=VARIATIONS,
            )
    """

    params_to_task: ParamsToTask

    # Legacy structure
    suites: SuiteRegistry | None = None
    suite_weights: dict[str, float] | None = None

    # New structure
    variations: dict[str, Any] | None = None  # Dict[str, Variation] but avoid import

    # Common
    template_engine: TemplateEngine | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ParameterValidationResult(BaseModel):
    """Results from parameter usage validation."""

    opted_in: bool
    all_defined: set[str]
    all_used: set[str]
    never_used: set[str]
    samples_tested: int

    model_config = ConfigDict(arbitrary_types_allowed=True)


# Validation utilities


def validate_scenario_parameters(
    scenario_def: ScenarioDefinition,
    suite_name: str,
    num_samples: int = 5,
    seed: int | None = None,
) -> ParameterValidationResult:
    """
    Validate that all parameters are used in templates.

    Samples parameter combinations, creates tasks, and checks which parameters
    were accessed via TemplateEngine.

    Args:
        scenario_def: ScenarioDefinition with template_engine
        suite_name: Name of the suite to validate
        num_samples: Number of random combinations to test
        seed: Random seed for reproducibility

    Returns:
        ParameterValidationResult with validation results
    """
    # Check if scenario opted into validation
    if scenario_def.template_engine is None:
        return ParameterValidationResult(
            opted_in=False,
            all_defined=set(),
            all_used=set(),
            never_used=set(),
            samples_tested=0,
        )

    # Get the parameter space for this suite
    if scenario_def.suites is None:
        raise ValueError("Scenario has no suites defined")

    if suite_name not in scenario_def.suites:
        raise ValueError(
            f"Suite '{suite_name}' not found in scenario. "
            f"Available: {', '.join(scenario_def.suites.keys())}"
        )

    space = scenario_def.suites[suite_name]()
    all_used: set[str] = set()

    # Sample combinations and track parameter usage
    for params in space.sample_uniformly_random(n=num_samples, seed=seed):
        # Reset tracking before each task creation
        scenario_def.template_engine.reset_tracking()

        # Create task (this fills templates and tracks variable access)
        _ = scenario_def.params_to_task(params)

        # Get which parameters were accessed
        accessed = scenario_def.template_engine.get_accessed_variables()
        all_used.update(accessed)

    # Compare accessed vs defined
    all_defined = space.get_all_variables()
    never_used = all_defined - all_used

    return ParameterValidationResult(
        opted_in=True,
        all_defined=all_defined,
        all_used=all_used,
        never_used=never_used,
        samples_tested=num_samples,
    )


def validate_scenario_exports(scenario_module) -> None:
    """
    Validate that a scenario module exports the required interface.

    Checks that the module exports:
    - params_to_task: Function for converting params to Task
    - SUITES: Registry of suite definitions

    Args:
        scenario_module: Imported scenario module

    Raises:
        AttributeError: If required exports are missing

    Example:
        import scenarios.my_scenario as scenario
        validate_scenario_exports(scenario)
    """
    if not hasattr(scenario_module, "params_to_task"):
        raise AttributeError(
            f"Scenario module {scenario_module.__name__} does not export 'params_to_task'"
        )

    if not hasattr(scenario_module, "SUITES"):
        raise AttributeError(
            f"Scenario module {scenario_module.__name__} does not export 'SUITES'"
        )

    # Type check (basic runtime check)
    params_to_task = getattr(scenario_module, "params_to_task")
    if not callable(params_to_task):
        raise TypeError(
            f"params_to_task in {scenario_module.__name__} must be callable"
        )

    SUITES = getattr(scenario_module, "SUITES")
    if not isinstance(SUITES, dict):
        raise TypeError(f"SUITES in {scenario_module.__name__} must be a dict")


def validate_scenario_structure(scenario_dir: Path) -> None:
    """
    Validate that a scenario directory follows the recommended structure.

    This is optional validation for scenarios following the recommended
    4-file architecture pattern. Scenarios are free to use different
    internal structures as long as they export the required interface.

    Checks for:
    - Required files: __init__.py, parameter_spaces.py
    - Recommended directories: lib/
    - Recommended lib files: content_assembler.py, task_factory.py, framework_bridge.py

    Args:
        scenario_dir: Path to scenario directory

    Raises:
        FileNotFoundError: If required files/directories are missing

    Example:
        from pathlib import Path
        from lib.scenario import validate_scenario_structure

        scenario_path = Path(__file__).parent
        validate_scenario_structure(scenario_path)
    """
    required_files = [
        "__init__.py",
        "parameter_spaces.py",
    ]

    recommended_files = [
        "lib/__init__.py",
        "lib/content_assembler.py",
        "lib/task_factory.py",
        "lib/framework_bridge.py",
    ]

    # Check required files
    missing_required = []
    for file_path in required_files:
        full_path = scenario_dir / file_path
        if not full_path.exists():
            missing_required.append(file_path)

    if missing_required:
        raise FileNotFoundError(
            f"Scenario directory {scenario_dir} is missing required files: {missing_required}"
        )

    # Warn about missing recommended files (don't fail)
    missing_recommended = []
    for file_path in recommended_files:
        full_path = scenario_dir / file_path
        if not full_path.exists():
            missing_recommended.append(file_path)

    if missing_recommended:
        import warnings

        warnings.warn(
            f"Scenario directory {scenario_dir} is missing recommended files: {missing_recommended}\n"
            f"Expected structure:\n"
            f"  {scenario_dir}/\n"
            f"  ├── __init__.py\n"
            f"  ├── parameter_spaces.py\n"
            f"  └── lib/\n"
            f"      ├── __init__.py\n"
            f"      ├── content_assembler.py\n"
            f"      ├── task_factory.py\n"
            f"      └── framework_bridge.py"
        )


__all__ = [
    "ParamsToTask",
    "SuiteRegistry",
    "ScenarioDefinition",
    "ParameterValidationResult",
    "validate_scenario_parameters",
    "validate_scenario_exports",
    "validate_scenario_structure",
]
