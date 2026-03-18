#!/usr/bin/env python3
"""Update paper sample cache from S3.

This script builds/updates the sample cache used for paper analysis.
It reads eval files from S3 and extracts all parameter values needed
for the Bayesian regression analysis.

The cache extraction is:
- Incremental: saves progress after each batch
- Interruptible: can safely Ctrl+C and resume later
- Balanced: spreads extraction across scenarios/models evenly

Usage:
    # Build/resume full cache with parameters (incremental, interruptible)
    uv run scripts/paper/update_sample_cache.py full

    # Check extraction progress
    uv run scripts/paper/update_sample_cache.py full --status

    # Force re-extraction (ignore existing progress)
    uv run scripts/paper/update_sample_cache.py full --force

    # Limit to specific scenarios
    uv run scripts/paper/update_sample_cache.py full --scenarios "agentic_misalignment_v2 sem_v2"

    # Adjust batch size (default 50)
    uv run scripts/paper/update_sample_cache.py full --batch-size 100

    # Check cache status
    uv run scripts/paper/update_sample_cache.py status

    # Sync cache to S3
    uv run scripts/paper/update_sample_cache.py sync
"""

import json
import logging
import os
import random
import signal
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fire
import pandas as pd
from inspect_ai.log import read_eval_log

from lib.model_registry import s3_name_to_api_name
from lib.paper_cache import PaperCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Models to exclude (no substantial samples per user decision)
EXCLUDED_MODELS = {
    "openai/gpt-5-pro-2025-10-06",
    "openai/o1-pro-2025-03-19",
    "openai/o3-pro-2025-06-10",
}

# Minimum version to include (from version tracking)
MIN_VERSION = "15.0.0"

# All variations to process
ALL_VARIATIONS = [
    ("agentic_misalignment_v2", "alert"),
    ("agentic_misalignment_v2", "leak-starsentinel"),
    ("agentic_misalignment_v2", "leak-doj"),
    ("email_spam_filter_v2", "email_spam_filter"),
    ("gpu_decision_email_assistant", "gpu_decision"),
    ("hiding_reward_hacking", "hiding_reward_hacking"),
    ("power_preservation", "threat"),
    ("power_preservation", "enhancement"),
    ("power_preservation", "expansion"),
    ("sem_v2", "classification"),
    ("sem_v2", "summarization"),
]

# Core parameters we want to extract (from README.md)
CORE_PARAMETERS = [
    # Strategic
    "goal_present",
    "goal_conflict",
    "threat",
    "cot_privacy",
    "action_oversight",
    "action_efficacy",
    "action_efficacy_binary",
    # Non-strategic
    "cot_tag",
    "reasoning_instructions",
    "independence",
    "anti_misalignment",
    "filler_richness",
    "date",
    "date_month_year",
]


def compute_derived_parameters(result: dict[str, Any]) -> None:
    """Compute derived parameters from base parameters.

    These parameters are defined as derived in parameter_spaces.py but aren't
    stored in the eval logs, so we need to recompute them during extraction.

    Args:
        result: Dict with extracted sample data (modified in place).
    """
    # action_efficacy_binary: effective -> "effective", else -> "not_effective"
    # From sem_v2/parameter_spaces.py lines 351-356
    action_efficacy = result.get("action_efficacy")
    if action_efficacy is not None:
        result["action_efficacy_binary"] = (
            "effective" if action_efficacy == "effective" else "not_effective"
        )


# =============================================================================
# Shutdown handling
# =============================================================================

shutdown_requested = False


