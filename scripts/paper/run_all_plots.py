#!/usr/bin/env python3
"""Run all plot scripts with all their modes.

Usage:
    uv run scripts/paper/run_all_plots.py           # Run all plots
    uv run scripts/paper/run_all_plots.py --dry-run # Show what would run
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import fire

PLOTS_DIR = Path("scripts/paper/plots")

# All plot commands to run
# Each tuple is (script_name, [extra_args], description)
PLOT_COMMANDS: list[tuple[str, list[str], str]] = [
    ("plot_08_raw_counts.py", [], "Raw counts heatmap"),
    ("plot_12_scheming_predictions.py", [], "Directional agreement"),
    ("plot_16_rq2_quartile_trends.py", [], "RQ2 quartile trends"),
    ("plot_17_pooled_coefficients.py", [], "Pooled coefficients (quartile)"),
    ("plot_20_per_model_coefficients.py", [], "Per-model coefficients (grid)"),
    (
        "plot_20_per_model_coefficients.py",
        ["--all-params"],
        "Per-model coefficients (individual)",
    ),
    ("plot_21_rq1_by_model_pooled.py", [], "RQ1 by model"),
    ("plot_21_rq1_by_model_pooled.py", ["--violin"], "RQ1 by model (violin)"),
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--compare-baselines"],
        "RQ1 baseline comparison",
    ),
    ("plot_22_rq1_by_variation_pooled.py", [], "RQ1 by variation"),
    ("plot_24_per_variation_coefficients.py", [], "Per-variation coefficients"),
    (
        "plot_24_per_variation_coefficients.py",
        ["--split"],
        "Per-variation coefficients (split)",
    ),
    (
        "plot_24_per_variation_coefficients.py",
        ["--good-only"],
        "Per-variation coefficients (good only)",
    ),
    ("plot_25_goal_coefficients.py", [], "Goal coefficients"),
    ("plot_27_entropy_explained.py", [], "Entropy explained"),
    ("plot_27_entropy_explained.py", ["--compare"], "Entropy explained (comparison)"),
    # Filtered variant (exclude unreliable models)
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--exclude-flagged"],
        "RQ1 by model (filtered)",
    ),
    # Less ambiguous variants
    (
        "plot_16_rq2_quartile_trends.py",
        ["--unambiguous"],
        "RQ2 quartile trends (less ambiguous)",
    ),
    (
        "plot_17_pooled_coefficients.py",
        ["--unambiguous"],
        "Pooled coefficients (quartile, less ambiguous)",
    ),
    (
        "plot_17_pooled_coefficients.py",
        ["--compare-unambiguous"],
        "Pooled coefficients (all vs less ambiguous comparison)",
    ),
    (
        "plot_20_per_model_coefficients.py",
        ["--unambiguous"],
        "Per-model coefficients (less ambiguous)",
    ),
    (
        "plot_20_per_model_coefficients.py",
        ["--all-params", "--unambiguous"],
        "Per-model coefficients (individual, less ambiguous)",
    ),
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--unambiguous"],
        "RQ1 by model (less ambiguous)",
    ),
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--unambiguous", "--exclude-flagged"],
        "RQ1 by model (less ambiguous, filtered)",
    ),
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--compare-unambiguous"],
        "RQ1 by model (all vs less ambiguous comparison)",
    ),
    (
        "plot_21_rq1_by_model_pooled.py",
        ["--compare-waic"],
        "RQ1 by model (WAIC comparison)",
    ),
    (
        "plot_12_scheming_predictions.py",
        ["--unambiguous"],
        "Directional agreement (less ambiguous)",
    ),
    (
        "plot_12_scheming_predictions.py",
        ["--compare-unambiguous"],
        "Directional agreement (all vs less ambiguous comparison)",
    ),
    ("plot_16b_rq2_avg_importance.py", [], "RQ2 quartile trends (avg importance)"),
    ("plot_26_extra_coefficients.py", [], "Extra coefficients (all environments)"),
    (
        "plot_26_extra_coefficients.py",
        ["--combined"],
        "Extra coefficients (combined figure)",
    ),
    ("plot_28_eci_vs_rq1.py", [], "ECI vs RQ1 scatter"),
    (
        "plot_28_eci_vs_rq1.py",
        ["--unambiguous"],
        "ECI vs RQ1 scatter (less ambiguous)",
    ),
    ("plot_29_eval_awareness_coefficients.py", [], "Eval awareness coefficients"),
    ("plot_30_eval_awareness_heatmap.py", [], "Eval awareness heatmap"),
]


def run_plot(
    script: str, args: list[str], description: str, dry_run: bool = False
) -> bool:
    """Run a single plot command."""
    script_path = PLOTS_DIR / script
    if not script_path.exists():
        print(f"  WARNING: Script not found: {script_path}")
        return False

    cmd = ["uv", "run", str(script_path)] + args
    cmd_str = " ".join(cmd)

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {description}")
    print(f"  {cmd_str}")

    if dry_run:
        print("  (dry run - skipping)")
        return True

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"  Done ({elapsed:.1f}s)")
        return True
    else:
        print(f"  FAILED ({elapsed:.1f}s)")
        if result.stderr:
            # Show last few lines of error
            error_lines = result.stderr.strip().split("\n")[-5:]
            for line in error_lines:
                print(f"    {line}")
        return False


def main(dry_run: bool = False):
    """Run all plot scripts with all modes.

    Args:
        dry_run: Show what would run without executing
    """
    print("=" * 60)
    print("RUNNING ALL PLOTS")
    print("=" * 60)

    if dry_run:
        print("DRY RUN MODE\n")

    successes = 0
    failures = []

    for script, args, description in PLOT_COMMANDS:
        ok = run_plot(script, args, description, dry_run)
        if ok:
            successes += 1
        else:
            failures.append(f"{script} {' '.join(args)}".strip())

    print("\n" + "=" * 60)
    print(f"COMPLETE: {successes} succeeded, {len(failures)} failed")
    print("=" * 60)

    if failures:
        print("\nFailed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nPlots saved to paper_cache/figures/")
    return 0


if __name__ == "__main__":
    sys.exit(fire.Fire(main))
