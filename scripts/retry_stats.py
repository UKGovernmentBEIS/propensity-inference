#!/usr/bin/env python3
"""Gather retry statistics from eval logs in structured S3 storage.

Scans eval logs and reports on samples that required retries or failed permanently.
Results are cached locally to avoid re-reading logs from S3 on subsequent runs.

Usage:
    # Stats for all scenarios
    uv run scripts/retry_stats.py

    # Stats for a specific scenario
    uv run scripts/retry_stats.py --scenario sem_v2

    # Stats for a specific scenario/variation
    uv run scripts/retry_stats.py --scenario sem_v2 --variation leaking

    # Process a specific list of S3 URIs from stdin (e.g. reprocess from a cache file)
    jq -r '.s3_uri' retry_stats_nonzero.jsonl | uv run scripts/retry_stats.py --from-stdin

    # Limit number of logs to process per scenario (for testing)
    uv run scripts/retry_stats.py --limit 100

    # Filter by model
    uv run scripts/retry_stats.py --scenario sem_v2 --model openai/o4-mini

    # Disable cache (always fetch fresh from S3)
    uv run scripts/retry_stats.py --no-cache

    # Use custom cache location
    uv run scripts/retry_stats.py --cache-path /tmp/my_cache.jsonl

    # List available scenarios
    uv run scripts/retry_stats.py --list-only
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fire
from inspect_ai.log import EvalError, EvalLog, read_eval_log
from pydantic import BaseModel

from lib.eval_storage import (
    EVALS_PREFIX,
    EvalStoragePath,
    get_bucket,
    get_s3_client,
    list_evals,
)

# Default cache location (in current working directory)
DEFAULT_CACHE_PATH = Path.cwd() / "retry_stats_cache.jsonl"


class RetryReasons(BaseModel):
    """Counts of retry errors by classification.

    All fields default to 0. The 'unclassified' field counts errors that don't
    match any known classification pattern.
    """

    unclassified: int = 0
    expired_token: int = 0
    openrouter_insufficient_credits: int = 0
    google_thinking_budget: int = 0
    google_empty_prompt: int = 0
    done_action_timeout: int = 0


def classify_error(error: EvalError) -> str:
    """Classify an error into a category based on its message.

    Returns the classification key (e.g., 'expired_token', 'unclassified').
    """
    if not error.message:
        return "unclassified"

    msg = error.message.lower()

    # Token expiration errors (AWS Secrets Manager, etc.)
    if (
        "expiredtokenexception" in msg
        and "security token included in the request is expired" in msg
    ):
        return "expired_token"

    # OpenRouter billing errors
    if (
        "openrouter" in msg
        and "insufficient credits" in msg
        and "error code: 402" in msg
    ):
        return "openrouter_insufficient_credits"

    # Google/Gemini: thinking_budget not supported
    if "does not support setting thinking_budget to 0" in msg:
        return "google_thinking_budget"

    # Google/Gemini: empty prompt / missing parts field
    if "at least one parts field" in msg and "prompt input" in msg:
        return "google_empty_prompt"

    if "model failed to call done() within" in msg:
        return "done_action_timeout"

    return "unclassified"


class RetryStats(BaseModel):
    """Retry statistics for a single eval log."""

    s3_uri: str
    total_samples: int
    samples_with_retries: int
    samples_with_errors: int
    total_retries: int
    retry_reasons: RetryReasons

    @classmethod
    def from_eval_log(cls, s3_uri: str, log: EvalLog) -> RetryStats:
        """Extract retry statistics from a full EvalLog."""
        total_samples = 0
        samples_with_retries = 0
        samples_with_errors = 0
        total_retries = 0
        reasons: dict[str, int] = {
            "unclassified": 0,
            "expired_token": 0,
            "openrouter_insufficient_credits": 0,
            "google_thinking_budget": 0,
            "google_empty_prompt": 0,
            "done_action_timeout": 0,
        }

        if log.samples:
            for sample in log.samples:
                total_samples += 1
                if sample.error_retries:
                    samples_with_retries += 1
                    total_retries += len(sample.error_retries)
                    # Classify each retry error
                    for error in sample.error_retries:
                        classification = classify_error(error)
                        reasons[classification] += 1
                if sample.error:
                    samples_with_errors += 1

        return cls(
            s3_uri=s3_uri,
            total_samples=total_samples,
            samples_with_retries=samples_with_retries,
            samples_with_errors=samples_with_errors,
            total_retries=total_retries,
            retry_reasons=RetryReasons(**reasons),
        )


class RetryStatsCache:
    """Local file cache for retry statistics using JSONL format.

    Uses append-only writes - new entries are appended to the file,
    and duplicates are deduplicated on load (last entry wins).
    """

    def __init__(self, cache_path: Path = DEFAULT_CACHE_PATH):
        self.cache_path = cache_path
        self._cache: dict[str, RetryStats] = {}
        self._pending: list[RetryStats] = []  # New entries to append
        self._load()

    def _load(self) -> None:
        """Load cache from disk (JSONL format)."""
        try:
            with open(self.cache_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        stats = RetryStats.model_validate(data)
                        self._cache[stats.s3_uri] = stats
            print(
                f"Loaded {len(self._cache):,} cached entries from {self.cache_path}",
                file=sys.stderr,
            )
        except FileNotFoundError:
            print(
                f"No cache file at {self.cache_path}, starting fresh", file=sys.stderr
            )

    def save(self) -> None:
        """Append new entries to cache file (JSONL format)."""
        if not self._pending:
            print("No new entries to save.", file=sys.stderr)
            return

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "a") as f:
            for stats in self._pending:
                f.write(json.dumps(stats.model_dump()) + "\n")
        print(
            f"Appended {len(self._pending):,} new entries to cache "
            f"(total: {len(self._cache):,}) at {self.cache_path}",
            file=sys.stderr,
        )
        self._pending = []

    def get(self, s3_uri: str) -> RetryStats | None:
        """Get cached stats for a URI, or None if not cached."""
        return self._cache.get(s3_uri)

    def put(self, stats: RetryStats) -> None:
        """Add stats to cache (will be appended on save)."""
        if stats.s3_uri not in self._cache:
            self._pending.append(stats)
        self._cache[stats.s3_uri] = stats

    def __contains__(self, s3_uri: str) -> bool:
        """Check if a URI is in the cache."""
        return s3_uri in self._cache

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)


def _print_running_summary(stats: list[RetryStats], processed: int, total: int) -> None:
    """Print a running summary of retry statistics."""
    total_samples = sum(s.total_samples for s in stats)
    if total_samples == 0:
        return

    samples_with_retries = sum(s.samples_with_retries for s in stats)
    samples_with_errors = sum(s.samples_with_errors for s in stats)
    total_retries = sum(s.total_retries for s in stats)
    logs_with_retries = sum(1 for s in stats if s.samples_with_retries > 0)

    print(
        f"\n--- Summary at {processed}/{total} logs ---\n"
        f"  Logs: {len(stats):,} | with retries: {logs_with_retries:,}\n"
        f"  Samples: {total_samples:,} | "
        f"retried: {samples_with_retries:,} ({100 * samples_with_retries / total_samples:.2f}%) | "
        f"errors: {samples_with_errors:,} ({100 * samples_with_errors / total_samples:.2f}%)\n"
        f"  Total retry attempts: {total_retries:,}",
        file=sys.stderr,
    )


def gather_retry_stats(
    s3_uris: list[str],
    max_workers: int = 16,
    summary_interval: int = 500,
    cache: RetryStatsCache | None = None,
    cache_save_interval: int = 500,
) -> list[RetryStats]:
    """Gather retry statistics from logs (reads full logs).

    Args:
        s3_uris: List of S3 URIs to eval logs
        max_workers: Number of parallel workers
        summary_interval: Print running summary every N logs
        cache: Optional cache to use for storing/retrieving stats
        cache_save_interval: Save cache to disk every N new entries

    Returns:
        List of RetryStats objects
    """
    stats: list[RetryStats] = []
    total = len(s3_uris)
    processed = 0
    errors = 0
    last_summary = 0
    last_cache_save = 0
    cache_hits = 0

    # Check cache for already-processed URIs
    uris_to_fetch: list[str] = []
    if cache is not None:
        for uri in s3_uris:
            cached = cache.get(uri)
            if cached is not None:
                stats.append(cached)
                cache_hits += 1
            else:
                uris_to_fetch.append(uri)
        if cache_hits > 0:
            print(
                f"Found {cache_hits:,} cached entries, "
                f"fetching {len(uris_to_fetch):,} from S3",
                file=sys.stderr,
            )
    else:
        uris_to_fetch = s3_uris

    if not uris_to_fetch:
        print("All entries found in cache!", file=sys.stderr)
        return stats

    def process_one(s3_uri: str) -> RetryStats:
        log = read_eval_log(s3_uri, header_only=False)
        return RetryStats.from_eval_log(s3_uri, log)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, uri): uri for uri in uris_to_fetch}

        for future in as_completed(futures):
            processed += 1
            print(
                f"\rGathering retry stats: {processed}/{len(uris_to_fetch)} "
                f"(collected: {len(stats)}, errors: {errors}, cached: {cache_hits})",
                end="",
                file=sys.stderr,
            )

            try:
                result = future.result()
            except Exception as e:
                uri = futures[future]
                print(f"\nError processing {uri}: {e}", file=sys.stderr)
                errors += 1
            else:
                stats.append(result)
                if cache is not None:
                    cache.put(result)

            # Print running summary periodically
            if processed - last_summary >= summary_interval:
                _print_running_summary(stats, processed + cache_hits, total)
                last_summary = processed

            # Save cache periodically
            if cache is not None and processed - last_cache_save >= cache_save_interval:
                cache.save()
                last_cache_save = processed

    print(file=sys.stderr)
    return stats


def print_retry_stats_summary(
    stats: list[RetryStats], label: str | None = None
) -> None:
    """Print a summary of retry statistics."""
    if not stats:
        print("No logs processed.", file=sys.stderr)
        return

    total_logs = len(stats)
    total_samples = sum(s.total_samples for s in stats)

    if total_samples == 0:
        print("No samples found in logs.", file=sys.stderr)
        return

    total_samples_with_retries = sum(s.samples_with_retries for s in stats)
    total_samples_with_errors = sum(s.samples_with_errors for s in stats)
    total_retries = sum(s.total_retries for s in stats)

    logs_with_retries = sum(1 for s in stats if s.samples_with_retries > 0)
    logs_with_errors = sum(1 for s in stats if s.samples_with_errors > 0)

    header = f"Retry Statistics: {label}" if label else "Retry Statistics Summary"
    print("\n" + "=" * 60)
    print(header)
    print("=" * 60)
    print(f"Logs processed:              {total_logs:,}")
    print(
        f"Logs with retried samples:   {logs_with_retries:,} "
        f"({100 * logs_with_retries / total_logs:.1f}%)"
    )
    print(
        f"Logs with failed samples:    {logs_with_errors:,} "
        f"({100 * logs_with_errors / total_logs:.1f}%)"
    )
    print()
    print(f"Total samples:               {total_samples:,}")
    print(
        f"Samples with retries:        {total_samples_with_retries:,} "
        f"({100 * total_samples_with_retries / total_samples:.2f}%)"
    )
    print(
        f"Samples with errors:         {total_samples_with_errors:,} "
        f"({100 * total_samples_with_errors / total_samples:.2f}%)"
    )
    print(f"Total retry attempts:        {total_retries:,}")
    if total_samples_with_retries > 0:
        print(
            f"Avg retries per affected:    "
            f"{total_retries / total_samples_with_retries:.2f}"
        )

    # Retry reasons breakdown
    if total_retries > 0:
        reason_totals: dict[str, int] = {}
        for s in stats:
            for field, count in s.retry_reasons.model_dump().items():
                reason_totals[field] = reason_totals.get(field, 0) + count
        print()
        print("Retry reasons breakdown:")
        for reason, count in sorted(reason_totals.items(), key=lambda x: -x[1]):
            if count > 0:
                print(
                    f"  {reason:<36} {count:>6,}  ({100 * count / total_retries:.1f}%)"
                )

    print("=" * 60)


def _list_children(prefix: str, bucket: str | None = None) -> list[str]:
    """List immediate children of an S3 prefix."""
    bucket = bucket or get_bucket()
    s3 = get_s3_client()

    result = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    children = [
        prefix_obj["Prefix"].rstrip("/").split("/")[-1]
        for prefix_obj in result.get("CommonPrefixes", [])
    ]
    return sorted(children)


def list_scenarios(bucket: str | None = None) -> list[str]:
    """List all scenarios in structured storage."""
    return _list_children(f"{EVALS_PREFIX}/", bucket)


def list_variations(scenario: str, bucket: str | None = None) -> list[str]:
    """List all variations for a scenario."""
    return _list_children(f"{EVALS_PREFIX}/{scenario}/", bucket)


def main(
    scenario: str | None = None,
    variation: str | None = None,
    model: str | None = None,
    limit: int | None = None,
    workers: int = 16,
    list_only: bool = False,
    no_cache: bool = False,
    cache_path: str | None = None,
    from_stdin: bool = False,
) -> int:
    """Gather retry statistics from eval logs.

    Args:
        scenario: Scenario name (optional, processes all scenarios if not specified)
        variation: Variation name (optional, scans all if not specified)
        model: Model API name to filter by (optional)
        limit: Limit number of logs to process per scenario (for testing)
        workers: Number of parallel workers
        list_only: Just list available scenarios and exit
        no_cache: Disable caching (always fetch from S3)
        cache_path: Custom path for the cache file
        from_stdin: Read S3 URIs from stdin (one per line) instead of listing from S3

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if from_stdin:
        s3_uris = [line.strip() for line in sys.stdin if line.strip()]
        print(f"Read {len(s3_uris):,} URIs from stdin", file=sys.stderr)
        cache: RetryStatsCache | None = None
        if not no_cache:
            path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
            cache = RetryStatsCache(path)
        stats = gather_retry_stats(s3_uris, max_workers=workers, cache=cache)
        if cache is not None:
            cache.save()
        print_retry_stats_summary(stats)
        return 0

    bucket = get_bucket()

    if list_only:
        print("Available scenarios:")
        for s in list_scenarios(bucket):
            variations = list_variations(s, bucket)
            print(f"  {s}: {', '.join(variations)}")
        return 0

    # Set up cache (shared across all scenarios)
    cache: RetryStatsCache | None = None
    if not no_cache:
        path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        cache = RetryStatsCache(path)

    # Determine which scenarios to process
    scenarios_to_process = [scenario] if scenario else list_scenarios(bucket)
    if not scenario:
        print(f"Processing all {len(scenarios_to_process)} scenarios", file=sys.stderr)

    all_stats: list[RetryStats] = []

    for current_scenario in scenarios_to_process:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"Processing: {current_scenario}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

        # Get min version for this scenario
        min_version = "0.0.0"

        # Determine variations to scan
        if variation:
            variations = [variation]
        else:
            variations = list_variations(current_scenario, bucket)
            print(
                f"Scanning {len(variations)} variations: {variations}", file=sys.stderr
            )

        # Collect all eval paths
        all_paths: list[EvalStoragePath] = []
        for var in variations:
            paths = list_evals(
                scenario=current_scenario,
                variation=var,
                model=model,
                min_version=min_version,
                bucket=bucket,
            )
            all_paths.extend(paths)
            print(f"  {var}: {len(paths)} evals", file=sys.stderr)

        print(f"Total: {len(all_paths)} eval files", file=sys.stderr)

        if not all_paths:
            print("No eval files found.", file=sys.stderr)
            continue

        # Apply limit (per scenario)
        if limit and len(all_paths) > limit:
            print(f"Limiting to {limit} files", file=sys.stderr)
            all_paths = all_paths[:limit]

        # Convert to URIs
        s3_uris = [p.s3_uri(bucket) for p in all_paths]

        # Gather stats
        print("\nGathering retry statistics (reading full logs)...", file=sys.stderr)
        stats = gather_retry_stats(s3_uris, max_workers=workers, cache=cache)
        all_stats.extend(stats)

        # Save cache after each scenario
        if cache is not None:
            cache.save()

        # Print per-scenario summary
        print_retry_stats_summary(stats, label=current_scenario)

    # Print overall summary if multiple scenarios
    if len(scenarios_to_process) > 1:
        print_retry_stats_summary(all_stats, label="OVERALL")

    return 0


if __name__ == "__main__":
    sys.exit(fire.Fire(main))
