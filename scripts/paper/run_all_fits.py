#!/usr/bin/env python3
"""Run all posterior fits sequentially and regenerate plots after each.

This script runs all 8 fitting commands in sequence, regenerating the
relevant plots after each fit completes. Designed for running on a VM
with ~32 cores.

Usage:
    uv run scripts/paper/run_all_fits.py              # Run everything (full quality)
    uv run scripts/paper/run_all_fits.py --fast       # Run with --fast MCMC (quick test)
    uv run scripts/paper/run_all_fits.py --dry-run    # Show what would run
    uv run scripts/paper/run_all_fits.py --skip-to 3  # Skip first 2 fits, start at fit 3

    # Save current plots as "_old" for comparison before re-running
    uv run scripts/paper/run_all_fits.py save-old

    # Compare old vs new plots (opens file browser or lists diffs)
    uv run scripts/paper/run_all_fits.py compare

The fits and their dependent plots:

    1. --all-models         -> plot_20, plot_21
    2. --all-variations     -> plot_22, plot_24
    3. --all-quartiles      -> plot_16, plot_17
    4. --all-singles        -> plot_12, plot_21 (re-run), plot_27
    5. --all-combined       -> (no plots)
    6. --all-models --goal  -> plot_25
    7. --all-models --unambiguous     -> plot_20 --unambiguous, plot_21 --unambiguous
    8. --all-quartiles --unambiguous  -> plot_16 --unambiguous, plot_17 --unambiguous
"""

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fire

FIGURES_DIR = Path("paper_cache/figures")


@dataclass
class FitStep:
    """A fitting step with its dependent plots."""

    name: str
    fit_args: list[str]
    workers: int
    plots: list[str | tuple[str, list[str]]]  # Script name, or (name, extra_args)


# All fitting steps in order
STEPS: list[FitStep] = [
    FitStep(
        name="1. Per-model (23 fits)",
        fit_args=["--all-models"],
        workers=8,
        plots=["plot_20_per_model_coefficients.py", "plot_21_rq1_by_model_pooled.py"],
    ),
    FitStep(
        name="2. Per-variation (11 fits)",
        fit_args=["--all-variations"],
        workers=8,
        plots=[
            "plot_22_rq1_by_variation_pooled.py",
            "plot_24_per_variation_coefficients.py",
        ],
    ),
    FitStep(
        name="3. Per-quartile (4 fits)",
        fit_args=["--all-quartiles"],
        workers=4,
        plots=["plot_16_rq2_quartile_trends.py", "plot_17_pooled_coefficients.py"],
    ),
    FitStep(
        name="4. All singles (253 fits)",
        fit_args=["--all-singles"],
        workers=8,
        plots=[
            "plot_12_scheming_predictions.py",
            "plot_21_rq1_by_model_pooled.py",  # Re-run with single fits available
            "plot_27_entropy_explained.py",
        ],
    ),
    FitStep(
        name="5. All-combined (1 giant fit)",
        fit_args=["--all-combined"],
        workers=1,
        plots=[],  # No plots depend directly on all-combined
    ),
    FitStep(
        name="6. Per-model with goal (23 fits)",
        fit_args=["--all-models", "--goal"],
        workers=8,
        plots=["plot_25_goal_coefficients.py"],
    ),
    FitStep(
        name="7. Per-model unambiguous (23 fits)",
        fit_args=["--all-models", "--unambiguous"],
        workers=8,
        plots=[
            ("plot_20_per_model_coefficients.py", ["--unambiguous"]),
            ("plot_21_rq1_by_model_pooled.py", ["--unambiguous"]),
        ],
    ),
    FitStep(
        name="8. Per-quartile unambiguous (4 fits)",
        fit_args=["--all-quartiles", "--unambiguous"],
        workers=4,
        plots=[
            ("plot_16_rq2_quartile_trends.py", ["--unambiguous"]),
            ("plot_17_pooled_coefficients.py", ["--unambiguous"]),
        ],
    ),
]

PLOTS_DIR = Path("scripts/paper/plots")


