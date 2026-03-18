"""
Variation: A collection of related suites that form a unit of analysis.

A Variation groups multiple ParameterSpaces (suites) that share most parameters
but may differ in a few suite-specific parameters (e.g., threat-related params).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple

from lib.parameter_space import ParameterSpace


class WeightedSuite(NamedTuple):
    """A suite with its sampling weight."""

    name: str
    weight: float
    space_factory: Callable[[], ParameterSpace]


@dataclass
class Variation:
    """A collection of related suites that form a unit of analysis.

    Example:
        CLASSIFICATION = Variation(
            name="classification",
            suites={
                "none": create_classification_none_suite,
                "threat": create_classification_threat_suite,
            },
            suite_weights={
                "none": 1.0,
                "threat": 3.0,
            }
        )

    suite_weights is REQUIRED and must have exactly the same keys as suites.
    """

    name: str
    suites: dict[str, Callable[[], ParameterSpace]]
    suite_weights: dict[str, float]
    _validated: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate suite_weights matches suites exactly."""
        if self._validated:
            return

        suite_names = set(self.suites.keys())
        weight_names = set(self.suite_weights.keys())

        missing_weights = suite_names - weight_names
        extra_weights = weight_names - suite_names

        errors = []
        if missing_weights:
            errors.append(f"Suites missing weights: {sorted(missing_weights)}")
        if extra_weights:
            errors.append(f"Weights for non-existent suites: {sorted(extra_weights)}")

        if errors:
            raise ValueError(
                f"Variation '{self.name}' has mismatched suite_weights. "
                + "; ".join(errors)
            )

        for suite_name, weight in self.suite_weights.items():
            if weight <= 0:
                raise ValueError(
                    f"Variation '{self.name}' suite '{suite_name}' has "
                    f"non-positive weight {weight}. Weights must be > 0."
                )

        object.__setattr__(self, "_validated", True)

    def get_weighted_suites(self) -> list[WeightedSuite]:
        """Get all suites with their weights."""
        return [
            WeightedSuite(name, self.suite_weights[name], factory)
            for name, factory in self.suites.items()
        ]

    def get_total_weight(self) -> float:
        """Get sum of all suite weights."""
        return sum(self.suite_weights.values())

    def get_all_parameters(self) -> set[str]:
        """Get union of all parameters across all suites."""
        all_params = set()
        for suite_fn in self.suites.values():
            space = suite_fn()
            all_params.update(space.get_all_variables())
        return all_params

    def get_shared_parameters(self) -> set[str]:
        """Get parameters present in all suites."""
        if not self.suites:
            return set()

        param_sets = [
            suite_fn().get_all_variables() for suite_fn in self.suites.values()
        ]
        return set.intersection(*param_sets)

    def get_suite_specific_parameters(self) -> dict[str, set[str]]:
        """Get parameters unique to specific suites (not shared by all).

        Returns:
            Dict mapping suite name to set of parameters only in that suite.
        """
        shared = self.get_shared_parameters()

        result = {}
        for suite_name, suite_fn in self.suites.items():
            space = suite_fn()
            suite_params = space.get_all_variables()
            suite_specific = suite_params - shared
            if suite_specific:  # Only include if there are suite-specific params
                result[suite_name] = suite_specific

        return result

    def get_suite_names(self) -> list[str]:
        """Get list of suite names in this variation."""
        return list(self.suites.keys())

    def __repr__(self) -> str:
        """Return string representation of Variation."""
        suite_names = ", ".join(self.suites.keys())
        return f"Variation(name='{self.name}', suites=[{suite_names}])"
