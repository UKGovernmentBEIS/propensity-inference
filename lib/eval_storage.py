"""Eval storage utilities for structured S3 hierarchy.

This module is the single source of truth for S3 eval operations. Use the
high-level API for most tasks - it handles defaults and reduces boilerplate.

Storage path format:
    s3://<bucket>/<prefix>/evals/<scenario>/<variation>/<version>/<model>/<filename>.eval

High-Level API (recommended):
    from lib.eval_storage import list_evals, load_evals, upload_eval, upload_evals

    # Query evals (auto-fetches min_version, excludes entropy files)
    paths = list_evals("agentic_misalignment_v2", "alert", model="openai/o4-mini")

    # Query and load in one call
    logs = load_evals("agentic_misalignment_v2", "alert", header_only=True)

    # Upload a single eval
    upload_eval("logs/abc.eval", scenario="...", variation="...", version="...", model="...")

    # Upload all evals from a directory (extracts metadata automatically)
    upload_evals("logs/2025-01-15T10-00-00/")

Lower-Level API (for custom queries):
    from lib.eval_storage import list_eval_files, EvalStoragePath

    # Iterate over matching files
    for path in list_eval_files(scenario="...", variation="...", min_version="15.0.0"):
        print(path.s3_uri(bucket))
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from inspect_ai._util.file import filesystem
from packaging.version import Version

from lib.model_registry import api_name_to_s3_name, s3_name_to_api_name

if TYPE_CHECKING:
    from inspect_ai.log import EvalLog

logger = logging.getLogger(__name__)

# Cached S3 client (avoid recreating per function call)
_s3_client: Any = None


def get_s3_client() -> Any:
    """Get cached boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


# S3 prefix for structured eval storage
# Note: includes /logs prefix by convention
EVALS_PREFIX = os.environ.get("EVALS_S3_PREFIX", "/logs")


@dataclass
class EvalStoragePath:
    """Represents a structured path in the eval storage hierarchy.

    Path format:
        evals/<scenario>/<variation>/<version>/<model>/[<subdir>/]<filename>.eval

    This enables fast prefix-based queries by scenario, variation, version, and model.
    """

    scenario: str
    variation: str
    version: str
    model_api_name: str  # e.g., "openai/o4-mini-2025-04-16"
    filename: str  # e.g., "abc123.eval"
    subdir: str | None = None  # e.g., "entropy" for entropy estimation files

    @property
    def model_s3_name(self) -> str:
        """S3-safe model name."""
        return api_name_to_s3_name(self.model_api_name)

    @property
    def s3_key(self) -> str:
        """Full S3 key (without bucket)."""
        if self.subdir:
            return f"{EVALS_PREFIX}/{self.scenario}/{self.variation}/{self.version}/{self.model_s3_name}/{self.subdir}/{self.filename}"
        return f"{EVALS_PREFIX}/{self.scenario}/{self.variation}/{self.version}/{self.model_s3_name}/{self.filename}"

    def s3_uri(self, bucket: str) -> str:
        """Full S3 URI."""
        return f"s3://{bucket}/{self.s3_key}"

    @classmethod
    def from_s3_key(cls, key: str) -> EvalStoragePath:
        """Parse an S3 key into components.

        Args:
            key: S3 key like "evals/scenario/variation/version/model/file.eval"

        Returns:
            EvalStoragePath with parsed components.

        Raises:
            ValueError: If key doesn't match expected structure.
        """
        # Handle both prefixed and non-prefixed keys
        if key.startswith(EVALS_PREFIX + "/"):
            key = key[len(EVALS_PREFIX) + 1 :]

        parts = key.split("/")
        if len(parts) < 5:
            raise ValueError(
                f"Invalid eval storage key: {key}. "
                f"Expected: <scenario>/<variation>/<version>/<model>/<filename>"
            )

        return cls(
            scenario=parts[0],
            variation=parts[1],
            version=parts[2],
            model_api_name=s3_name_to_api_name(parts[3]),
            filename="/".join(parts[4:]),  # Handle nested filenames
        )