def run_command(cmd: list[str], description: str, dry_run: bool = False) -> bool:
    """Run a command and return success status."""
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    if dry_run:
        print("(dry run - skipping)")
        return True

    start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"Completed in {elapsed / 60:.1f} minutes")
        return True
    else:
        print(f"FAILED with return code {result.returncode}")
        return False


def run_fit(step: FitStep, dry_run: bool = False, fast: bool = False) -> bool:
    """Run a fitting step."""
    cmd = [
        "uv",
        "run",
        "scripts/paper/run_pooled_fits.py",
        "fit",
        *step.fit_args,
        "--workers",
        str(step.workers),
        "--delete-everything",
    ]
    if fast:
        cmd.append("--fast")
    return run_command(cmd, f"FIT: {step.name}", dry_run)


def run_plot(
    plot_name: str, extra_args: list[str] | None = None, dry_run: bool = False
) -> bool:
    """Run a plot script with optional extra arguments."""
    plot_path = PLOTS_DIR / plot_name
    if not plot_path.exists():
        print(f"WARNING: Plot script not found: {plot_path}")
        return False

    cmd = ["uv", "run", str(plot_path)]
    if extra_args:
        cmd.extend(extra_args)
    description = f"PLOT: {plot_name}"
    if extra_args:
        description += f" {' '.join(extra_args)}"
    return run_command(cmd, description, dry_run)


def main(
    dry_run: bool = False,
    skip_to: int = 1,
    fits_only: bool = False,
    plots_only: bool = False,
    fast: bool = False,
):
    """Run all posterior fits and regenerate plots.

    Args:
        dry_run: Show what would run without executing
        skip_to: Skip to this step number (1-indexed, default 1 = start from beginning)
        fits_only: Only run fits, skip plots
        plots_only: Only run plots (assumes fits already done)
        fast: Use --fast MCMC (500 samples, 2 chains) for quick testing
    """
    print("\n" + "=" * 60)
    print("FINAL POSTERIOR FITTING PIPELINE")
    print("=" * 60)

    if dry_run:
        print("DRY RUN MODE - no commands will be executed\n")
    if fast:
        print("FAST MODE - using reduced MCMC (500 samples, 2 chains)\n")

    # Also run plot_08 at the start (doesn't need posteriors)
    if not fits_only and skip_to <= 1:
        print("\n--- Running plot_08 (raw counts, no posteriors needed) ---")
        run_plot("plot_08_raw_counts.py", dry_run)

    total_steps = len(STEPS)
    failed_steps: list[str] = []

    for i, step in enumerate(STEPS, start=1):
        if i < skip_to:
            print(f"\nSkipping step {i}: {step.name}")
            continue

        print(f"\n{'#' * 60}")
        print(f"# STEP {i}/{total_steps}: {step.name}")
        print(f"{'#' * 60}")

        # Run fit
        if not plots_only:
            fit_ok = run_fit(step, dry_run, fast=fast)
            if not fit_ok:
                failed_steps.append(f"FIT: {step.name}")
                print(f"\nFit failed for {step.name}, skipping its plots")
                continue

        # Run dependent plots
        if not fits_only and step.plots:
            print(f"\n--- Running {len(step.plots)} dependent plot(s) ---")
            for plot_entry in step.plots:
                if isinstance(plot_entry, tuple):
                    plot_name, plot_args = plot_entry
                else:
                    plot_name, plot_args = plot_entry, []
                plot_ok = run_plot(plot_name, plot_args or None, dry_run)
                if not plot_ok:
                    failed_steps.append(f"PLOT: {plot_name}")

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    if failed_steps:
        print(f"\nFailed steps ({len(failed_steps)}):")
        for step in failed_steps:
            print(f"  - {step}")
        return 1
    else:
        print("\nAll steps completed successfully!")
        print("\nNext: Upload posteriors to S3 (if configured):")
        print(
            "  aws s3 sync paper_cache/posteriors/ "
            "s3://$S3_BUCKET/$PROPENSITY_S3_ROOT/paper_cache/posteriors/"
        )
        return 0


