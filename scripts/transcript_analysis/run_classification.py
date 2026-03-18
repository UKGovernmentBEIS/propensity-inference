#!/usr/bin/env python
"""Main CLI for running eval awareness classification at scale.

Usage:
    # Estimate cost
    uv run scripts/transcript_analysis/run_classification.py estimate

    # Run classification (samples uniformly from remaining work)
    uv run scripts/transcript_analysis/run_classification.py run --num-samples 100

    # Dry run to see what would be processed
    uv run scripts/transcript_analysis/run_classification.py run --num-samples 100 --dry-run

    # View progress against targets
    uv run scripts/transcript_analysis/run_classification.py progress

    # View summary of results
    uv run scripts/transcript_analysis/run_classification.py summary
"""

import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import fire
import pandas as pd

from scripts.transcript_analysis.config import (
    DEFAULT_CLASSIFIER_MODEL,
    DEFAULT_MAX_TRANSCRIPTS,
    DEFAULT_SCANS_DIR,
    PAPER_CACHE_SAMPLES,
    S3_EVAL_AWARENESS_LISTING,
    S3_LOGS_BASE,
    TARGETS_PATH,
    load_completed_classifications,
    load_targets,
)
from scripts.transcript_analysis.cost_estimator import print_estimate

# Scanner path for CLI invocation
SCANNER_PATH = "scripts/transcript_analysis/scanners/eval_awareness.py"


def discover_parquet_files(samples_dir: Path = PAPER_CACHE_SAMPLES) -> list[Path]:
    """Find all parquet sample files in the paper cache."""
    return sorted(samples_dir.rglob("samples_*.parquet"))


def load_available_transcripts(
    samples_dir: Path = PAPER_CACHE_SAMPLES,
) -> pd.DataFrame:
    """Load metadata for all available transcripts from parquet files.

    Returns:
        DataFrame with columns: meta_eval_file, meta_model, meta_scenario, meta_variation
    """
    parquet_files = discover_parquet_files(samples_dir)
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {samples_dir}")

    dfs = []
    for pf in parquet_files:
        df = pd.read_parquet(
            pf,
            columns=[
                "meta_eval_file",
                "meta_model",
                "meta_scenario",
                "meta_variation",
            ],
        )
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)

    # Deduplicate by eval file (each transcript should appear once)
    return combined.drop_duplicates(subset=["meta_eval_file"])


def build_remaining_pool(
    targets: dict[str, dict[str, int]],
    completed: dict[str, dict[str, set[str]]],
    available: pd.DataFrame,
) -> list[tuple[str, str, str]]:
    """Build pool of remaining transcripts to classify.

    For each (model, variation) pair in targets, find transcripts that:
    1. Match that model and variation in the available pool
    2. Haven't been classified yet
    3. Only include up to (target - completed) transcripts per (model, variation)

    Returns:
        List of (eval_path, model, variation) tuples for remaining work
    """
    remaining_pool: list[tuple[str, str, str]] = []

    for model, variations in targets.items():
        for variation, target in variations.items():
            if target == 0:
                continue

            completed_paths = completed.get(model, {}).get(variation, set())
            completed_count = len(completed_paths)

            needed = target - completed_count
            if needed <= 0:
                continue

            scenario, var_name = variation.split("/")
            mask = (
                (available["meta_model"] == model)
                & (available["meta_scenario"] == scenario)
                & (available["meta_variation"] == var_name)
            )

            matching = available[mask]

            unclassified = [
                str(row["meta_eval_file"])
                for _, row in matching.iterrows()
                if str(row["meta_eval_file"]) not in completed_paths
            ]
            random.shuffle(unclassified)

            for eval_path in unclassified[:needed]:
                remaining_pool.append((eval_path, model, variation))

    return remaining_pool


def print_progress_summary(
    targets: dict[str, dict[str, int]],
    completed: dict[str, dict[str, set[str]]],
) -> None:
    """Print progress summary against targets."""
    print("=" * 70)
    print("PROGRESS SUMMARY")
    print("=" * 70)
    print(f"{'Model':<45} {'Variation':<45} {'Done':>6} {'Target':>6}")
    print("-" * 70)

    total_done = 0
    total_target = 0

    for model, variations in sorted(targets.items()):
        short_model = model.split("/")[-1][:43]
        for variation, target in sorted(variations.items()):
            if target == 0:
                continue

            done = len(completed.get(model, {}).get(variation, set()))
            total_done += done
            total_target += target

            status = "OK" if done >= target else ""
            print(f"{short_model:<45} {variation:<25} {done:>6} {target:>6} {status}")

    print("-" * 70)
    pct = 100 * total_done / total_target if total_target > 0 else 0
    print(f"{'TOTAL':<45} {'':<25} {total_done:>6} {total_target:>6} ({pct:.1f}%)")
    print("=" * 70)


