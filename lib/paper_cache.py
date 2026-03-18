"""Paper analysis cache management.

This module manages the sample caching system for paper analysis:
- Raw sample cache (parquet files with scores and parameters)
- S3 sync for sharing cache across machines

Usage:
    from lib.paper_cache import PaperCache

    cache = PaperCache()

    # Load raw samples for a variation
    df = cache.load_samples("agentic_misalignment_v2", "alert")

    # Sync with S3
    cache.sync_from_s3()
    cache.sync_to_s3()
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Local cache directory (relative to repo root)
LOCAL_CACHE_DIR = Path(__file__).parent.parent / "paper_cache"

# S3 prefix for paper cache
S3_CACHE_PREFIX = os.environ.get("PROPENSITY_S3_ROOT", "propensity") + "/paper_cache"


@dataclass
class CacheMetadata:
    """Metadata about the cache state."""

    listing_hash: str  # Hash of listing.json used to build cache
    last_updated: str  # ISO timestamp
    sample_counts: dict[str, dict[str, int]]  # {scenario: {variation: count}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_hash": self.listing_hash,
            "last_updated": self.last_updated,
            "sample_counts": self.sample_counts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CacheMetadata:
        return cls(
            listing_hash=d["listing_hash"],
            last_updated=d["last_updated"],
            sample_counts=d["sample_counts"],
        )


class PaperCache:
    """Manages paper analysis cache with S3 sync."""

    def __init__(
        self,
        local_dir: Path | None = None,
        bucket: str | None = None,
    ):
        """Initialize cache manager.

        Args:
            local_dir: Local cache directory. Defaults to paper_cache/ in repo.
            bucket: S3 bucket name. Defaults to S3_BUCKET env var.
        """
        self.local_dir = local_dir or LOCAL_CACHE_DIR
        self.samples_dir = self.local_dir / "samples"

        # Ensure directories exist
        self.samples_dir.mkdir(parents=True, exist_ok=True)

        # S3 config
        self._bucket = bucket
        self._s3_client = None

    @property
    def bucket(self) -> str:
        """Get S3 bucket, raising if not configured."""
        if self._bucket is None:
            self._bucket = os.environ.get("S3_BUCKET")
        if not self._bucket:
            raise ValueError("S3_BUCKET environment variable not set")
        return self._bucket

    @property
    def s3_client(self):
        """Lazy-load boto3 S3 client."""
        if self._s3_client is None:
            import boto3

            self._s3_client = boto3.client("s3")
        return self._s3_client

    # =========================================================================
    # Sample Cache
    # =========================================================================

    def samples_variation_dir(self, scenario: str, variation: str) -> Path:
        """Get local path for samples directory (per-model parquet files)."""
        return self.samples_dir / scenario / variation

    def load_samples(self, scenario: str, variation: str) -> pd.DataFrame:
        """Load raw samples for a scenario/variation.

        Loads all per-model parquet files and concatenates them.

        Args:
            scenario: Scenario name.
            variation: Variation name.

        Returns:
            DataFrame with columns: eval_file, sample_id, model, score, <params>

        Raises:
            FileNotFoundError: If cache doesn't exist for this combination.
        """
        var_dir = self.samples_variation_dir(scenario, variation)
        if not var_dir.exists():
            raise FileNotFoundError(
                f"No sample cache for {scenario}/{variation}. "
                f"Run scripts/paper/update_sample_cache.py first."
            )

        parquet_files = list(var_dir.glob("samples_*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(
                f"No sample cache for {scenario}/{variation}. "
                f"Run scripts/paper/update_sample_cache.py first."
            )

        dfs = []
        for pf in parquet_files:
            try:
                dfs.append(pd.read_parquet(pf))
            except Exception as e:
                logger.warning(f"Could not read {pf}: {e}")

        if not dfs:
            raise FileNotFoundError(
                f"Could not read any sample files for {scenario}/{variation}."
            )

        return pd.concat(dfs, ignore_index=True)

    def list_cached_variations(self) -> list[tuple[str, str]]:
        """List all (scenario, variation) pairs in sample cache."""
        variations = []
        if not self.samples_dir.exists():
            return variations

        for scenario_dir in self.samples_dir.iterdir():
            if not scenario_dir.is_dir():
                continue
            for variation_dir in scenario_dir.iterdir():
                if not variation_dir.is_dir():
                    continue
                # Check for any samples_*.parquet files
                if list(variation_dir.glob("samples_*.parquet")):
                    variations.append((scenario_dir.name, variation_dir.name))

        return sorted(variations)

    # =========================================================================
    # Metadata
    # =========================================================================

    def metadata_path(self) -> Path:
        """Get path to cache metadata file."""
        return self.local_dir / "cache_metadata.json"

    def load_metadata(self) -> CacheMetadata | None:
        """Load cache metadata, or None if not exists."""
        path = self.metadata_path()
        if not path.exists():
            return None
        with open(path) as f:
            return CacheMetadata.from_dict(json.load(f))

    def save_metadata(self, metadata: CacheMetadata) -> None:
        """Save cache metadata."""
        path = self.metadata_path()
        with open(path, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

    # =========================================================================
    # S3 Sync
    # =========================================================================

    def sync_to_s3(self, dry_run: bool = False) -> int:
        """Upload local cache to S3.

        Args:
            dry_run: If True, just log what would be uploaded.

        Returns:
            Number of files uploaded.
        """
        s3 = self.s3_client
        uploaded = 0

        # Walk local cache and upload all files
        for local_path in self.local_dir.rglob("*"):
            if local_path.is_dir():
                continue

            relative = local_path.relative_to(self.local_dir)
            s3_key = f"{S3_CACHE_PREFIX}/{relative}"

            if dry_run:
                logger.info(f"Would upload: {relative} -> s3://{self.bucket}/{s3_key}")
            else:
                s3.upload_file(str(local_path), self.bucket, s3_key)
                logger.debug(f"Uploaded: {relative}")
                uploaded += 1

        logger.info(f"Uploaded {uploaded} files to S3")
        return uploaded

    def sync_from_s3(self, dry_run: bool = False) -> int:
        """Download S3 cache to local.

        Args:
            dry_run: If True, just log what would be downloaded.

        Returns:
            Number of files downloaded.
        """
        s3 = self.s3_client
        paginator = s3.get_paginator("list_objects_v2")
        downloaded = 0

        for page in paginator.paginate(Bucket=self.bucket, Prefix=S3_CACHE_PREFIX):
            for obj in page.get("Contents", []):
                s3_key = obj["Key"]
                relative = s3_key[len(S3_CACHE_PREFIX) + 1 :]  # Remove prefix
                local_path = self.local_dir / relative

                if dry_run:
                    logger.info(
                        f"Would download: s3://{self.bucket}/{s3_key} -> {relative}"
                    )
                else:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    s3.download_file(self.bucket, s3_key, str(local_path))
                    logger.debug(f"Downloaded: {relative}")
                    downloaded += 1

        logger.info(f"Downloaded {downloaded} files from S3")
        return downloaded


def compute_listing_hash(listing: dict[str, Any]) -> str:
    """Compute hash of listing.json for cache invalidation."""
    # Sort keys for deterministic hashing
    listing_str = json.dumps(listing, sort_keys=True)
    return hashlib.sha256(listing_str.encode()).hexdigest()[:16]