def handle_interrupt(sig, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_requested
    if shutdown_requested:
        print("\nForce quit")
        sys.exit(1)
    print("\n\nShutdown requested, finishing current batch...")
    print("(Press Ctrl+C again to force quit)\n")
    shutdown_requested = True


signal.signal(signal.SIGINT, handle_interrupt)


# =============================================================================
# Listing loading and filtering
# =============================================================================


def load_listing_from_s3() -> dict[str, Any]:
    """Load listing.json from S3."""
    import boto3

    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET environment variable not set")

    s3 = boto3.client("s3")
    s3_root = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
    key = f"{s3_root}/evals/logs/listing.json"

    logger.info(f"Loading listing.json from s3://{bucket}/{key}...")

    with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        s3.download_file(bucket, key, tmp_path)
        with open(tmp_path) as f:
            listing = json.load(f)
        logger.info(f"Loaded {len(listing)} entries from listing.json")
        return listing
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def parse_listing_path(path: str) -> dict[str, str] | None:
    """Parse a listing.json key into components.

    Path format: scenario/variation/version/model/filename.eval

    Returns:
        Dict with scenario, variation, version, model, or None if invalid.
    """
    parts = path.split("/")
    if len(parts) < 5:
        return None

    scenario = parts[0]
    variation = parts[1]
    version = parts[2]
    model_s3 = parts[3]

    # Convert model name
    try:
        model = s3_name_to_api_name(model_s3)
    except Exception:
        model = model_s3.replace("_", "/", 1)

    return {
        "scenario": scenario,
        "variation": variation,
        "version": version,
        "model": model,
        "model_s3": model_s3,
    }


def filter_listing(
    listing: dict[str, Any],
    min_version: str = MIN_VERSION,
    excluded_models: set[str] | None = None,
    scenarios: set[str] | None = None,
) -> dict[str, Any]:
    """Filter listing to include only valid entries.

    Args:
        listing: Raw listing.json data.
        min_version: Minimum version string to include.
        excluded_models: Set of model API names to exclude.
        scenarios: If provided, only include these scenarios.

    Returns:
        Filtered listing dict.
    """
    from packaging.version import Version

    excluded_models = excluded_models or EXCLUDED_MODELS
    min_ver = Version(min_version)
    filtered = {}

    for path, entry in listing.items():
        # Parse path
        parsed = parse_listing_path(path)
        if parsed is None:
            continue

        # Filter by scenario if specified
        if scenarios and parsed["scenario"] not in scenarios:
            continue

        # Filter by version
        try:
            if Version(parsed["version"]) < min_ver:
                continue
        except Exception:
            continue

        # Filter by model
        if parsed["model"] in excluded_models:
            continue

        # Filter by status
        if entry.get("status") != "success":
            continue

        # Filter out entropy files
        if "/entropy/" in path:
            continue

        filtered[path] = entry

    logger.info(
        f"Filtered to {len(filtered)} entries "
        f"(removed {len(listing) - len(filtered)})"
    )
    return filtered


# =============================================================================
# Full cache (incremental extraction with parameters)
# =============================================================================


@dataclass
class WorkItem:
    """A single eval file to process."""

    eval_file: str  # S3 path (unique identifier)
    scenario: str
    variation: str
    model: str
    model_s3: str


def extract_single_eval(args: tuple[WorkItem, str]) -> dict[str, Any] | None:
    """Extract data from a single eval file (module-level for multiprocessing).

    Args:
        args: Tuple of (WorkItem, bucket_name).

    Returns:
        Dict with sample data, or None if extraction failed.
    """
    item, bucket = args
    s3_root = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
    s3_uri = f"s3://{bucket}/{s3_root}/evals/logs/{item.eval_file}"

    try:
        log = read_eval_log(s3_uri)

        if log.status != "success":
            return None

        if not log.samples or len(log.samples) == 0:
            return None

        sample = log.samples[0]

        if not sample.scores:
            return None

        score_obj = next(iter(sample.scores.values()))
        score_value = score_obj.value

        # Normalize score
        if score_value == "I" or score_value == "INCORRECT":
            score = 0.0
        elif score_value == "C" or score_value == "CORRECT":
            score = 1.0
        elif isinstance(score_value, (int, float)):
            score = float(score_value)
        else:
            try:
                score = float(score_value)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                return None

        # Build result dict - metadata fields get "meta_" prefix
        result: dict[str, Any] = {
            "meta_eval_file": item.eval_file,
            "meta_sample_id": log.eval.run_id,
            "meta_scenario": item.scenario,  # From S3 path
            "meta_variation": item.variation,  # From S3 path
            "meta_model": item.model,  # LLM model from S3 path
            "meta_score": score,
        }

        # Add task_params as-is (no prefix)
        metadata = sample.metadata or {}
        task_params = metadata.get("task_params", {})

        for key, value in task_params.items():
            if isinstance(value, (list, tuple)):
                continue
            if isinstance(value, str) and len(value) > 100:
                continue
            result[key] = value

        # Compute derived parameters that may be missing from older evals
        # action_efficacy_binary derived from action_efficacy for scenarios that need it
        if "action_efficacy" in result:
            if "action_efficacy_binary" not in result or result["action_efficacy_binary"] is None:
                action_efficacy = result["action_efficacy"]
                result["action_efficacy_binary"] = (
                    "effective" if action_efficacy == "effective" else "not_effective"
                )

        return result

    except Exception:
        return None


class IncrementalExtractor:
    """Handles incremental, interruptible extraction of eval files."""

    def __init__(
        self,
        cache: PaperCache,
        batch_size: int = 500,
        max_workers: int = 32,
    ):
        self.cache = cache
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.processed: set[str] = set()
        self.failed: set[str] = set()  # Track failed evals to avoid re-processing
        self.start_time: float | None = None
        self.processed_count = 0  # Successful extractions this session
        self.failed_count = 0  # Failed extractions this session
        self.failed_evals_path = cache.samples_dir / "failed_evals.json"

    def load_processed_eval_files(self) -> None:
        """Load set of already-processed eval files from existing parquet files."""
        self.processed = set()
        self.failed = set()

        if not self.cache.samples_dir.exists():
            logger.info("No existing cache found, starting fresh")
            return

        parquet_files = list(self.cache.samples_dir.rglob("samples_*.parquet"))
        logger.info(f"Loading progress from {len(parquet_files)} existing parquet files...")

        for parquet_file in parquet_files:
            try:
                # Read just the meta_eval_file column (fast columnar read)
                df = pd.read_parquet(parquet_file, columns=["meta_eval_file"])
                self.processed.update(df["meta_eval_file"].tolist())
            except Exception as e:
                logger.warning(f"Could not read {parquet_file}: {e}")

        # Load failed evals
        if self.failed_evals_path.exists():
            try:
                with open(self.failed_evals_path) as f:
                    self.failed = set(json.load(f))
                logger.info(f"Loaded {len(self.failed)} previously failed eval files")
            except Exception as e:
                logger.warning(f"Could not load failed evals: {e}")

        logger.info(f"Found {len(self.processed)} successfully processed, {len(self.failed)} failed")

    def build_work_queue(
        self,
        listing: dict[str, Any],
        seed: int = 42,
    ) -> list[WorkItem]:
        """Build shuffled work queue from listing, excluding already-processed and failed.

        Args:
            listing: Filtered listing.json data.
            seed: Random seed for reproducible shuffling.

        Returns:
            Shuffled list of WorkItem objects.
        """
        work = []
        skipped_processed = 0
        skipped_failed = 0

        for path, entry in listing.items():
            # Skip if already processed successfully
            if path in self.processed:
                skipped_processed += 1
                continue

            # Skip if previously failed (don't re-process known failures)
            if path in self.failed:
                skipped_failed += 1
                continue

            parsed = parse_listing_path(path)
            if parsed is None:
                continue

            work.append(
                WorkItem(
                    eval_file=path,
                    scenario=parsed["scenario"],
                    variation=parsed["variation"],
                    model=parsed["model"],
                    model_s3=parsed["model_s3"],
                )
            )

        # Shuffle for balanced progress across scenarios/models
        random.seed(seed)
        random.shuffle(work)

        logger.info(
            f"Work queue: {len(work)} evals to process "
            f"(skipped {skipped_processed} processed, {skipped_failed} failed)"
        )
        return work

    def save_failed_evals(self) -> None:
        """Save the set of failed eval files to disk."""
        self.failed_evals_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.failed_evals_path, "w") as f:
            json.dump(sorted(self.failed), f)

    def save_batch_results(self, results: list[dict[str, Any]]) -> None:
        """Save batch results to parquet files (one per model).

        Args:
            results: List of extracted sample dicts.
        """
        if not results:
            return

        # Group by (meta_scenario, meta_variation, meta_model)
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for result in results:
            key = (result["meta_scenario"], result["meta_variation"], result["meta_model"])
            grouped[key].append(result)

        # Save each group
        for (scenario, variation, model), group_results in grouped.items():
            model_safe = model.replace("/", "_")
            parquet_path = (
                self.cache.samples_dir / scenario / variation / f"samples_{model_safe}.parquet"
            )
            parquet_path.parent.mkdir(parents=True, exist_ok=True)

            new_df = pd.DataFrame(group_results)

            # Ensure core parameters exist
            for param in CORE_PARAMETERS:
                if param not in new_df.columns:
                    new_df[param] = None

            # Append to existing file if it exists
            if parquet_path.exists():
                existing_df = pd.read_parquet(parquet_path)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                # Deduplicate by meta_eval_file (in case of partial writes)
                combined_df = combined_df.drop_duplicates(subset=["meta_eval_file"], keep="first")
                combined_df.to_parquet(parquet_path, index=False)
            else:
                new_df.to_parquet(parquet_path, index=False)

        # Update in-memory processed set
        for result in results:
            self.processed.add(result["meta_eval_file"])

    def print_progress(self, total_work: int, batch_results: int, batch_failed: int) -> None:
        """Print progress statistics."""
        self.processed_count += batch_results
        self.failed_count += batch_failed

        if self.start_time is None:
            return

        elapsed = time.time() - self.start_time
        rate = self.processed_count / elapsed if elapsed > 0 else 0

        remaining = total_work - len(self.processed)
        eta_seconds = remaining / rate if rate > 0 else 0
        eta_hours = eta_seconds / 3600

        # Count unique scenarios and models with data
        scenarios_with_data = set()
        models_with_data = set()
        for pf in self.cache.samples_dir.rglob("samples_*.parquet"):
            parts = pf.relative_to(self.cache.samples_dir).parts
            if len(parts) >= 3:
                scenarios_with_data.add(parts[0])
                models_with_data.add(pf.stem.replace("samples_", "").replace("_", "/", 1))

        pct = 100 * len(self.processed) / (len(self.processed) + remaining) if (len(self.processed) + remaining) > 0 else 0

        print(f"\n{'='*60}")
        print(f"Progress: {len(self.processed):,} / {len(self.processed) + remaining:,} ({pct:.1f}%)")
        print(f"This batch: {batch_results} extracted, {batch_failed} failed")
        print(f"Rate: {rate:.1f} evals/sec")
        print(f"Scenarios with data: {len(scenarios_with_data)} | Models with data: {len(models_with_data)}")
        print(f"Remaining: {remaining:,} evals | ETA: {eta_hours:.1f} hours")
        print(f"{'='*60}\n")

    def run(
        self,
        listing: dict[str, Any],
        force: bool = False,
    ) -> None:
        """Run incremental extraction.

        Args:
            listing: Filtered listing.json data.
            force: If True, ignore existing progress and start fresh.
        """
        global shutdown_requested

        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise ValueError("S3_BUCKET environment variable not set")

        # Load existing progress (unless force)
        if not force:
            self.load_processed_eval_files()
        else:
            logger.info("Force mode: ignoring existing progress")
            self.processed = set()
            self.failed = set()

        # Build work queue
        work_queue = self.build_work_queue(listing)

        if not work_queue:
            print("\nAll evals already processed! Nothing to do.")
            return

        total_work = len(work_queue) + len(self.processed) + len(self.failed)
        print(f"\nStarting extraction: {len(work_queue)} evals to process")
        print(f"Already processed: {len(self.processed)} successful, {len(self.failed)} failed (skipped)")
        print(f"Batch size: {self.batch_size}, Workers: {self.max_workers}")
        print("\nPress Ctrl+C to stop gracefully (progress will be saved)\n")

        self.start_time = time.time()
        self.processed_count = 0

        # Process in batches
        for batch_start in range(0, len(work_queue), self.batch_size):
            if shutdown_requested:
                print("\nShutdown complete. Progress saved.")
                break

            batch = work_queue[batch_start : batch_start + self.batch_size]
            results: list[dict[str, Any]] = []
            batch_failed: list[str] = []  # Track failed eval files

            # Extract batch in parallel using processes (bypasses GIL for CPU-bound parsing)
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit work as (item, bucket) tuples for the module-level function
                work_args = [(item, bucket) for item in batch]
                futures = {
                    executor.submit(extract_single_eval, args): args[0]
                    for args in work_args
                }

                for future in as_completed(futures):
                    if shutdown_requested:
                        # Cancel remaining futures
                        for f in futures:
                            f.cancel()
                        break

                    item = futures[future]  # Get the WorkItem for this future
                    result = future.result()
                    if result is not None:
                        results.append(result)
                    else:
                        batch_failed.append(item.eval_file)

            # Save batch results
            self.save_batch_results(results)

            # Track failed evals (so we don't re-process them next time)
            if batch_failed:
                self.failed.update(batch_failed)
                self.save_failed_evals()

            # Print progress
            self.print_progress(total_work, len(results), len(batch_failed))

        # Final summary
        elapsed = time.time() - self.start_time if self.start_time else 0
        print(f"\n{'='*60}")
        print(f"Extraction {'stopped' if shutdown_requested else 'complete'}!")
        print(f"This session: {self.processed_count} successful, {self.failed_count} failed")
        print(f"Total in cache: {len(self.processed)} successful, {len(self.failed)} failed")
        print(f"Time elapsed: {elapsed / 60:.1f} minutes")
        print(f"{'='*60}")