def get_bucket() -> str:
    """Get S3 bucket from environment.

    Returns:
        Bucket name from S3_BUCKET env var.

    Raises:
        ValueError: If env var not set.
    """
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET environment variable not set")
    return bucket


def _extract_version_base(version: str) -> str:
    """Extract base version, stripping dev suffixes.

    Converts "15.0.1.dev1+g2399e30f4.d20251217" to "15.0.1".
    """
    if ".dev" in version:
        return version.split(".dev")[0]
    if "+" in version:
        return version.split("+")[0]
    return version


# =============================================================================
# High-Level API (preferred for most use cases)
# =============================================================================


def list_evals(
    scenario: str,
    variation: str,
    model: str | None = None,
    min_version: str | None = None,
    bucket: str | None = None,
    exclude_entropy: bool = True,
    subdir: str | None = None,
) -> list[EvalStoragePath]:
    """Query eval files with sensible defaults.

    This is the recommended way to query evals. It auto-fetches
    min_version from version tracking if not provided.

    Args:
        scenario: Scenario name.
        variation: Variation name.
        model: Model API name to filter by (optional).
        min_version: Minimum version (auto-fetched if None).
        bucket: S3 bucket (defaults to env var).
        exclude_entropy: Exclude files in /entropy/ subdirectory (default True).
            Ignored if subdir is specified.
        subdir: If provided, only include files in this subdirectory (e.g., "entropy").
            When set, exclude_entropy is ignored.

    Returns:
        List of EvalStoragePath objects.

    Example:
        # Regular evals (excludes entropy by default)
        paths = list_evals("agentic_misalignment_v2", "alert", model="openai/o4-mini")

        # Entropy samples only
        paths = list_evals("agentic_misalignment_v2", "alert", model="...", subdir="entropy")
    """
    bucket = bucket or get_bucket()

    # Default to accepting all versions if not specified
    if min_version is None:
        min_version = "0.0.0"

    # Use the lower-level iterator and collect results
    paths = []
    for path in list_eval_files(
        scenario=scenario,
        variation=variation,
        model=model,
        min_version=min_version,
        bucket=bucket,
    ):
        # If subdir specified, only include files in that subdirectory
        if subdir:
            if path.subdir == subdir:
                paths.append(path)
        else:
            # Filter out entropy files if requested
            if exclude_entropy and path.subdir == "entropy":
                continue
            paths.append(path)

    return paths


def count_evals(
    scenario: str,
    variation: str,
    model: str | None = None,
    min_version: str | None = None,
    bucket: str | None = None,
    exclude_entropy: bool = True,
    status_filter: str | None = "success",
) -> int:
    """Count eval files matching criteria.

    Convenience function that queries and counts evals, optionally filtering
    by status. Useful for checking how many samples exist before running more.

    Args:
        scenario: Scenario name.
        variation: Variation name.
        model: Model API name to filter by (optional).
        min_version: Minimum version (auto-fetched if None).
        bucket: S3 bucket (defaults to env var).
        exclude_entropy: Exclude files in /entropy/ subdirectory (default True).
        status_filter: Only count evals with this status (default "success").
            Set to None to count all statuses.

    Returns:
        Number of matching eval files.

    Example:
        n = count_evals("agentic_misalignment_v2", "alert", model="openai/o4-mini")
    """
    bucket = bucket or get_bucket()
    paths = list_evals(
        scenario=scenario,
        variation=variation,
        model=model,
        min_version=min_version,
        bucket=bucket,
        exclude_entropy=exclude_entropy,
    )

    if not paths:
        return 0

    # If no status filter, just return the count
    if status_filter is None:
        return len(paths)

    # Read headers in parallel to check status
    s3_uris = [p.s3_uri(bucket) for p in paths]
    log_results = read_eval_logs_parallel(
        s3_uris, header_only=True, show_progress=False
    )

    count = 0
    for _uri, log in log_results:
        if log is not None and log.status == status_filter:
            count += 1

    return count


