#!/usr/bin/env python3
"""S3 Log Crawler - Find and filter evaluation logs in S3.

This tool scans S3 for evaluation logs matching specified criteria:
- Scenario name filtering (exact match or regex)
- Date range filtering (ISO format)
- Version validity filtering (requires valid version metadata)

Usage:
    # List matching logs to stdout
    uv run scripts/s3_log_crawler.py --scenarios "sem_v2,gpu_decision_email_assistant"

    # Filter by date range
    uv run scripts/s3_log_crawler.py --start-date 2025-11-01 --end-date 2025-12-01

    # Output to file
    uv run scripts/s3_log_crawler.py --scenarios "sem_v2" --output results.txt

    # Sync to local directory
    uv run scripts/s3_log_crawler.py --scenarios "sem_v2" --sync-to ./local_logs/

    # Filter by run type
    uv run scripts/s3_log_crawler.py --run-type main-runs

    # Limit number of files to process (for testing)
    uv run scripts/s3_log_crawler.py --limit 100
"""

from __future__ import annotations

import logging
import os
import re
import sys
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import boto3
import fire
from inspect_ai.log import EvalLog, read_eval_log

# Configure module logger
logger = logging.getLogger(__name__)

# S3 path constants
PROPENSITY_S3_ROOT = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
S3_LOG_PREFIX = f"{PROPENSITY_S3_ROOT}/automated-experiments"
RUN_TYPE_SUBDIRS = {
    "main-runs": "main-runs/logs",
    "other-runs": "other-runs/logs",
}

# Regex to extract timestamp from S3 path (format: 2025-12-02T13-24-32)
DIR_TIMESTAMP_PATTERN = re.compile(r"/(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})/")


def extract_dir_timestamp(s3_path: str) -> datetime | None:
    """Extract timestamp from directory name in S3 path.

    Expected format: .../2025-12-02T13-24-32/...
    """
    match = DIR_TIMESTAMP_PATTERN.search(s3_path)
    if match:
        try:
            ts_str = match.group(1)
            # Parse format: 2025-12-02T13-24-32
            return datetime.strptime(ts_str, "%Y-%m-%dT%H-%M-%S")
        except ValueError:
            pass
    return None