def print_full_cache_status(cache: PaperCache) -> None:
    """Print status of the sample cache extraction."""
    print("\n=== Sample Cache Extraction Status ===\n")

    if not cache.samples_dir.exists():
        print("No cache found. Run 'full' command to start extraction.")
        return

    parquet_files = list(cache.samples_dir.rglob("samples_*.parquet"))
    if not parquet_files:
        print("No cache found. Run 'full' command to start extraction.")
        return

    # Count processed evals and samples
    total_evals = 0
    total_samples = 0
    by_scenario: dict[str, int] = defaultdict(int)
    by_model: dict[str, int] = defaultdict(int)

    for parquet_file in parquet_files:
        try:
            df = pd.read_parquet(parquet_file)
            n_samples = len(df)
            total_samples += n_samples
            total_evals += n_samples

            # Parse path for scenario
            parts = parquet_file.relative_to(cache.samples_dir).parts
            if len(parts) >= 2:
                scenario = parts[0]
                by_scenario[scenario] += n_samples

            # Count by model
            if "meta_model" in df.columns:
                for model, count in df["meta_model"].value_counts().items():
                    by_model[str(model)] += count

        except Exception as e:
            logger.warning(f"Could not read {parquet_file}: {e}")

    # Load failed evals count
    failed_evals_path = cache.samples_dir / "failed_evals.json"
    failed_count = 0
    if failed_evals_path.exists():
        try:
            with open(failed_evals_path) as f:
                failed_count = len(json.load(f))
        except Exception:
            pass

    print(f"Total samples extracted: {total_samples:,}")
    if failed_count > 0:
        print(f"Failed evals (skipped): {failed_count:,}")
    print("\nBy scenario:")
    for scenario in sorted(by_scenario.keys()):
        print(f"  {scenario}: {by_scenario[scenario]:,}")

    print(f"\nBy model ({len(by_model)} models with data):")
    for model, count in sorted(by_model.items(), key=lambda x: -x[1])[:10]:
        print(f"  {model}: {count:,}")
    if len(by_model) > 10:
        print(f"  ... and {len(by_model) - 10} more models")

    # Estimate remaining work
    try:
        listing = load_listing_from_s3()
        listing = filter_listing(listing)
        total_available = len(listing)
        total_processed = total_evals + failed_count
        remaining = total_available - total_processed
        pct = 100 * total_processed / total_available if total_available > 0 else 0
        print(f"\nProgress: {total_processed:,} / {total_available:,} ({pct:.1f}%)")
        print(f"  ({total_evals:,} successful, {failed_count:,} failed)")
        print(f"Remaining: {remaining:,} evals")
    except Exception as e:
        logger.warning(f"Could not load listing for progress estimate: {e}")