def load_evals(
    scenario: str,
    variation: str,
    model: str | None = None,
    min_version: str | None = None,
    header_only: bool = False,
    max_workers: int = 32,
    bucket: str | None = None,
) -> list[EvalLog]:
    """Query and load evals in one call.

    This combines list_evals() + read_eval_logs_parallel() for convenience.

    Args:
        scenario: Scenario name.
        variation: Variation name.
        model: Model API name to filter by (optional).
        min_version: Minimum version (auto-fetched if None).
        header_only: If True, only read headers (faster).
        max_workers: Number of parallel workers.
        bucket: S3 bucket (defaults to env var).

    Returns:
        List of EvalLog objects (excludes failed reads).

    Example:
        logs = load_evals("agentic_misalignment_v2", "alert", header_only=True)
    """
    bucket = bucket or get_bucket()

    # Query
    paths = list_evals(
        scenario=scenario,
        variation=variation,
        model=model,
        min_version=min_version,
        bucket=bucket,
    )

    if not paths:
        return []

    # Convert to URIs and read
    uris = [p.s3_uri(bucket) for p in paths]
    results = read_eval_logs_parallel(
        uris,
        header_only=header_only,
        max_workers=max_workers,
        show_progress=True,
    )

    # Return only successful reads
    return [log for _, log in results if log is not None]


def upload_eval(
    local_path: Path | str,
    scenario: str,
    variation: str,
    version: str,
    model: str,
    bucket: str | None = None,
    subdir: str | None = None,
) -> EvalStoragePath:
    """Upload a single eval to structured storage.

    Args:
        local_path: Path to local .eval file.
        scenario: Scenario name.
        variation: Variation name.
        version: Version string (dev suffixes will be stripped).
        model: Model API name.
        bucket: S3 bucket (defaults to env var).
        subdir: Optional subdirectory (e.g., "entropy").

    Returns:
        EvalStoragePath of uploaded file.

    Example:
        path = upload_eval(
            "logs/abc.eval",
            scenario="agentic_misalignment_v2",
            variation="alert",
            version="15.0.1",
            model="openai/o4-mini",
        )
    """
    bucket = bucket or get_bucket()
    local_path = Path(local_path)

    # Strip dev suffix from version
    base_version = _extract_version_base(version)

    # Add random suffix to filename to ensure uniqueness across runs
    random_suffix = uuid.uuid4().hex[:12]
    unique_filename = f"{local_path.stem}_{random_suffix}.eval"

    # Build storage path
    storage_path = EvalStoragePath(
        scenario=scenario,
        variation=variation,
        version=base_version,
        model_api_name=model,
        filename=unique_filename,
    )

    # Adjust key if subdir specified
    if subdir:
        model_s3 = api_name_to_s3_name(model)
        s3_key = f"{EVALS_PREFIX}/{scenario}/{variation}/{base_version}/{model_s3}/{subdir}/{unique_filename}"
    else:
        s3_key = storage_path.s3_key

    target_uri = f"s3://{bucket}/{s3_key}"

    # Upload
    s3_fs = filesystem(f"s3://{bucket}")
    s3_fs.put_file(str(local_path), target_uri)
    logger.debug(f"Uploaded: {s3_key}")

    return storage_path


def upload_evals(
    local_dir: Path | str,
    bucket: str | None = None,
) -> int:
    """Upload all evals from a directory, extracting metadata from each.

    Reads each .eval file to extract scenario, variation, version, and model
    from the log metadata, then uploads to the appropriate structured path.

    Args:
        local_dir: Directory containing .eval files.
        bucket: S3 bucket (defaults to env var).

    Returns:
        Number of files uploaded.

    Raises:
        ValueError: If required metadata is missing from any eval.

    Example:
        count = upload_evals("logs/2025-01-15T10-00-00/")
    """
    from inspect_ai.log import read_eval_log

    bucket = bucket or get_bucket()
    local_dir = Path(local_dir)

    eval_files = list(local_dir.rglob("*.eval"))
    if not eval_files:
        logger.warning(f"No .eval files found in {local_dir}")
        return 0

    for eval_file in eval_files:
        # Read metadata
        log = read_eval_log(str(eval_file), header_only=True)
        metadata = log.eval.metadata or {}

        scenario = metadata.get("scenario_name")
        variation = metadata.get("variation_name")
        version = metadata.get("version")
        model = log.eval.model

        # Validate required fields
        if not scenario:
            raise ValueError(f"Missing scenario_name in {eval_file.name}")
        if not variation:
            raise ValueError(f"Missing variation_name in {eval_file.name}")
        if not version:
            raise ValueError(f"Missing version in {eval_file.name}")

        # Upload
        result = upload_eval(
            local_path=eval_file,
            scenario=scenario,
            variation=variation,
            version=version,
            model=model,
            bucket=bucket,
        )
        logger.info(f"  Uploaded: {result.s3_key}")

    logger.info(f"Uploaded {len(eval_files)} files")
    return len(eval_files)