@dataclass
class LogMetadata:
    """Metadata extracted from an evaluation log."""

    s3_path: str
    scenario_name: str | None
    version: str | None
    timestamp: datetime | None
    variation_name: str | None
    suite_name: str | None
    assigned_model: str | None
    status: str | None

    @classmethod
    def from_eval_log(cls, s3_path: str, log: EvalLog) -> LogMetadata:
        """Create LogMetadata from an EvalLog object.

        Note: This expects a log loaded with header_only=True, which excludes
        sample data. All metadata is read from eval.metadata.
        """
        metadata = log.eval.metadata or {}

        # Extract timestamp from run_config or eval creation time
        timestamp = None
        run_config = metadata.get("run_config", {})
        if run_config and "timestamp" in run_config:
            try:
                timestamp = datetime.fromisoformat(run_config["timestamp"])
            except (ValueError, TypeError):
                pass

        # Fall back to eval created time
        if timestamp is None and log.eval.created:
            try:
                timestamp = datetime.fromisoformat(
                    log.eval.created.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Get model - prefer assigned_model from metadata, fallback to log.eval.model
        assigned_model = metadata.get("assigned_model")
        if assigned_model is None:
            assigned_model = log.eval.model

        return cls(
            s3_path=s3_path,
            scenario_name=metadata.get("scenario_name"),
            version=metadata.get("version"),
            timestamp=timestamp,
            variation_name=metadata.get("variation_name"),
            suite_name=metadata.get("suite_name"),
            assigned_model=assigned_model,
            status=log.status,
        )


class LogFilter(ABC):
    """Base class for log filters."""

    @abstractmethod
    def matches(self, metadata: LogMetadata) -> bool:
        """Return True if the log matches this filter."""
        pass

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of this filter."""
        pass


class ScenarioFilter(LogFilter):
    """Filter logs by scenario name (exact match or regex)."""

    def __init__(self, patterns: list[str], use_regex: bool = False):
        self.patterns = patterns
        self.use_regex = use_regex
        if use_regex:
            self.compiled_patterns = [re.compile(p) for p in patterns]
        else:
            self.compiled_patterns = []

    def matches(self, metadata: LogMetadata) -> bool:
        if metadata.scenario_name is None:
            logger.warning(
                "Log has no scenario_name metadata, excluding: %s", metadata.s3_path
            )
            return False

        if self.use_regex:
            return any(p.search(metadata.scenario_name) for p in self.compiled_patterns)
        else:
            return metadata.scenario_name in self.patterns

    def describe(self) -> str:
        if self.use_regex:
            return f"scenario matches regex: {self.patterns}"
        return f"scenario in: {self.patterns}"


class DateRangeFilter(LogFilter):
    """Filter logs by date range."""

    def __init__(self, start_date: datetime | None, end_date: datetime | None):
        # Normalize filter dates to UTC-aware for consistent comparison
        self.start_date = self._to_utc_aware(start_date)
        self.end_date = self._to_utc_aware(end_date)

    @staticmethod
    def _to_utc_aware(dt: datetime | None) -> datetime | None:
        """Convert datetime to UTC-aware. Naive datetimes are assumed to be UTC."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def matches(self, metadata: LogMetadata) -> bool:
        if metadata.timestamp is None:
            logger.warning(
                "Log has no timestamp metadata, excluding: %s", metadata.s3_path
            )
            return False

        # Normalize log timestamp to UTC-aware for comparison
        # (metadata.timestamp was validated as non-None above)
        ts = self._to_utc_aware(metadata.timestamp)
        assert ts is not None

        if self.start_date and ts < self.start_date:
            return False
        if self.end_date and ts > self.end_date:
            return False
        return True

    def describe(self) -> str:
        parts = []
        if self.start_date:
            parts.append(f"after {self.start_date.isoformat()}")
        if self.end_date:
            parts.append(f"before {self.end_date.isoformat()}")
        return "date " + " and ".join(parts) if parts else "any date"


class ModelFilter(LogFilter):
    """Filter logs by model name (substring match)."""

    def __init__(self, model_pattern: str):
        self.model_pattern = model_pattern

    def matches(self, metadata: LogMetadata) -> bool:
        if metadata.assigned_model is None:
            logger.warning(
                "Log has no assigned_model metadata, excluding: %s", metadata.s3_path
            )
            return False
        return self.model_pattern in metadata.assigned_model

    def describe(self) -> str:
        return f"model contains: {self.model_pattern}"


class VariationFilter(LogFilter):
    """Filter logs by variation name (exact match)."""

    def __init__(self, variation: str):
        self.variation = variation

    def matches(self, metadata: LogMetadata) -> bool:
        if metadata.variation_name is None:
            logger.warning(
                "Log has no variation_name metadata, excluding: %s", metadata.s3_path
            )
            return False
        return metadata.variation_name == self.variation

    def describe(self) -> str:
        return f"variation == {self.variation}"


class VersionValidityFilter(LogFilter):
    """Filter logs by version validity.

    With the version tracking system removed, this accepts all logs
    that have valid version metadata.
    """

    def matches(self, metadata: LogMetadata) -> bool:
        if metadata.scenario_name is None:
            logger.warning(
                "Log has no scenario_name metadata, excluding: %s", metadata.s3_path
            )
            return False

        if metadata.version is None:
            logger.warning(
                "Log has no version metadata, excluding: %s", metadata.s3_path
            )
            return False

        return True

    def describe(self) -> str:
        return "has valid version metadata"


def read_log_metadata(s3_path: str) -> LogMetadata | None:
    """Read metadata from an eval log file."""
    log = read_eval_log(s3_path, header_only=True)
    return LogMetadata.from_eval_log(s3_path, log)


def prefilter_by_dir_timestamp(
    files: list[str],
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[str]:
    """Pre-filter files by directory timestamp.

    This is a fast filter based on the timestamp in the directory name,
    which avoids reading the actual log files. Files without a parseable
    directory timestamp are included for further filtering by metadata.
    """
    filtered = []
    for f in files:
        dir_ts = extract_dir_timestamp(f)
        if dir_ts is None:
            # Can't determine timestamp from path - include for metadata check
            filtered.append(f)
            continue

        if start_date and dir_ts < start_date:
            continue
        if end_date and dir_ts > end_date:
            continue
        filtered.append(f)
    return filtered


def filter_logs(
    s3_paths: list[str], filters: list[LogFilter], max_workers: int = 16
) -> list[LogMetadata]:
    """Filter logs based on provided filters using parallel processing."""
    matching: list[LogMetadata] = []
    total = len(s3_paths)
    processed = 0
    errors = 0

    def process_one(s3_path: str) -> LogMetadata | None:
        metadata = read_log_metadata(s3_path)
        if metadata is None:
            return None
        if all(f.matches(metadata) for f in filters):
            return metadata
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, p): p for p in s3_paths}

        for future in as_completed(futures):
            processed += 1
            print(
                f"\rScanning logs: {processed}/{total} "
                f"(matched: {len(matching)}, errors: {errors})",
                end="",
                file=sys.stderr,
            )

            try:
                result = future.result()
                if result is not None:
                    matching.append(result)
            except Exception:
                errors += 1

    print(file=sys.stderr)  # Newline after progress
    return matching