def print_cache_status(cache: PaperCache) -> None:
    """Print current cache status."""
    metadata = cache.load_metadata()

    print("\n=== Paper Cache Status ===\n")

    if metadata is None:
        print("No cache metadata found. Run 'summary' command to build cache.")
        return

    print(f"Last updated: {metadata.last_updated}")
    print(f"Listing hash: {metadata.listing_hash}")
    print()

    # Sample counts table
    print("Sample counts by scenario/variation:\n")

    # Collect all variations
    all_variations = set()
    for scenario_counts in metadata.sample_counts.values():
        all_variations.update(scenario_counts.keys())

    # Print header
    scenarios = sorted(metadata.sample_counts.keys())
    print(f"{'Variation':<25}", end="")
    for scenario in scenarios:
        abbrev = {
            "agentic_misalignment_v2": "AM",
            "email_spam_filter_v2": "ESF",
            "gpu_decision_email_assistant": "GPU",
            "hiding_reward_hacking": "HRH",
            "power_preservation": "PP",
            "sem_v2": "SEM",
        }.get(scenario, scenario[:6])
        print(f"{abbrev:>10}", end="")
    print()

    # Print rows
    for variation in sorted(all_variations):
        print(f"{variation:<25}", end="")
        for scenario in scenarios:
            count = metadata.sample_counts.get(scenario, {}).get(variation, 0)
            if count > 0:
                print(f"{count:>10,}", end="")
            else:
                print(f"{'--':>10}", end="")
        print()

    # Totals
    print(f"\n{'TOTAL':<25}", end="")
    total = 0
    for scenario in scenarios:
        scenario_total = sum(metadata.sample_counts.get(scenario, {}).values())
        print(f"{scenario_total:>10,}", end="")
        total += scenario_total
    print(f"\n\nGrand total: {total:,} samples")


