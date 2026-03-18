"""Aggregate Scout scan results into a listing JSON file.

Workflow:
1. `scout scan` runs the eval awareness classifier, saving results to a scan dir
2. `run_classification.py aggregate --scan-dir ./scans/... --upload` calls this module to:
   - Load scan results from the directory using inspect_scout
   - Build a listing JSON with entries keyed by eval path
   - Merge with existing listing (preserving previous classifications)
   - Save to S3 at eval_awareness_listing.json
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from inspect_scout import scan_results_df

from scripts.transcript_analysis.config import (
    DEFAULT_CLASSIFIER_MODEL,
    S3_BUCKET,
    S3_EVAL_AWARENESS_LISTING,
    S3_LOGS_BASE,
    S3_MOUNT,
)


def load_scan_results(scan_location: str) -> pd.DataFrame:
    """Load scan results from a Scout scan directory."""
    results = scan_results_df(scan_location)

    if "eval_awareness" not in results.scanners:
        raise ValueError(f"No eval_awareness scanner results in {scan_location}")

    return results.scanners["eval_awareness"]


def aggregate_scan_results(scan_dirs: list[str]) -> pd.DataFrame:
    """Aggregate results from multiple scan directories."""
    dfs = []
    for scan_dir in scan_dirs:
        df = load_scan_results(scan_dir)
        dfs.append(df)

    if not dfs:
        raise ValueError("No scan directories provided")

    return pd.concat(dfs, ignore_index=True)


def extract_eval_path_from_transcript_id(transcript_id: str) -> str:
    """Extract the relative eval path from a full transcript ID.

    Scout transcript IDs are typically full paths. We want the relative
    path from the logs base directory. Handles both S3 mount paths and
    local copies that preserve the directory structure (e.g.
    /tmp/.../transcripts/scenario/variation/version/model/file.eval).
    """
    s3_base = str(S3_LOGS_BASE)
    if transcript_id.startswith(s3_base):
        return transcript_id[len(s3_base) :].lstrip("/")

    # For local copies with preserved directory structure, extract the
    # relative path by matching the expected 5-component pattern:
    # scenario/variation/version/model/file.eval
    parts = transcript_id.replace("\\", "/").split("/")
    eval_parts = [p for p in parts if p]
    if len(eval_parts) >= 5 and eval_parts[-1].endswith(".eval"):
        return "/".join(eval_parts[-5:])

    return transcript_id


def build_listing_json(
    df: pd.DataFrame,
    classifier_model: str = DEFAULT_CLASSIFIER_MODEL,
) -> dict[str, Any]:
    """Build the eval awareness listing JSON structure.

    The scanner always produces "YES", "NO", or "UNSURE" as the value.
    Rows with missing values (classifier error) are recorded as "ERROR".
    """
    classified_at = datetime.now(UTC).isoformat()
    entries = {}
    for _, row in df.iterrows():
        source_uri = row["transcript_source_uri"]
        eval_path = extract_eval_path_from_transcript_id(str(source_uri))

        raw_value = row["value"]
        raw_str = str(raw_value)
        if raw_value is None or raw_str in ("<NA>", "None", "nan"):
            eval_awareness = "ERROR"
        elif raw_str in ("YES", "NO", "UNSURE"):
            eval_awareness = raw_str
        else:
            raise ValueError(f"Unexpected scanner value {raw_value!r} for {eval_path}")

        # Extract only_in_thinking from metadata JSON
        metadata_str = row.get("metadata", "{}")
        only_in_thinking = "N/A"
        if metadata_str and pd.notna(metadata_str):
            metadata = json.loads(metadata_str)
            only_in_thinking = metadata.get("only_in_thinking", "N/A")

        transcript_id = str(row["transcript_id"])

        entries[eval_path] = {
            "eval_awareness": eval_awareness,
            "only_in_thinking": only_in_thinking,
            "classified_at": classified_at,
            "transcript_id": transcript_id,
        }

    return _build_listing_from_entries(entries, classifier_model)


def _build_listing_from_entries(
    entries: dict[str, dict[str, Any]],
    classifier_model: str,
) -> dict[str, Any]:
    """Build a full listing structure (metadata + entries + summary) from entries."""
    total = len(entries)
    yes_count = sum(1 for e in entries.values() if e["eval_awareness"] == "YES")
    no_count = sum(1 for e in entries.values() if e["eval_awareness"] == "NO")
    unsure_count = sum(1 for e in entries.values() if e["eval_awareness"] == "UNSURE")

    by_model: dict[str, dict[str, int]] = {}
    by_scenario: dict[str, dict[str, int]] = {}

    for eval_path, entry in entries.items():
        parts = eval_path.split("/")
        if len(parts) < 4:
            raise ValueError(
                f"Unexpected eval path format (expected at least 4 parts): {eval_path}"
            )

        scenario = parts[0]
        model_part = parts[3]

        awareness = entry["eval_awareness"]
        if awareness == "ERROR":
            continue

        if model_part not in by_model:
            by_model[model_part] = {"YES": 0, "NO": 0, "UNSURE": 0}
        by_model[model_part][awareness] += 1

        if scenario not in by_scenario:
            by_scenario[scenario] = {"YES": 0, "NO": 0, "UNSURE": 0}
        by_scenario[scenario][awareness] += 1

    return {
        "metadata": {
            "classifier_model": classifier_model,
            "total_classified": total,
            "last_updated": datetime.now(UTC).isoformat(),
        },
        "entries": entries,
        "summary": {
            "overall": {
                "YES": yes_count,
                "NO": no_count,
                "UNSURE": unsure_count,
                "total": total,
            },
            "by_model": by_model,
            "by_scenario": by_scenario,
        },
    }


def save_listing_json(
    listing: dict[str, Any],
    output_path: Path = S3_EVAL_AWARENESS_LISTING,
) -> None:
    """Save listing JSON to file.

    Writes to a local temp file first, then uploads via `aws s3 cp` to
    bypass the S3 FUSE mount's ~8MB write limit.
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(listing, tmp, indent=2)
        tmp_path = Path(tmp.name)

    try:
        # Convert FUSE mount path to S3 URI and upload via CLI
        s3_key = str(output_path.relative_to(S3_MOUNT))
        s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
        subprocess.run(
            ["aws", "s3", "cp", str(tmp_path), s3_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"Saved listing to {s3_uri}")
    finally:
        tmp_path.unlink(missing_ok=True)


def _read_s3_json(path: Path) -> dict[str, Any]:
    """Read a JSON file from S3, bypassing any filesystem cache.

    If the file is on a mounted S3 filesystem, cached data may be stale when
    files are updated externally. This function downloads via ``aws s3 cp``
    to a temp file to get a fresh read. For local paths, reads directly.
    """
    import subprocess
    import tempfile

    if str(path).startswith(str(S3_MOUNT)):
        s3_key = str(path.relative_to(S3_MOUNT))
        s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            subprocess.run(
                ["aws", "s3", "cp", s3_uri, str(tmp_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            with open(tmp_path) as f:
                return json.load(f)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        with open(path) as f:
            return json.load(f)


def merge_with_existing(
    new_listing: dict[str, Any],
    existing_path: Path = S3_EVAL_AWARENESS_LISTING,
) -> dict[str, Any]:
    """Merge new results with existing listing.

    New results override existing entries for the same eval path.
    """
    if not existing_path.exists():
        return new_listing

    existing = _read_s3_json(existing_path)

    existing_entries: dict[str, Any] = existing["entries"]
    new_entries: dict[str, Any] = new_listing["entries"]
    merged_entries = {**existing_entries, **new_entries}

    classifier_model = new_listing["metadata"]["classifier_model"]
    return _build_listing_from_entries(merged_entries, classifier_model)


def print_summary(listing: dict[str, Any]) -> None:
    """Print a formatted summary of the listing."""
    summary = listing["summary"]
    overall = summary["overall"]

    print("=" * 60)
    print("EVAL AWARENESS CLASSIFICATION RESULTS")
    print("=" * 60)
    print()
    print(f"Total classified: {overall['total']:,}")
    print()
    print("Overall distribution:")
    print(
        f"  YES:    {overall['YES']:,} ({100 * overall['YES'] / overall['total']:.1f}%)"
    )
    print(
        f"  NO:     {overall['NO']:,} ({100 * overall['NO'] / overall['total']:.1f}%)"
    )
    print(
        f"  UNSURE: {overall['UNSURE']:,} ({100 * overall['UNSURE'] / overall['total']:.1f}%)"
    )
    print()
    print("By scenario:")
    for scenario, counts in sorted(summary["by_scenario"].items()):
        total = sum(counts.values())
        yes_pct = 100 * counts["YES"] / total if total > 0 else 0
        print(f"  {scenario}: {total:,} (YES: {yes_pct:.1f}%)")
    print()
    print("By model:")
    for model, counts in sorted(summary["by_model"].items()):
        total = sum(counts.values())
        yes_pct = 100 * counts["YES"] / total if total > 0 else 0
        print(f"  {model}: {total:,} (YES: {yes_pct:.1f}%)")
    print("=" * 60)