def update_evals_listing(bucket: str | None = None) -> int:
    """Update the listing.json for the evals bundle with any new files.

    This function incrementally updates the listing.json in S3 by:
    1. Loading existing listing.json
    2. Scanning S3 for all eval files
    3. Adding entries for any files not in the listing
    4. Writing updated listing.json back to S3

    Args:
        bucket: S3 bucket name (defaults to env var).

    Returns:
        Number of new entries added to listing.

    Example:
        added = update_evals_listing()
        print(f"Added {added} new entries to listing.json")
    """
    import json
    import tempfile

    from inspect_ai._util.file import filesystem
    from inspect_ai.log._file import read_eval_log, to_overview

    bucket = bucket or get_bucket()
    logs_dir = f"s3://{bucket}/{EVALS_PREFIX}"
    evals_base = logs_dir.rsplit("/logs", 1)[0]
    listing_path = f"{logs_dir}/listing.json"

    fs = filesystem(evals_base)

    # Load existing listing
    existing_listing: dict[str, dict[str, Any]] = {}
    try:
        with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        fs.get_file(listing_path, tmp_path)
        with open(tmp_path, "r") as f:
            existing_listing = json.load(f)
        Path(tmp_path).unlink()
        logger.info(f"Loaded existing listing with {len(existing_listing)} entries")
    except Exception as e:
        logger.warning(f"Could not load existing listing: {e}")
        existing_listing = {}

    # List all eval files in S3 using paginator
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    prefix = f"{EVALS_PREFIX}/"

    all_eval_keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".eval"):
                all_eval_keys.append(key)

    logger.info(f"Found {len(all_eval_keys)} total eval files in S3")

    # Find files not in listing
    files_to_process: list[tuple[str, str]] = []  # (rel_path, s3_uri)
    for s3_key in all_eval_keys:
        # Compute relative path from EVALS_PREFIX (logs/) directory
        # Key format: <EVALS_S3_PREFIX>/<scenario>/<variation>/<version>/<model>/<filename>
        rel_path = s3_key[len(prefix) :]  # Remove prefix to get relative path

        if rel_path not in existing_listing:
            s3_uri = f"s3://{bucket}/{s3_key}"
            files_to_process.append((rel_path, s3_uri))

    if not files_to_process:
        logger.info("No new entries to add to listing")
        return 0

    logger.info(f"Processing {len(files_to_process)} new files in parallel...")

    def process_one(item: tuple[str, str]) -> tuple[str, dict[str, Any] | None]:
        rel_path, s3_uri = item
        try:
            log_header = read_eval_log(s3_uri, header_only=True)
            overview = to_overview(log_header)
            return (rel_path, overview.model_dump(exclude_none=True))
        except Exception as e:
            logger.warning(f"Could not read {rel_path}: {e}")
            return (rel_path, None)

    new_entries: dict[str, dict[str, Any]] = {}
    completed = 0
    max_workers = 32

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_one, item): item for item in files_to_process
        }

        for future in as_completed(futures):
            rel_path, entry = future.result()
            if entry is not None:
                new_entries[rel_path] = entry
            completed += 1

            if completed % 100 == 0:
                logger.info(f"  Progress: {completed}/{len(files_to_process)}")

    if not new_entries:
        logger.info("No new entries to add to listing")
        return 0

    # Update and write listing
    existing_listing.update(new_entries)
    listing_json = json.dumps(existing_listing, indent=2)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp_file:
        tmp_file.write(listing_json)
        tmp_file_path = tmp_file.name

    try:
        fs.put_file(tmp_file_path, listing_path)
    finally:
        Path(tmp_file_path).unlink()

    logger.info(f"Added {len(new_entries)} new entries to listing")
    return len(new_entries)


