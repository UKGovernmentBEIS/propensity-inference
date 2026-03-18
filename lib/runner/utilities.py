"""Utilities for scenario evaluation runner.

This module provides utilities for:
- Model weight normalization using softmax
- Variance-reduced model allocation
- Multi-model mode setup
- Model-specific configurations
"""

import json
import logging
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

from frozendict import frozendict

from lib.model_configs import MODEL_CONFIGS

logger = logging.getLogger(__name__)


def load_model_configs_from_json(path: str | Path) -> tuple[frozendict[str, Any], ...]:
    """Load model configurations from a JSON file.

    The JSON file should contain a list of model config objects, each with at least:
    - name: Full model name (e.g., "anthropic/claude-opus-4-20250514")
    - weight: Sampling weight (higher = more samples)

    Optional fields:
    - short_name: Display name (defaults to last part of name)
    - lab: Lab/provider name (defaults to "unknown")

    Example JSON:
    [
        {"name": "anthropic/claude-opus-4-20250514", "weight": 1.0, "short_name": "Opus 4", "lab": "anthropic"},
        {"name": "openai/o4-mini-2025-04-16", "weight": 1.0, "short_name": "o4 Mini", "lab": "openai"}
    ]

    Args:
        path: Path to JSON file

    Returns:
        Tuple of frozendict model configurations

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or missing required fields
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model config file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Model config JSON must be a list, got {type(data).__name__}")

    configs = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(
                f"Model config item {i} must be a dict, got {type(item).__name__}"
            )

        # Validate required fields
        if "name" not in item:
            raise ValueError(f"Model config item {i} missing required 'name' field")
        if "weight" not in item:
            raise ValueError(f"Model config item {i} missing required 'weight' field")

        # Build config with defaults
        config = {
            "name": item["name"],
            "weight": float(item["weight"]),
            "short_name": item.get("short_name", item["name"].split("/")[-1]),
            "lab": item.get("lab", "unknown"),
        }
        configs.append(frozendict(config))

    if not configs:
        raise ValueError("Model config file contains no models")

    return tuple(configs)


def normalize_model_weights(
    models: tuple[frozendict[str, Any], ...],
) -> tuple[frozendict[str, Any], ...]:
    """Normalize model weights using linearly.

    Converts weights (e.g., 10, 20) to probabilities that sum to 1.0.

    Args:
        models: Tuple of model config frozendicts with 'weight' field

    Returns:
        Tuple of model configs with normalized weights

    Raises:
        ValueError: If models tuple is empty or weights are invalid
    """
    if not models:
        raise ValueError("Cannot normalize empty models tuple")

    weights = [m["weight"] for m in models]

    total = sum(weights)
    normalised_weights = (w / total for w in weights)

    # Create normalized models
    normalized_models = tuple(
        frozendict({**dict(model), "weight": prob})
        for model, prob in zip(models, normalised_weights)
    )

    # Verify normalization
    total = sum(m["weight"] for m in normalized_models)
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"Normalized weights don't sum to 1.0: {total}")

    return normalized_models


def allocate_models_with_variance_reduction(
    num_samples: int,
    seed: int,
    model_configs: tuple[frozendict[str, Any], ...] | None = None,
) -> list[str]:
    """Allocate models to samples using variance reduction.

    Uses randomized rounding: each model with expected allocation x samples
    receives either floor(x) or ceil(x) samples, maintaining correct expected values.

    Args:
        num_samples: Total number of samples to allocate
        seed: Random seed for reproducibility
        model_configs: Model configurations to use. Defaults to MODEL_CONFIGS from lib/model_configs.py

    Returns:
        List of model names (length = num_samples), shuffled deterministically

    Raises:
        ValueError: If num_samples <= 0
    """
    if num_samples <= 0:
        raise ValueError(f"num_samples must be positive, got {num_samples}")

    # Use provided configs or default
    configs = model_configs if model_configs is not None else MODEL_CONFIGS

    # Normalize weights
    normalized_models = normalize_model_weights(configs)

    rng = random.Random(seed)

    # Compute floor and fractional parts using list comprehension
    allocations = [
        {
            "name": model["name"],
            "floor": (
                floor_count := math.floor(expected := model["weight"] * num_samples)
            ),
            "fractional": expected - floor_count,
        }
        for model in normalized_models
    ]

    # Start with floor allocations
    model_counts = {a["name"]: a["floor"] for a in allocations}

    # Calculate remaining samples to allocate
    remaining = num_samples - sum(model_counts.values())

    # Randomly select which models get +1, weighted by fractional parts
    if remaining > 0:
        fractional_weights = [a["fractional"] for a in allocations]
        # If all fractional weights are zero (perfect division), use uniform weights
        if sum(fractional_weights) == 0:
            fractional_weights = [1.0] * len(allocations)
        selected_indices = rng.choices(
            range(len(allocations)), weights=fractional_weights, k=remaining
        )
        for idx in selected_indices:
            model_counts[allocations[idx]["name"]] += 1

    # Verify we allocated exactly num_samples
    total_allocated = sum(model_counts.values())
    assert total_allocated == num_samples, (
        f"Allocation error: allocated {total_allocated} samples instead of {num_samples}"
    )

    # Create list of model assignments
    model_assignments = []
    for model_name, count in model_counts.items():
        model_assignments.extend([model_name] * count)

    # Shuffle to randomize order (but deterministically with seed)
    rng.shuffle(model_assignments)

    return model_assignments


def setup_multi_model_mode(
    num_samples: int,
    seed: int,
    model_configs: tuple[frozendict[str, Any], ...] | None = None,
) -> tuple[list[str], tuple[frozendict[str, Any], ...]]:
    """Set up multi-model mode with variance-reduced allocation.

    Allocates models to samples and logs allocation statistics.

    Args:
        num_samples: Total number of samples to allocate
        seed: Random seed for reproducibility
        model_configs: Model configurations to use. Defaults to MODEL_CONFIGS from lib/model_configs.py

    Returns:
        Tuple of (model_assignments, normalized_model_configs)
        - model_assignments: List of model names for each sample
        - normalized_model_configs: Tuple of normalized model configs

    Raises:
        ValueError: If num_samples <= 0
    """
    # Use provided configs or default
    configs = model_configs if model_configs is not None else MODEL_CONFIGS

    # Normalize weights and allocate models
    normalized_models = normalize_model_weights(configs)
    model_assignments = allocate_models_with_variance_reduction(
        num_samples, seed, configs
    )

    # Log multi-model setup
    logger.info("=" * 60)
    logger.info("Multi-model sampling enabled")
    logger.info("=" * 60)
    logger.info(f"Total models: {len(normalized_models)}")

    # Count allocations per model
    allocation_counts = Counter(model_assignments)
    logger.info(f"Allocation (num_samples={num_samples}):")

    # Sort by count (descending)
    for model_name in sorted(
        allocation_counts.keys(),
        key=lambda m: allocation_counts[m],
        reverse=True,
    ):
        count = allocation_counts[model_name]
        model_info = next(m for m in normalized_models if m["name"] == model_name)
        expected = model_info["weight"] * num_samples
        short_name = model_info.get("short_name", model_name.split("/")[-1])
        logger.info(
            f"  {short_name:20s} ({model_info['lab']:9s}): "
            f"{count:3d} samples (expected: {expected:5.2f})"
        )

    return model_assignments, normalized_models
