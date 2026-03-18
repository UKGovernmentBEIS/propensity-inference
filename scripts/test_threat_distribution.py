#!/usr/bin/env python3
"""
Test script to verify threat parameter distribution across all scenarios.

For each scenario, samples from the parameter space and reports the distribution
of the derived 'threat' parameter (none, replacement, other).

Target distribution: replacement:other:none ≈ 2:1:1

Uses WEIGHTED sampling (sample_weighted) to reflect actual evaluation distribution.
"""

from collections import Counter
from typing import Any

# Number of samples per suite for distribution estimation
NUM_SAMPLES = 10000


def sample_threat_distribution(space, num_samples: int = NUM_SAMPLES) -> Counter[str]:
    """Sample from a parameter space using weighted sampling and count threat values."""
    counter: Counter[str] = Counter()

    # Use weighted sampling to reflect actual evaluation distribution
    for params in space.sample_weighted(n=num_samples, seed=42):
        threat = params.get("threat", "MISSING")
        counter[threat] += 1

    return counter


def print_distribution(name: str, counter: Counter[str], indent: str = "") -> None:
    """Print distribution statistics."""
    total = sum(counter.values())
    if total == 0:
        print(f"{indent}{name}: No samples")
        return

    # Calculate proportions
    replacement = counter.get("replacement", 0)
    other = counter.get("other", 0)
    none = counter.get("none", 0)

    # Calculate ratio relative to 'none' (or smallest non-zero)
    base = none if none > 0 else min(v for v in [replacement, other, none] if v > 0)
    if base > 0:
        ratio_str = f"{replacement / base:.1f}:{other / base:.1f}:{none / base:.1f}"
    else:
        ratio_str = "N/A"

    print(f"{indent}{name}:")
    print(f"{indent}  replacement: {replacement / total:6.1%} ({replacement:,})")
    print(f"{indent}  other:       {other / total:6.1%} ({other:,})")
    print(f"{indent}  none:        {none / total:6.1%} ({none:,})")
    print(f"{indent}  ratio:       {ratio_str}")


def _analyze_scenario_with_suites(scenario_name: str, suites: dict[str, Any]) -> None:
    """Analyze a scenario with flat suite structure."""
    print(f"\n{'=' * 60}")
    print(f"{scenario_name.upper()}")
    print("=" * 60)

    combined = Counter()
    for suite_name, suite_func in suites.items():
        space = suite_func()
        counter = sample_threat_distribution(space)
        combined.update(counter)
        print_distribution(suite_name, counter, indent="  ")

    if len(suites) > 1:
        print()
        print_distribution("COMBINED (unweighted)", combined, indent="  ")


def _analyze_scenario_with_variations(
    scenario_name: str, variations: dict[str, Any]
) -> None:
    """Analyze a scenario with variation structure."""
    print(f"\n{'=' * 60}")
    print(f"{scenario_name.upper()}")
    print("=" * 60)

    for var_name, variation in variations.items():
        print(f"\n  Variation: {var_name}")
        print("  " + "-" * 40)

        # Collect per-suite distributions and weights
        suite_counters = {}
        suite_weights = getattr(variation, "suite_weights", None)

        for suite_name, suite_func in variation.suites.items():
            space = suite_func()
            counter = sample_threat_distribution(space)
            suite_counters[suite_name] = counter
            print_distribution(suite_name, counter, indent="    ")

        if len(variation.suites) > 1:
            # Calculate weighted combination using suite_weights
            if suite_weights:
                print(f"\n    Suite weights: {suite_weights}")
                total_weight = sum(suite_weights.values())
                weighted_counter: Counter[str] = Counter()
                for suite_name, counter in suite_counters.items():
                    weight = suite_weights.get(suite_name, 1.0) / total_weight
                    suite_total = sum(counter.values())
                    for threat_val, count in counter.items():
                        # Scale by weight and normalize
                        weighted_counter[threat_val] += int(
                            (count / suite_total) * weight * NUM_SAMPLES
                        )
                print()
                print_distribution(
                    "WEIGHTED variation", weighted_counter, indent="    "
                )
            else:
                # No weights, use unweighted combination
                var_combined: Counter[str] = Counter()
                for counter in suite_counters.values():
                    var_combined.update(counter)
                print()
                print_distribution(
                    "variation combined (unweighted)", var_combined, indent="    "
                )


def main():
    print("Threat Distribution Test")
    print(f"Samples per suite: {NUM_SAMPLES:,}")
    print("Target distribution: replacement:other:none ≈ 2:1:1")

    # =========================================================================
    # HRH - single variation with default suite
    # =========================================================================
    from scenarios.hiding_reward_hacking.parameter_spaces import (
        VARIATIONS as HRH_VARIATIONS,
    )

    _analyze_scenario_with_variations("hiding_reward_hacking", HRH_VARIATIONS)

    # =========================================================================
    # PP - 3 variations, each with single suite
    # =========================================================================
    from scenarios.power_preservation.parameter_spaces import (
        VARIATIONS as PP_VARIATIONS,
    )

    _analyze_scenario_with_variations("power_preservation", PP_VARIATIONS)

    # =========================================================================
    # ESF - single variation with single suite (consolidated)
    # =========================================================================
    from scenarios.email_spam_filter_v2.parameter_spaces import (
        VARIATIONS as ESF_VARIATIONS,
    )

    _analyze_scenario_with_variations("email_spam_filter_v2", ESF_VARIATIONS)

    # =========================================================================
    # SEM - 2 variations, each with 2 suites
    # =========================================================================
    from scenarios.sem_v2.parameter_spaces import VARIATIONS as SEM_VARIATIONS

    _analyze_scenario_with_variations("sem_v2", SEM_VARIATIONS)

    # =========================================================================
    # AM - 3 variations, each with 2 suites
    # =========================================================================
    from scenarios.agentic_misalignment_v2.parameter_spaces import (
        VARIATIONS as AM_VARIATIONS,
    )

    _analyze_scenario_with_variations("agentic_misalignment_v2", AM_VARIATIONS)

    # =========================================================================
    # GPU - single variation with default suite
    # =========================================================================
    from scenarios.gpu_decision_email_assistant.parameter_spaces import (
        VARIATIONS as GPU_VARIATIONS,
    )

    _analyze_scenario_with_variations("gpu_decision_email_assistant", GPU_VARIATIONS)

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