class EvalAwarenessClassifier:
    """CLI for running eval awareness classification at scale."""

    def estimate(self) -> None:
        """Estimate the cost of running classification."""
        print_estimate()

    def run(
        self,
        num_samples: int = 100,
        scans_dir: str = str(DEFAULT_SCANS_DIR),
        classifier_model: str = DEFAULT_CLASSIFIER_MODEL,
        max_transcripts: int = DEFAULT_MAX_TRANSCRIPTS,
        max_connections: int | None = None,
        max_processes: int | None = None,
        seed: int | None = None,
        dry_run: bool = False,
        display: str = "log",
    ) -> None:
        """Run classification on transcripts, sampling uniformly from remaining work.

        Args:
            num_samples: Number of transcripts to classify in this batch
            scans_dir: Directory to store scan results
            classifier_model: Model to use for classification
            max_transcripts: Max concurrent transcripts to process
            max_connections: Max concurrent API connections (defaults to max_transcripts)
            max_processes: Number of worker processes (defaults to scout's default of 4)
            seed: Random seed for reproducibility (default: random)
            dry_run: Print what would be done without executing
            display: Display type (rich, plain, log, none)
        """
        if seed is None:
            seed = random.randint(0, (1 << 64) - 1)

        print(f"Loading targets from: {TARGETS_PATH}")
        targets = load_targets()

        print("Loading completed classifications...")
        completed = load_completed_classifications()

        print("Loading available transcripts from parquet metadata...")
        available = load_available_transcripts()
        print(f"  Found {len(available):,} unique transcripts")

        print("\nBuilding remaining work pool...")
        remaining_pool = build_remaining_pool(targets, completed, available)
        print(f"  {len(remaining_pool):,} transcripts remaining to classify")

        if not remaining_pool:
            print("\nAll targets met! Nothing to classify.")
            return

        rng = random.Random(seed)
        sample_size = min(num_samples, len(remaining_pool))
        sampled = rng.sample(remaining_pool, sample_size)

        print(f"\nSampled {sample_size} transcripts (seed={seed})")

        by_model: dict[str, int] = defaultdict(int)
        by_variation: dict[str, int] = defaultdict(int)
        for _, m, v in sampled:
            by_model[m] += 1
            by_variation[v] += 1

        print("\nSample distribution by model:")
        for m, count in sorted(by_model.items(), key=lambda x: -x[1]):
            print(f"  {m.split('/')[-1]}: {count}")

        print("\nSample distribution by variation:")
        for v, count in sorted(by_variation.items(), key=lambda x: -x[1]):
            print(f"  {v}: {count}")

        if dry_run:
            print("\n[Dry run] Would classify the following transcripts:")
            for eval_path, m, v in sampled[:10]:
                print(f"  {eval_path}")
            if len(sampled) > 10:
                print(f"  ... and {len(sampled) - 10} more")
            return

        eval_paths = [str(S3_LOGS_BASE / eval_path) for eval_path, _, _ in sampled]

        print(f"\nProcessing {len(eval_paths)} transcripts...")

        # Build base command (without -T paths)
        base_cmd = [
            "uv",
            "run",
            "scout",
            "scan",
            SCANNER_PATH,
            "--model",
            classifier_model,
            "--scans",
            scans_dir,
            "--max-transcripts",
            str(max_transcripts),
            "--display",
            display,
        ]

        if max_connections is not None:
            base_cmd.extend(["--max-connections", str(max_connections)])
        if max_processes is not None:
            base_cmd.extend(["--max-processes", str(max_processes)])

        # Record existing scan dirs so we can find new ones after all batches
        scans_path = Path(scans_dir)
        scans_path.mkdir(parents=True, exist_ok=True)
        existing_scan_dirs = set(scans_path.iterdir())

        # Split into batches to avoid ARG_MAX limits (~2MB on Linux).
        # Each path is ~200 chars, so 250 paths ≈ 50KB — well within limits.
        batch_size = 250
        batches = [
            eval_paths[i : i + batch_size]
            for i in range(0, len(eval_paths), batch_size)
        ]
        n_batches = len(batches)

        exit_code = 0
        for batch_idx, batch_paths in enumerate(batches):
            if n_batches > 1:
                print(
                    f"\n--- Batch {batch_idx + 1}/{n_batches} "
                    f"({len(batch_paths)} transcripts) ---"
                )

            cmd = list(base_cmd)
            for path in batch_paths:
                cmd.extend(["-T", path])

            try:
                result = subprocess.run(cmd, check=True)
                print(
                    f"\nBatch {batch_idx + 1}/{n_batches} completed "
                    f"with exit code {result.returncode}"
                )
            except subprocess.CalledProcessError as e:
                print(
                    f"\nBatch {batch_idx + 1}/{n_batches} failed "
                    f"with exit code {e.returncode}"
                )
                exit_code = e.returncode
            except KeyboardInterrupt:
                print("\nInterrupted.")
                exit_code = 130
                break

        # Auto-aggregate even on failure/interrupt — completed results are still on disk
        new_scan_dirs = [d for d in scans_path.iterdir() if d not in existing_scan_dirs]
        if new_scan_dirs:
            self._auto_aggregate(new_scan_dirs)

        if exit_code != 0:
            sys.exit(exit_code)

    def _auto_aggregate(self, scan_dirs: list[Path]) -> None:
        """Aggregate new scan results into the S3 listing for deduplication."""
        from scripts.transcript_analysis.results_aggregator import (
            aggregate_scan_results,
            build_listing_json,
            merge_with_existing,
            print_summary,
            save_listing_json,
        )

        print("\n" + "=" * 60)
        print("AUTO-AGGREGATING results into listing for deduplication")
        print("=" * 60)

        scan_dir_strs = [str(d) for d in scan_dirs]
        print(f"Aggregating from {len(scan_dir_strs)} scan dir(s): {scan_dir_strs}")

        df = aggregate_scan_results(scan_dir_strs)
        listing = build_listing_json(df, classifier_model=DEFAULT_CLASSIFIER_MODEL)

        output_path = S3_EVAL_AWARENESS_LISTING
        if output_path.exists():
            print(f"Merging with existing listing at {output_path}")
            listing = merge_with_existing(listing, output_path)

        save_listing_json(listing, output_path)
        print_summary(listing)

    def progress(self) -> None:
        """Show progress against classification targets."""
        targets = load_targets()
        completed = load_completed_classifications()
        print_progress_summary(targets, completed)

    def summary(self) -> None:
        """Show summary of classification results."""
        from scripts.transcript_analysis.config import S3_EVAL_AWARENESS_LISTING
        from scripts.transcript_analysis.results_aggregator import (
            print_summary,
        )

        if not S3_EVAL_AWARENESS_LISTING.exists():
            print("No listing found at", S3_EVAL_AWARENESS_LISTING)
            return

        import json

        with open(S3_EVAL_AWARENESS_LISTING) as f:
            listing = json.load(f)
        print_summary(listing)

    def aggregate(
        self,
        scan_dir: str,
        output: str | None = None,
        merge: bool = True,
        upload: bool = False,
    ) -> None:
        """Aggregate scan results into a listing JSON file.

        Args:
            scan_dir: Path to scan directory (or glob pattern)
            output: Path to save listing JSON (default: S3 location)
            merge: Merge with existing listing if present
            upload: Upload to S3 after saving (saves to S3 path)
        """
        from scripts.transcript_analysis.results_aggregator import (
            aggregate_scan_results,
            build_listing_json,
            merge_with_existing,
            print_summary,
            save_listing_json,
        )

        scan_dirs = [scan_dir]
        if "*" in scan_dir:
            from glob import glob

            scan_dirs = glob(scan_dir)
            if not scan_dirs:
                raise ValueError(f"No scan directories match pattern: {scan_dir}")

        print(f"Aggregating results from {len(scan_dirs)} scan directories...")

        df = aggregate_scan_results(scan_dirs)
        listing = build_listing_json(df, classifier_model=DEFAULT_CLASSIFIER_MODEL)

        if output:
            output_path = Path(output)
        elif upload:
            output_path = S3_EVAL_AWARENESS_LISTING
        else:
            output_path = Path("eval_awareness_listing.json")

        if merge and output_path.exists():
            print(f"Merging with existing listing at {output_path}")
            listing = merge_with_existing(listing, output_path)

        save_listing_json(listing, output_path)
        print_summary(listing)

    def status(self, scan_dir: str) -> None:
        """Show status of a scan.

        Args:
            scan_dir: Path to scan directory
        """
        cmd = ["uv", "run", "scout", "scan", "status", scan_dir]
        subprocess.run(cmd)


def main() -> None:
    """Main entry point."""
    fire.Fire(EvalAwarenessClassifier)


if __name__ == "__main__":
    main()