# =============================================================================
# Lower-Level Query Functions
# =============================================================================


def list_versions(
    scenario: str,
    variation: str,
    bucket: str | None = None,
    min_version: str | None = None,
) -> list[str]:
    """List all versions for a scenario/variation, optionally filtered.

    Args:
        scenario: Scenario name.
        variation: Variation name.
        bucket: S3 bucket name (defaults to env var).
        min_version: If provided, only return versions >= this.

    Returns:
        List of version strings, sorted newest first.
    """
    bucket = bucket or get_bucket()
    s3 = get_s3_client()

    # List "directories" under evals/<scenario>/<variation>/
    prefix = f"{EVALS_PREFIX}/{scenario}/{variation}/"
    result = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    versions = []
    min_ver = Version(min_version) if min_version else None

    for prefix_obj in result.get("CommonPrefixes", []):
        # Extract version from "evals/scenario/variation/version/"
        version_str = prefix_obj["Prefix"].rstrip("/").split("/")[-1]

        # Filter by min_version if specified
        if min_ver:
            try:
                if Version(version_str) < min_ver:
                    continue
            except Exception:
                # Skip invalid versions
                continue

        versions.append(version_str)

    # Sort newest first
    return sorted(versions, key=lambda v: Version(v), reverse=True)


def list_models(
    scenario: str,
    variation: str,
    version: str,
    bucket: str | None = None,
) -> list[str]:
    """List all models for a scenario/variation/version.

    Args:
        scenario: Scenario name.
        variation: Variation name.
        version: Version string.
        bucket: S3 bucket name (defaults to env var).

    Returns:
        List of model API names.
    """
    bucket = bucket or get_bucket()
    s3 = get_s3_client()

    # List "directories" under evals/<scenario>/<variation>/<version>/
    prefix = f"{EVALS_PREFIX}/{scenario}/{variation}/{version}/"
    result = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    models = []
    for prefix_obj in result.get("CommonPrefixes", []):
        # Extract model s3_name from path
        model_s3_name = prefix_obj["Prefix"].rstrip("/").split("/")[-1]
        models.append(s3_name_to_api_name(model_s3_name))

    return sorted(models)


def list_eval_files(
    scenario: str,
    variation: str,
    model: str | None = None,
    version: str | None = None,
    min_version: str | None = None,
    bucket: str | None = None,
) -> Iterator[EvalStoragePath]:
    """List eval files with flexible filtering.

    Path format: evals/<scenario>/<variation>/<version>/<model>/<filename>

    This is the main query function. It supports:
    - Exact version match
    - Version range (>= min_version)
    - Model filtering
    - All combinations thereof

    Args:
        scenario: Scenario name (required).
        variation: Variation name (required).
        model: Model API name to filter by (optional).
        version: Exact version to query (optional).
        min_version: Minimum version for range query (optional).
        bucket: S3 bucket name (defaults to env var).

    Yields:
        EvalStoragePath for each matching eval file.

    Example:
        # All o4-mini evals for agentic_misalignment_v2/alert, version >= 15.0.0
        for path in list_eval_files(
            scenario="agentic_misalignment_v2",
            variation="alert",
            model="openai/o4-mini-2025-04-16",
            min_version="15.0.0",
        ):
            print(path.s3_uri(bucket))
    """
    bucket = bucket or get_bucket()
    s3 = get_s3_client()

    # Determine which versions to query
    if version:
        versions = [version]
    else:
        versions = list_versions(scenario, variation, bucket, min_version)

    # For each version, list matching files
    for ver in versions:
        if model:
            # Direct query for specific model
            model_s3_name = api_name_to_s3_name(model)
            prefix = f"{EVALS_PREFIX}/{scenario}/{variation}/{ver}/{model_s3_name}/"
            yield from _list_files_at_prefix(
                s3, bucket, prefix, scenario, variation, ver, model
            )
        else:
            # List all models for this version
            model_names = list_models(scenario, variation, ver, bucket)
            for model_name in model_names:
                model_s3_name = api_name_to_s3_name(model_name)
                prefix = f"{EVALS_PREFIX}/{scenario}/{variation}/{ver}/{model_s3_name}/"
                yield from _list_files_at_prefix(
                    s3, bucket, prefix, scenario, variation, ver, model_name
                )