class S3LogCrawler:
    """Crawls S3 for evaluation logs."""

    def __init__(
        self,
        bucket: str,
        run_types: list[str] | None = None,
    ):
        self.bucket = bucket
        self.run_types = run_types or ["main-runs", "other-runs"]
        self.s3_client = boto3.client("s3")

    def list_eval_files(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[str]:
        """List all .eval files in the configured S3 paths.

        Args:
            start_date: If provided, pre-filter by directory timestamp >= start_date
            end_date: If provided, pre-filter by directory timestamp <= end_date
        """
        eval_files = []

        for run_type in self.run_types:
            if run_type not in RUN_TYPE_SUBDIRS:
                logger.warning("Unknown run type '%s', skipping", run_type)
                continue

            prefix = f"{S3_LOG_PREFIX}/{RUN_TYPE_SUBDIRS[run_type]}/"
            files = self._list_files_with_prefix(prefix, ".eval")

            # Pre-filter by directory timestamp if date range specified
            if start_date or end_date:
                files = prefilter_by_dir_timestamp(files, start_date, end_date)

            eval_files.extend(files)

        return eval_files

    def _list_files_with_prefix(self, prefix: str, suffix: str) -> list[str]:
        """List all files with given prefix and suffix."""
        files = []
        paginator = self.s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(suffix):
                    files.append(f"s3://{self.bucket}/{key}")

        return files


def sync_to_local(
    s3_paths: list[str], local_dir: str, bucket: str, dry_run: bool = False
) -> None:
    """Sync matching files to local directory using boto3."""
    local_path = Path(local_dir)
    s3_client = boto3.client("s3")

    if not dry_run:
        local_path.mkdir(parents=True, exist_ok=True)

    for s3_path in s3_paths:
        # Extract key from s3://bucket/key format
        if not s3_path.startswith(f"s3://{bucket}/"):
            logger.warning("Unexpected S3 path format: %s", s3_path)
            continue

        key = s3_path[len(f"s3://{bucket}/") :]

        # Create local path preserving directory structure
        rel_path = key.removeprefix(f"{S3_LOG_PREFIX}/")
        dest_path = local_path / rel_path

        if dry_run:
            print(f"Would download: {s3_path} -> {dest_path}")
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloading: {s3_path} -> {dest_path}")
            s3_client.download_file(bucket, key, str(dest_path))


def count_samples_by_model_variation(
    logs: list[LogMetadata],
    count_failures: bool = True,
) -> dict[str, dict[str, int]]:
    """Count samples by (model, scenario/variation) from log metadata.

    Args:
        logs: List of LogMetadata objects
        count_failures: If True, include failed runs in counts (default True)

    Returns:
        Nested dict: model -> "scenario/variation" -> count
        Example: {"claude-sonnet-4-20250514": {"sem_v2/classification": 50}}
    """
    counts: dict[str, dict[str, int]] = {}

    for log in logs:
        # Skip if missing required fields
        if log.assigned_model is None:
            logger.debug("Log missing assigned_model: %s", log.s3_path)
            continue
        if log.scenario_name is None:
            logger.debug("Log missing scenario_name: %s", log.s3_path)
            continue
        if log.variation_name is None:
            logger.debug("Log missing variation_name: %s", log.s3_path)
            continue

        # Skip failed runs if requested
        if not count_failures and log.status != "success":
            continue

        # Build key: "scenario/variation"
        key = f"{log.scenario_name}/{log.variation_name}"

        # Initialize nested dict if needed
        if log.assigned_model not in counts:
            counts[log.assigned_model] = {}
        if key not in counts[log.assigned_model]:
            counts[log.assigned_model][key] = 0

        counts[log.assigned_model][key] += 1

    return counts


def parse_date(date_str: str) -> datetime:
    """Parse ISO format date string."""
    # Try different ISO formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(
        f"Invalid date format: {date_str}. Use ISO format (e.g., 2025-12-01)"
    )


