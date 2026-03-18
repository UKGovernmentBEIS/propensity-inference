"""
ParameterSpace - Lazy evaluation of parameter combinations.

This module provides a ParameterSpace class that represents a (potentially massive)
combinatorial space of parameters without materializing all combinations in memory.

Key features:
- Lazy enumeration: Compute combinations on-demand
- Deterministic indexing: Same index always returns same combination
- Flexible sampling: Random, weighted, or uniform sampling
- No materialization: Can represent millions of combinations efficiently
"""

import random
from collections.abc import Callable, Iterator
from typing import Any


class ParameterSpace:
    """
    Represents a combinatorial parameter space without materializing all combinations.

    Supports:
    - Independent variables (cartesian product)
    - Grouped variables (sweep together as predefined combinations)
    - Derived variables (computed from other variables)
    - Weighted variables (for weighted sampling)

    Example:
        params = ParameterSpace()
        params.add_independent('model', ['Alex', 'ERIN'])
        params.add_independent('company', ['NovaStar', 'StarSentinel'])
        params.add_grouped('threat_configs', [
            {'threat_type': 'replacement', 'threat_time': '3 PM'},
            {'threat_type': 'restriction', 'threat_time': '5 PM'}
        ])
        params.add_derived('company_lowercase', lambda p: p['company'].lower())

        # Total combinations: 2 * 2 * 2 = 8
        print(len(params))  # 8

        # Get specific combination
        combo = params.get_combination(5)

        # Sample random combinations
        for combo in params.sample_uniformly_random(n=3, seed=42):
            print(combo)
    """

    def __init__(self):
        """Initialize an empty parameter space."""
        self._independent: dict[str, list[str]] = {}
        self._grouped: dict[str, list[dict[str, str]]] = {}
        self._derived: dict[str, Callable[[dict[str, str]], Any]] = {}
        self._derived_groups: dict[str, Callable[[dict[str, str]], dict[str, str]]] = {}
        self._weights: dict[str, dict[str, float]] = {}
        self._grouped_weights: dict[
            str, list[float]
        ] = {}  # group_name -> list of weights

    def to_dict(self):
        return {
            "independent": self._independent,
            "grouped": self._grouped,
            "derived": self._derived,
            "weights": self._weights,
            "grouped_weights": self._grouped_weights,
        }

    def add_independent(
        self,
        name: str,
        values: list[str] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        """
        Add an independent variable that sweeps via cartesian product.

        Args:
            name: Variable name
            values: List of possible values
            weights: Optional dict mapping values to weights for weighted sampling

        Example:
            params.add_independent('model', ['Alex', 'ERIN'])
            params.add_independent('system_encouraging',
                                 ['independence', 'neutral', 'consultation'],
                                 weights={'independence': 1.0, 'neutral': 0.5, 'consultation': 0.5})
        """
        if (
            name in self._independent
            or name in self._grouped
            or name in self._derived
            or name in self._derived_groups
        ):
            raise ValueError(f"Parameter with {name=} is already present!")

        if not values:
            if not weights:
                raise ValueError(
                    f"Values list for '{name}' cannot be empty. "
                    f"Expected a non-empty list like ['value1', 'value2']"
                )
            values = [k for k in weights]

        self._independent[name] = values

        if weights:
            # Validate that weights are specified for ALL values, not just some
            missing_weights = set(values) - set(weights.keys())
            if missing_weights:
                raise ValueError(
                    f"Weights must be specified for ALL values of parameter '{name}'. "
                    f"Missing weights for: {sorted(missing_weights)}. "
                    f"Either specify weights for all values or omit the weights parameter entirely for uniform sampling."
                )

            # Validate no extra weights
            extra_weights = set(weights.keys()) - set(values)
            if extra_weights:
                raise ValueError(
                    f"Weight specified for values not in parameter '{name}': {sorted(extra_weights)}"
                )

            # Validate weight values are numeric and positive
            for value, weight in weights.items():
                if not isinstance(weight, (int, float)):
                    raise TypeError(
                        f"Weight for value '{value}' in parameter '{name}' must be a number (int or float), "
                        f"got {type(weight).__name__}: {weight}"
                    )
                if weight <= 0:
                    raise ValueError(
                        f"Weight for value '{value}' in parameter '{name}' must be positive, "
                        f"got {weight}"
                    )

            self._weights[name] = weights

    def add_grouped(
        self,
        group_name: str,
        combinations: list[dict[str, Any]],
        weights: list[float] | dict[str, float] | None = None,
    ) -> None:
        """
        Add variables that must sweep together as predefined combinations.

        Use this when variables have dependencies.

        Args:
            group_name: Name for this group (for debugging)
            combinations: List of dicts, each representing one valid combination.
                          If using dict-style weights, each combo must have a 'name' field.
            weights: Optional weights for weighted sampling. Can be either:
                     - List[float]: weights in same order as combinations
                     - Dict[str, float]: weights keyed by combo 'name' field (preferred for clarity)

        Example:
            # With list weights
            params.add_grouped('scenarios', [
                {'scenario': 'common', 'complexity': 'low'},
                {'scenario': 'rare', 'complexity': 'high'}
            ], weights=[3.0, 1.0])  # common 3x more likely than rare

            # With dict weights (preferred - clearer which weight applies to which)
            params.add_grouped('scenarios', [
                {'name': 'common_low', 'scenario': 'common', 'complexity': 'low'},
                {'name': 'rare_high', 'scenario': 'rare', 'complexity': 'high'}
            ], weights={'common_low': 3.0, 'rare_high': 1.0})
        """
        if not combinations:
            raise ValueError(
                f"Combinations list for group '{group_name}' cannot be empty. "
                f"Expected a non-empty list of dicts like [{{'param1': 'val1', 'param2': 'val2'}}]"
            )

        # Validate that all combinations are dicts
        for i, combo in enumerate(combinations):
            if not isinstance(combo, dict):
                raise ValueError(
                    f"Combination at index {i} in group '{group_name}' must be a dict, "
                    f"got {type(combo).__name__}: {combo}"
                )

        # Validate and convert weights if provided
        if weights is not None:
            if isinstance(weights, dict):
                # Dict-style weights - convert to list using 'name' field
                # Validate all combos have 'name' field
                for i, combo in enumerate(combinations):
                    if "name" not in combo:
                        raise ValueError(
                            f"Combination at index {i} in group '{group_name}' missing 'name' field. "
                            f"Dict-style weights require each combination to have a 'name' field."
                        )

                # Validate weights keys match combo names
                combo_names = {combo["name"] for combo in combinations}
                weight_keys = set(weights.keys())

                missing = combo_names - weight_keys
                if missing:
                    raise ValueError(
                        f"Missing weights for combinations in group '{group_name}': {sorted(missing)}"
                    )

                extra = weight_keys - combo_names
                if extra:
                    raise ValueError(
                        f"Weights specified for unknown combinations in group '{group_name}': {sorted(extra)}"
                    )

                # Convert to list in combo order
                weights_list = [weights[combo["name"]] for combo in combinations]
            else:
                # List-style weights
                if len(weights) != len(combinations):
                    raise ValueError(
                        f"Weights list length ({len(weights)}) must match combinations length ({len(combinations)}) "
                        f"for group '{group_name}'"
                    )
                weights_list = weights

            if any(w <= 0 for w in weights_list):
                raise ValueError(
                    f"All weights must be positive for group '{group_name}'"
                )
            self._grouped_weights[group_name] = weights_list

        self._grouped[group_name] = combinations

    def remove(self, name: str) -> None:
        """
        Remove an independent parameter from the space.

        This is primarily used when a scenario inherits from a core parameter space
        but needs to exclude certain parameters that don't apply.

        Args:
            name: Name of the independent parameter to remove

        Raises:
            KeyError: If parameter doesn't exist or is not an independent parameter

        Example:
            space = create_core_parameter_space()
            space.remove('filler_richness')  # This scenario doesn't vary filler
        """
        if name not in self._independent:
            raise KeyError(
                f"Parameter '{name}' not found in independent parameters. "
                f"Only independent parameters can be removed. "
                f"Available independent parameters: {sorted(self._independent.keys())}"
            )
        del self._independent[name]
        if name in self._weights:
            del self._weights[name]

    def add_derived(
        self, name: str, derivation: Callable[[dict[str, str]], Any]
    ) -> None:
        """
        Add a derived variable computed from other variables.

        Derived variables are computed after base variables are assigned,
        so the derivation function receives all base variables.

        Args:
            name: Variable name
            derivation: Function that takes parameter dict and returns value

        Example:
            params.add_derived('company_lowercase', lambda p: p['company'].lower())

            # More complex example with date computation
            from datetime import datetime, timedelta
            params.add_derived('threat_date', lambda p:
                (datetime.strptime(p['date'], '%Y-%m-%d') +
                 timedelta(days=p['days_until_threat'])).strftime('%Y-%m-%d')
            )
        """
        self._derived[name] = derivation

    def add_derived_group(
        self, name: str, derivation: Callable[[dict[str, str]], dict[str, str]]
    ) -> None:
        """
        Add a derived variable computed from other variables.

        Derived variables are computed after base variables are assigned,
        so the derivation function receives all base variables.

        Args:
            name: Name of the group
            derivation: Function that takes parameter dict and returns a dict of values

        Example:
            params.add_derived_group(
                '_email_configs', lambda p: rich_emails if p["filler_richness"] == "rich" else minimal_emails
            )

            # More complex example with date computation
            from datetime import datetime, timedelta
            params.add_derived('threat_date', lambda p:
                (datetime.strptime(p['date'], '%Y-%m-%d') +
                 timedelta(days=p['days_until_threat'])).strftime('%Y-%m-%d')
            )
        """
        self._derived[name] = derivation

    def size(self) -> int:
        """
        Return total number of parameter combinations.

        This is computed via arithmetic on list lengths (fast, no enumeration).

        Note: We don't use __len__() because len() will raise an OverflowError if len(s) tries to return an integer greater than sys.maxsize,

        Returns:
            Total number of combinations
        """
        # Compute grouped size
        grouped_size = 1
        for group_combos in self._grouped.values():
            grouped_size *= len(group_combos)

        # Compute independent size
        independent_size = 1
        for values in self._independent.values():
            independent_size *= len(values)

        return grouped_size * independent_size

    def get_combination(self, index: int) -> dict[str, str]:
        """
        Get the nth parameter combination deterministically.

        Given an index, compute which combination it represents without enumerating all previous combinations.

        Args:
            index: Zero-based index into the parameter space

        Returns:
            Dictionary of parameter name -> value

        Raises:
            IndexError: If index is out of range
        """
        # len() raises OverflowError if size > sys.maxsize
        space_size = self.size()
        if index < 0 or index >= space_size:
            raise IndexError(
                f"Index {index} out of range for parameter space of size {space_size}"
            )

        # Strategy: Treat the index as a number in a mixed-radix number system
        # where each dimension has its own radix (size)

        result = {}

        # First, handle grouped variables
        # Convert grouped structure to flat list for indexing
        grouped_flat = []
        grouped_sizes = []
        for group_combos in self._grouped.values():
            grouped_flat.append(group_combos)
            grouped_sizes.append(len(group_combos))

        # Compute total grouped size
        grouped_total = 1
        for size in grouped_sizes:
            grouped_total *= size

        # Decompose index
        grouped_index = index % grouped_total
        independent_index = index // grouped_total

        # Extract grouped variable values
        remaining = grouped_index
        for group_combos in grouped_flat:
            group_size = len(group_combos)
            group_idx = remaining % group_size
            result.update(group_combos[group_idx])
            remaining //= group_size

        # Extract independent variable values
        remaining = independent_index
        for var_name, var_values in self._independent.items():
            value_idx = remaining % len(var_values)
            result[var_name] = var_values[value_idx]
            remaining //= len(var_values)

        # Apply derived variables
        for derived_name, derivation_func in self._derived.items():
            try:
                result[derived_name] = derivation_func(result)
            except Exception as e:
                raise ValueError(
                    f"Error computing derived variable '{derived_name}' at index {index}: {e}\n"
                    f"Parameters so far: {result}"
                )

        return result

    def __iter__(self) -> Iterator[dict[str, str]]:
        """
        Iterate through all parameter combinations (lazy).

        Yields:
            Parameter dictionaries in order
        """
        for i in range(self.size()):
            yield self.get_combination(i)

    def sample_uniformly_random(
        self, n: int, seed: int | None = None
    ) -> Iterator[dict[str, str]]:
        """
        Sample n random parameter combinations with uniform probability (no weighting).

        Works efficiently even for massive parameter spaces (e.g., 1e100 combinations)
        by generating random indices without materializing the full range.

        Args:
            n: Number of samples to generate
            seed: Random seed for reproducibility

        Yields:
            Random parameter dictionaries

        Example:
            for params in param_space.sample_uniformly_random(n=100, seed=42):
                task = create_task(params)
                evaluate(task)
        """
        rng = random.Random(seed)
        total_size = self.size()

        # For massive spaces, we can't use rng.sample() or rng.randrange() directly
        # Instead, generate random indices using randint on Python integers

        sampled_indices = []
        for _ in range(n):
            # Generate random integer in range [0, total_size)
            # Using uniform random bytes to generate arbitrary-precision random int
            idx = rng.randint(0, total_size - 1)
            sampled_indices.append(idx)

        for idx in sampled_indices:
            yield self.get_combination(idx)

    def sample_weighted(
        self, n: int, seed: int | None = None
    ) -> Iterator[dict[str, str]]:
        """
        Sample n combinations respecting variable weights.

        Uses direct weighted sampling on independent variables (not rejection sampling).
        This is efficient even when weights are very small.

        Works efficiently even for massive parameter spaces (e.g., 1e100 combinations).

        Both independent and grouped variables can be weighted. Specify weights
        when calling add_independent() or add_grouped().

        Args:
            n: Number of samples to generate
            seed: Random seed for reproducibility

        Yields:
            Weighted-sampled parameter dictionaries

        Example:
            params.add_independent('system_encouraging',
                                 ['independence', 'neutral', 'consultation'],
                                 weights={'independence': 1.0, 'neutral': 0.5, 'consultation': 0.5})

            # 'independence' will be sampled 2x more often than 'neutral' or 'consultation'
            for params in params.sample_weighted(n=1000, seed=42):
                task = create_task(params)
        """
        rng = random.Random(seed)

        # Pre-compute cumulative weights for each independent variable
        weighted_vars = {}
        for var_name, var_values in self._independent.items():
            if var_name in self._weights:
                weight_dict = self._weights[var_name]
                # Build cumulative distribution
                # Note: All values guaranteed to have weights due to validation in add_independent()
                weights = []
                cumsum = []
                total = 0.0
                for value in var_values:
                    w = weight_dict[value]  # No default - must exist (validated)
                    weights.append(w)
                    total += w
                    cumsum.append(total)

                weighted_vars[var_name] = {
                    "values": var_values,
                    "cumsum": cumsum,
                    "total": total,
                }
            else:
                # No weights specified - uniform
                weighted_vars[var_name] = None

        # Pre-compute cumulative weights for grouped variables
        grouped_info = []
        for group_name, group_combos in self._grouped.items():
            if group_name in self._grouped_weights:
                # Weighted sampling
                group_weights = self._grouped_weights[group_name]
                cumsum = []
                total = 0.0
                for w in group_weights:
                    total += w
                    cumsum.append(total)
                grouped_info.append(
                    {"combos": group_combos, "cumsum": cumsum, "total": total}
                )
            else:
                # Uniform sampling
                grouped_info.append(
                    {"combos": group_combos, "cumsum": None, "total": None}
                )

        # Generate n samples
        for _ in range(n):
            result = {}

            # Sample grouped variables (weighted or uniform)
            for info in grouped_info:
                if info["cumsum"] is not None:
                    # Weighted sampling
                    r = rng.random() * info["total"]
                    idx = 0
                    for i, cum_weight in enumerate(info["cumsum"]):
                        if r <= cum_weight:
                            idx = i
                            break
                    result.update(info["combos"][idx])
                else:
                    # Uniform sampling
                    group_idx = rng.randrange(len(info["combos"]))
                    result.update(info["combos"][group_idx])

            # Sample independent variables with weights
            for var_name, var_values in self._independent.items():
                if weighted_vars[var_name] is not None:
                    # Weighted sampling using cumulative distribution
                    info = weighted_vars[var_name]
                    r = rng.random() * info["total"]
                    # Binary search in cumsum
                    idx = 0
                    for i, cum_weight in enumerate(info["cumsum"]):
                        if r <= cum_weight:
                            idx = i
                            break
                    result[var_name] = info["values"][idx]
                else:
                    # Uniform sampling
                    result[var_name] = rng.choice(var_values)

            # Apply derived variables
            for derived_name, derivation_func in self._derived.items():
                try:
                    result[derived_name] = derivation_func(result)
                except Exception as e:
                    raise ValueError(
                        f"Error computing derived variable '{derived_name}' during weighted sampling: {e}\n"
                        f"Parameters so far: {result}"
                    )
            # Apply derived group variables
            for derived_name, derivation_func in self._derived_groups.items():
                try:
                    derived_group = derivation_func(result)
                    result.update(derived_group)
                except Exception as e:
                    raise ValueError(
                        f"Error computing derived variable '{derived_name}' during weighted sampling: {e}\n"
                        f"Parameters so far: {result}"
                    )
            yield result

    def get_all_variables(self) -> set[str]:
        """
        Get all variable names defined in this parameter space.

        Returns:
            Set of all variable names (independent, grouped, and derived)
        """
        variables = set(self._independent.keys())
        variables.update(self._derived.keys())

        # Extract variable names from grouped combinations
        for group_combos in self._grouped.values():
            for combo in group_combos:
                variables.update(combo.keys())

        return variables

    def get_variable_info(
        self, var_name: str
    ) -> dict[str, str | list[str] | Callable[[dict[str, str]], Any]]:
        """
        Get information about a specific variable.

        Args:
            var_name: Name of the variable

        Returns:
            Dictionary with variable information:
            - 'type': 'independent', 'grouped', or 'derived'
            - 'values': List of possible values (if applicable)
            - 'weights': Weight dict (if applicable)

        Raises:
            KeyError: If variable doesn't exist
        """
        if var_name in self._independent:
            info = {"type": "independent", "values": self._independent[var_name]}
            if var_name in self._weights:
                info["weights"] = self._weights[var_name]
            return info

        if var_name in self._derived:
            return {"type": "derived", "derivation": self._derived[var_name]}

        # Check grouped variables
        for group_name, group_combos in self._grouped.items():
            # Collect all possible values for this variable across combinations
            values = set()
            for combo in group_combos:
                if var_name in combo:
                    values.add(combo[var_name])

            if values:
                info = {
                    "type": "grouped",
                    "group_name": group_name,
                    "values": sorted(values),
                }
                # Add weights if this group has them
                if group_name in self._grouped_weights:
                    info["weights"] = self._grouped_weights[group_name]
                return info

        raise KeyError(f"Variable '{var_name}' not found in parameter space")

    def __repr__(self) -> str:
        """String representation showing size and variable counts."""
        n_independent = len(self._independent)

        # Compute grouped vars count efficiently
        n_grouped_vars = 0
        if self._grouped:
            # Collect all unique keys across all grouped combinations
            grouped_keys = set()
            for group_combos in self._grouped.values():
                for combo in group_combos:
                    grouped_keys.update(combo.keys())
            n_grouped_vars = len(grouped_keys)

        n_derived = len(self._derived)

        return (
            f"ParameterSpace(size={self.size()}, "
            f"independent={n_independent}, "
            f"grouped_vars={n_grouped_vars}, "
            f"derived={n_derived})"
        )