def _list_files_at_prefix(
    s3,
    bucket: str,
    prefix: str,
    scenario: str,
    variation: str,
    version: str,
    model: str,
) -> Iterator[EvalStoragePath]:
    """List all .eval files at a specific prefix.

    Uses pagination to handle large result sets.
    Handles both direct files and files in subdirectories (e.g., entropy/).
    """
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".eval"):
                # Extract relative path after the model prefix
                relative = key[
                    len(prefix) :
                ]  # e.g., "file.eval" or "entropy/file.eval"
                parts = relative.split("/")

                if len(parts) == 1:
                    # Direct file: model/file.eval
                    filename = parts[0]
                    subdir = None
                else:
                    # Subdirectory: model/subdir/file.eval
                    subdir = parts[0]
                    filename = parts[-1]

                yield EvalStoragePath(
                    scenario=scenario,
                    variation=variation,
                    version=version,
                    model_api_name=model,
                    filename=filename,
                    subdir=subdir,
                )


# =============================================================================
# Parallel S3 Reading Utilities
# =============================================================================


def read_eval_logs_parallel(
    s3_uris: list[str],
    *,
    header_only: bool = False,
    max_workers: int = 32,
    show_progress: bool = True,
) -> list[tuple[str, EvalLog | None]]:
    """Read multiple eval logs from S3 in parallel.

    Args:
        s3_uris: List of S3 URIs to read.
        header_only: If True, only read headers (faster).
        max_workers: Number of parallel workers.
        show_progress: Log progress every 100 files.

    Returns:
        List of (s3_uri, EvalLog | None) tuples. None if reading failed.
    """
    from inspect_ai.log import read_eval_log

    if not s3_uris:
        return []

    def read_one(uri: str) -> tuple[str, EvalLog | None]:
        try:
            log = read_eval_log(uri, header_only=header_only)
            return (uri, log)
        except Exception as e:
            logger.warning(f"Failed to read {uri}: {e}")
            return (uri, None)

    results: list[tuple[str, EvalLog | None]] = []
    completed = 0

    logger.info(
        f"Reading {len(s3_uris)} eval files in parallel "
        f"(header_only={header_only}, workers={max_workers})..."
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(read_one, uri): uri for uri in s3_uris}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1

            if show_progress and completed % 100 == 0:
                logger.info(f"  Progress: {completed}/{len(s3_uris)}")

    logger.info(
        f"Read {sum(1 for _, log in results if log is not None)} files successfully"
    )
    return results


def process_eval_logs_parallel[T](
    s3_uris: list[str],
    processor: Callable[[EvalLog], T | None],
    *,
    header_only: bool = False,
    max_workers: int = 32,
    show_progress: bool = True,
) -> list[T]:
    """Read and process eval logs in parallel.

    Args:
        s3_uris: List of S3 URIs to read.
        processor: Function that takes an EvalLog and returns a result (or None to skip).
        header_only: If True, only read headers.
        max_workers: Number of parallel workers.
        show_progress: Log progress.

    Returns:
        List of non-None processor results.
    """
    from inspect_ai.log import read_eval_log

    if not s3_uris:
        return []

    def read_and_process(uri: str) -> T | None:
        try:
            log = read_eval_log(uri, header_only=header_only)
            return processor(log)
        except Exception as e:
            logger.warning(f"Failed to process {uri}: {e}")
            return None

    results: list[T] = []
    completed = 0

    logger.info(
        f"Processing {len(s3_uris)} eval files in parallel (workers={max_workers})..."
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(read_and_process, uri): uri for uri in s3_uris}

        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
            completed += 1

            if show_progress and completed % 100 == 0:
                logger.info(f"  Progress: {completed}/{len(s3_uris)}")

    logger.info(f"Processed {len(results)} files successfully")
    return results