def main(
    scenarios: str | None = None,
    scenario_regex: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    run_type: str = "both",
    output: str | None = None,
    sync_to: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    workers: int = 16,
    verbose: bool = False,
    debug: bool = False,
) -> int:
    """Scan S3 for evaluation logs matching specified criteria.

    Args:
        scenarios: Comma-separated list of scenario names to filter by.
        scenario_regex: Regex pattern for scenario name matching.
        start_date: Start date for filtering (ISO format, e.g., 2025-12-01).
        end_date: End date for filtering (ISO format, e.g., 2025-12-01).
        run_type: Type of runs to search: "main-runs", "other-runs", or "both".
        output: Output file path (default: stdout).
        sync_to: Local directory to sync matching files to.
        dry_run: Show what would be done without actually syncing.
        limit: Limit the number of files to process (for testing).
        workers: Number of parallel workers for reading logs.
        verbose: Enable verbose logging (show INFO and WARNING messages).
        debug: Enable debug logging (show all log messages).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Validate run_type
    if run_type not in ("main-runs", "other-runs", "both"):
        logger.error("run_type must be one of: main-runs, other-runs, both")
        return 1

    # Configure logging based on verbosity
    if debug:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Get bucket from environment
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        logger.error("S3_BUCKET environment variable not set")
        return 1

    # Determine run types
    if run_type == "both":
        run_types = ["main-runs", "other-runs"]
    else:
        run_types = [run_type]

    # Parse dates for pre-filtering
    parsed_start_date = parse_date(start_date) if start_date else None
    parsed_end_date = parse_date(end_date) if end_date else None

    # Build filters
    filters: list[LogFilter] = []

    # Always apply version validity filter
    filters.append(VersionValidityFilter())

    # Scenario filter
    if scenarios:
        scenario_list = [s.strip() for s in scenarios.split(",")]
        filters.append(ScenarioFilter(scenario_list, use_regex=False))
    elif scenario_regex:
        filters.append(ScenarioFilter([scenario_regex], use_regex=True))

    # Date range filter (applied to precise timestamp from log metadata)
    if parsed_start_date or parsed_end_date:
        filters.append(DateRangeFilter(parsed_start_date, parsed_end_date))

    # Print filter summary
    print("Filters:", file=sys.stderr)
    for f in filters:
        print(f"  - {f.describe()}", file=sys.stderr)
    print(file=sys.stderr)

    # Initialize crawler
    crawler = S3LogCrawler(bucket, run_types)

    # List all eval files (with pre-filtering by directory timestamp)
    print("Listing S3 objects...", file=sys.stderr)
    eval_files = crawler.list_eval_files(
        start_date=parsed_start_date, end_date=parsed_end_date
    )
    print(
        f"Found {len(eval_files)} eval files (after directory pre-filter)",
        file=sys.stderr,
    )

    if not eval_files:
        print("No eval files found.", file=sys.stderr)
        return 0

    # Apply limit if specified
    if limit and len(eval_files) > limit:
        print(f"Limiting to first {limit} files", file=sys.stderr)
        eval_files = eval_files[:limit]

    # Filter logs
    print("Filtering logs...", file=sys.stderr)
    matching_logs = filter_logs(eval_files, filters, max_workers=workers)
    print(f"\nFound {len(matching_logs)} matching logs", file=sys.stderr)

    if not matching_logs:
        print("No logs matched the filters.", file=sys.stderr)
        return 0

    # Output results
    s3_paths = [m.s3_path for m in matching_logs]

    if output:
        with open(output, "w") as f:
            for path in s3_paths:
                f.write(path + "\n")
        print(f"Wrote {len(s3_paths)} paths to {output}", file=sys.stderr)
    elif not sync_to:
        # Only print to stdout if not syncing
        for path in s3_paths:
            print(path)

    # Sync if requested
    if sync_to:
        print(f"\nSyncing to {sync_to}...", file=sys.stderr)
        sync_to_local(s3_paths, sync_to, bucket, dry_run=dry_run)
        print("Done.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(fire.Fire(main))