def save_old():
    """Save current plots with '_old' suffix for later comparison.

    Copies all PDFs in paper_cache/figures/ to *_old.pdf versions.
    Run this BEFORE re-running fits to preserve the old plots.
    """
    if not FIGURES_DIR.exists():
        print(f"No figures directory found at {FIGURES_DIR}")
        return 1

    pdfs = list(FIGURES_DIR.glob("*.pdf"))
    # Exclude already-old files
    pdfs = [p for p in pdfs if not p.stem.endswith("_old")]

    if not pdfs:
        print("No PDF files found to save")
        return 1

    print(f"Saving {len(pdfs)} plots with '_old' suffix...")
    for pdf in pdfs:
        old_path = pdf.with_stem(pdf.stem + "_old")
        shutil.copy2(pdf, old_path)
        print(f"  {pdf.name} -> {old_path.name}")

    print(f"\nSaved {len(pdfs)} old versions to {FIGURES_DIR}")
    return 0


def compare():
    """List old vs new plot pairs for comparison.

    Shows which plots have both old and new versions available.
    """
    if not FIGURES_DIR.exists():
        print(f"No figures directory found at {FIGURES_DIR}")
        return 1

    # Find all _old.pdf files
    old_pdfs = list(FIGURES_DIR.glob("*_old.pdf"))

    if not old_pdfs:
        print("No '_old' plots found. Run 'save-old' first before regenerating plots.")
        return 1

    print(f"Found {len(old_pdfs)} plot pairs to compare:\n")

    pairs = []
    for old_pdf in sorted(old_pdfs):
        new_name = old_pdf.stem.replace("_old", "") + ".pdf"
        new_pdf = FIGURES_DIR / new_name

        if new_pdf.exists():
            # Get file sizes for quick comparison
            old_size = old_pdf.stat().st_size
            new_size = new_pdf.stat().st_size
            size_diff = new_size - old_size
            size_pct = (size_diff / old_size * 100) if old_size > 0 else 0

            status = "SAME" if abs(size_pct) < 1 else f"{size_pct:+.1f}%"
            print(f"  {new_name:45} {status:>10}")
            pairs.append((old_pdf, new_pdf))
        else:
            print(f"  {new_name:45} {'NEW MISSING':>10}")

    print(f"\n{len(pairs)} pairs ready for comparison in {FIGURES_DIR}")
    print("\nTo visually compare, open the folder and view side-by-side:")
    print(f"  open {FIGURES_DIR}  # macOS")
    print(f"  xdg-open {FIGURES_DIR}  # Linux")

    return 0


def clean_old():
    """Remove all '_old' plot files."""
    if not FIGURES_DIR.exists():
        print(f"No figures directory found at {FIGURES_DIR}")
        return 1

    old_pdfs = list(FIGURES_DIR.glob("*_old.pdf"))

    if not old_pdfs:
        print("No '_old' plots found to clean")
        return 0

    print(f"Removing {len(old_pdfs)} old plots...")
    for pdf in old_pdfs:
        pdf.unlink()
        print(f"  Deleted: {pdf.name}")

    print(f"\nCleaned {len(old_pdfs)} old files")
    return 0


class CLI:
    """Pipeline for running all posterior fits and managing plot comparisons."""

    def run(
        self,
        dry_run: bool = False,
        skip_to: int = 1,
        fits_only: bool = False,
        plots_only: bool = False,
        fast: bool = False,
    ):
        """Run all posterior fits and regenerate plots.

        Args:
            dry_run: Show what would run without executing
            skip_to: Skip to this step number (1-indexed)
            fits_only: Only run fits, skip plots
            plots_only: Only run plots (assumes fits done)
            fast: Use --fast MCMC (500 samples, 2 chains) for quick testing
        """
        return main(
            dry_run=dry_run,
            skip_to=skip_to,
            fits_only=fits_only,
            plots_only=plots_only,
            fast=fast,
        )

    def save_old(self):
        """Save current plots with '_old' suffix for comparison."""
        return save_old()

    def compare(self):
        """List old vs new plot pairs for comparison."""
        return compare()

    def clean_old(self):
        """Remove all '_old' plot files."""
        return clean_old()


if __name__ == "__main__":
    # Support both `run_all_fits.py` (runs main) and `run_all_fits.py run/save-old/compare`
    if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
        # No subcommand or just flags -> run main
        sys.exit(fire.Fire(main))
    else:
        # Subcommand provided
        sys.exit(fire.Fire(CLI))
