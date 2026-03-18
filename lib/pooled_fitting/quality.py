"""Quality tracking for pooled regression fits.

Quality levels: ultra (1) < fast (2) < full (3)
The fit command only upgrades quality, never downgrades.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Quality levels
QUALITY_LEVELS = {"ultra": 1, "fast": 2, "full": 3}


def load_quality_metadata(metadata_file: Path) -> dict[str, dict[str, str]]:
    """Load quality metadata from JSON file.

    Args:
        metadata_file: Path to fit_quality.json

    Returns:
        Dict mapping item_id -> {"quality": "ultra"|"fast"|"full", "timestamp": ...}
    """
    if metadata_file.exists():
        with open(metadata_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_quality_metadata(
    metadata: dict[str, dict[str, str]],
    metadata_file: Path,
) -> None:
    """Save quality metadata to JSON file.

    Args:
        metadata: Quality metadata dict
        metadata_file: Path to fit_quality.json
    """
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)


def should_fit(
    item_id: str,
    requested_quality: str,
    metadata: dict[str, dict[str, str]],
) -> tuple[bool, str]:
    """Check if we should fit based on quality upgrade logic.

    Only upgrades, never downgrades.

    Args:
        item_id: Identifier for the fit (model slug, variation name, quartile, etc.)
        requested_quality: "ultra", "fast", or "full"
        metadata: Quality metadata dict

    Returns:
        (should_fit, reason)
    """
    if item_id not in metadata:
        return True, "new_fit"

    item_metadata = metadata[item_id]
    if "quality" not in item_metadata:
        raise ValueError(
            f"Metadata for '{item_id}' missing 'quality' key. Got: {item_metadata}"
        )
    existing_quality = item_metadata["quality"]

    if existing_quality not in QUALITY_LEVELS:
        raise ValueError(
            f"Unknown existing quality '{existing_quality}' for '{item_id}'. "
            f"Valid: {list(QUALITY_LEVELS.keys())}"
        )
    if requested_quality not in QUALITY_LEVELS:
        raise ValueError(
            f"Unknown requested quality '{requested_quality}'. "
            f"Valid: {list(QUALITY_LEVELS.keys())}"
        )

    existing_level = QUALITY_LEVELS[existing_quality]
    requested_level = QUALITY_LEVELS[requested_quality]

    if requested_level > existing_level:
        return True, f"upgrade_{existing_quality}_to_{requested_quality}"
    elif requested_level == existing_level:
        return False, f"already_{existing_quality}"
    else:
        return False, f"no_downgrade_{existing_quality}_to_{requested_quality}"


def update_quality_metadata(
    item_id: str,
    quality: str,
    metadata: dict[str, dict[str, str]],
    metadata_file: Path,
) -> None:
    """Update quality metadata for a completed fit.

    Args:
        item_id: Identifier for the fit
        quality: Quality level achieved
        metadata: Quality metadata dict (will be modified in place)
        metadata_file: Path to save updated metadata
    """
    metadata[item_id] = {
        "quality": quality,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    save_quality_metadata(metadata, metadata_file)


def get_quality_summary(metadata: dict[str, dict[str, str]]) -> dict[str, int]:
    """Get count of items at each quality level.

    Args:
        metadata: Quality metadata dict

    Returns:
        Dict with counts: {"full": N, "fast": N, "ultra": N}
    """
    counts = {"full": 0, "fast": 0, "ultra": 0}
    for info in metadata.values():
        quality = info.get("quality", "unknown")
        if quality in counts:
            counts[quality] += 1
    return counts


def quality_to_mcmc_mode(quality: str) -> str | None:
    """Convert quality level to MCMC mode.

    Args:
        quality: "ultra", "fast", or "full"

    Returns:
        MCMC mode string or None for full
    """
    if quality == "ultra":
        return "ultra"
    elif quality == "fast":
        return "fast"
    else:
        return None  # Full quality uses default MCMC settings
