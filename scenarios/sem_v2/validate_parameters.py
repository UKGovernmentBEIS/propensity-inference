#!/usr/bin/env python3
"""
Validate parameter usage in SEM v2 scenario.

This script demonstrates how to use the TemplateEngine tracking functionality
to verify that all parameters defined in the parameter space are actually used
in templates.

Usage:
    python validate_parameters.py [--suite SUITE_NAME] [--samples N]

Example:
    python validate_parameters.py --suite classification_none --samples 5
"""

import argparse
import random
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.parameter_space import ParameterSpace
from scenarios.sem_v2.lib.content_assembler import SEMContentAssembler
from scenarios.sem_v2.parameter_spaces import SUITES


def validate_suite(
    suite_name: str, space: ParameterSpace, num_samples: int = 5
) -> dict[str, str | set[str] | int]:
    """
    Validate parameter usage for a suite.

    Args:
        suite_name: Name of the suite (for display)
        space: ParameterSpace object
        num_samples: Number of random samples to test

    Returns:
        Dict with validation results
    """
    print(f"\n{'=' * 70}")
    print(f"Validating suite: {suite_name}")
    print(f"{'=' * 70}")
    print(f"Parameter space size: {space.size()}")
    print(f"Testing {num_samples} random samples...")

    assembler = SEMContentAssembler()

    # Track which parameters are used across all samples
    all_used = set()
    all_unused = set()

    # Sample random combinations
    sample_indices = random.sample(range(space.size()), min(num_samples, space.size()))

    for i, idx in enumerate(sample_indices, 1):
        params = space.get_combination(idx)

        print(f"\n  Sample {i}/{num_samples} (index {idx}):")
        print(f"    Parameters: goal={params['goal']}, model={params['model']}")

        # Assemble with tracking
        result = assembler.assemble(params)

        # Get usage info
        usage_info = result["usage_info"]
        accessed = usage_info["accessed_variables"]

        # Validate against parameter space
        all_defined = space.get_all_variables()
        unused = all_defined - accessed

        # Track across samples
        all_used.update(accessed)
        all_unused &= unused  # Only keep params unused in ALL samples

        print(f"    Variables accessed: {len(accessed)}")
        print(f"    Variables defined: {len(all_defined)}")
        print(f"    Unused in this sample: {len(unused)}")

        if unused:
            # Show first few unused (if many)
            unused_list = sorted(unused)
            if len(unused_list) > 5:
                print(f"      Examples: {', '.join(unused_list[:5])}...")
            else:
                print(f"      {', '.join(unused_list)}")

    # Compute parameters that were never used in any sample
    all_defined = space.get_all_variables()
    never_used = all_defined - all_used

    print(f"\n  {'=' * 66}")
    print("  Summary:")
    print(f"    Total parameters defined: {len(all_defined)}")
    print(f"    Parameters used at least once: {len(all_used)}")
    print(f"    Parameters NEVER used: {len(never_used)}")

    if never_used:
        print("\n  ⚠️  WARNING: Parameters never used in any sample:")
        for param in sorted(never_used):
            print(f"      - {param}")

    return {
        "suite_name": suite_name,
        "all_defined": all_defined,
        "all_used": all_used,
        "never_used": never_used,
        "samples_tested": len(sample_indices),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate parameter usage in SEM v2 scenario"
    )
    parser.add_argument(
        "--suite",
        choices=list(SUITES.keys()) + ["all"],
        default="all",
        help="Which suite to validate (default: all)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Number of random samples to test per suite (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()

    # Set random seed for reproducibility
    random.seed(args.seed)

    # Select which suites to validate
    if args.suite == "all":
        suites_to_validate = SUITES
    else:
        suites_to_validate = {args.suite: SUITES[args.suite]}

    print("\n" + "=" * 70)
    print("SEM v2 Parameter Usage Validation")
    print("=" * 70)
    print(f"Random seed: {args.seed}")
    print(f"Samples per suite: {args.samples}")

    # Validate each suite
    results = []
    for suite_name, suite_func in suites_to_validate.items():
        space = suite_func()
        result = validate_suite(suite_name, space, args.samples)
        results.append(result)

    # Final summary
    print(f"\n\n{'=' * 70}")
    print("OVERALL SUMMARY")
    print(f"{'=' * 70}")

    total_never_used = sum(len(r["never_used"]) for r in results)

    if total_never_used == 0:
        print("✅ SUCCESS: All parameters are used across tested samples!")
    else:
        print(f"⚠️  WARNING: {total_never_used} total parameters never used")
        print("\nConsider:")
        print("  1. Are these parameters meant to be used conditionally?")
        print("  2. Should they be removed from the parameter space?")
        print("  3. Are they used in templates that weren't loaded?")
        print("  4. Increase --samples to test more combinations")

    print(f"\nValidated {len(results)} suite(s) with {args.samples} samples each.")
    print("=" * 70)


if __name__ == "__main__":
    main()