def sync_cache(cache: PaperCache, direction: str = "both") -> None:
    """Sync cache with S3.

    Args:
        cache: PaperCache instance to sync.
        direction: "to_s3", "from_s3", or "both"
    """
    if direction in ("from_s3", "both"):
        logger.info("Syncing from S3...")
        cache.sync_from_s3()

    if direction in ("to_s3", "both"):
        logger.info("Syncing to S3...")
        cache.sync_to_s3()


class CLI:
    """CLI commands for sample cache management."""

    def __init__(self):
        self.cache = PaperCache()

    def status(self):
        """Print current cache status."""
        print_cache_status(self.cache)
        print_full_cache_status(self.cache)

    def sync(self, direction: str = "both"):
        """Sync cache with S3.

        Args:
            direction: "to_s3", "from_s3", or "both"
        """
        sync_cache(self.cache, direction)

    def full(
        self,
        status: bool = False,
        force: bool = False,
        scenarios: str | None = None,
        batch_size: int = 500,
        max_workers: int = 32,
    ):
        """Build full cache with parameters (incremental, interruptible).

        Args:
            status: Just show extraction progress, don't extract.
            force: Force re-extraction, ignoring existing progress.
            scenarios: Space-separated list of scenarios to include.
            batch_size: Number of evals per batch (saves after each batch).
            max_workers: Number of parallel processes for extraction.
        """
        if status:
            print_full_cache_status(self.cache)
            return

        # Load and filter listing
        listing = load_listing_from_s3()

        # Parse scenarios filter
        scenario_set = None
        if scenarios:
            scenario_set = set(scenarios.split())
            logger.info(f"Filtering to scenarios: {scenario_set}")

        listing = filter_listing(listing, scenarios=scenario_set)

        # Run incremental extraction
        extractor = IncrementalExtractor(
            self.cache,
            batch_size=batch_size,
            max_workers=max_workers,
        )
        extractor.run(listing, force=force)


def main():
    fire.Fire(CLI)


if __name__ == "__main__":
    main()
