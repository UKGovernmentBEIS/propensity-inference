"""Model capability rankings for bundling analysis.

This module defines capability rankings for models used in propensity analysis.
Rankings are based on ECI (Elicit Capability Index) and METR benchmarks.
Higher position in the list = more capable model.
"""

import logging

logger = logging.getLogger(__name__)

# Models ranked by capability (most capable first)
# Format: "model_name",  # ECI: X, METR: Ymin (where available)
MODEL_CAPABILITY_RANKING: list[str] = [
    "claude-opus-4-5-20251101",
    "gpt-5.2-2025-12-11",  # Newest GPT-5
    "gemini-3-pro-preview",  # ECI: 154
    "gpt-5.1-2025-11-13",  # ECI: 149, METR: 161.8min
    "gpt-5-pro-2025-10-06",  # ECI: 151
    "gpt-5-2025-08-07",  # ECI: 150, METR: 137.3min
    "claude-sonnet-4-5-20250929",  # ECI: 141, METR: 113.3min
    "grok-4-1-fast-reasoning",
    "grok-4-0709",  # ECI: 147, METR: 110.1min
    "claude-opus-4-1-20250805",  # ECI: 143, METR: 105.5min
    "o3-pro-2025-06-10",
    "o3-2025-04-16",  # ECI: 148, METR: 92.2min
    "claude-opus-4-20250514",  # ECI: 142, METR: 79.9min
    "o4-mini-2025-04-16",  # ECI: 146, METR: 77.6min
    "claude-haiku-4-5-20251001",  # ECI: 142
    "claude-sonnet-4-20250514",  # ECI: 142, METR: 67.7min
    "claude-3-7-sonnet-20250219",  # ECI: 137, METR: 54.2min
    "o1-pro-2025-03-19",
    "gpt-oss-120b",  # METR: 42.0min
    "o1-2024-12-17",  # ECI: 143, METR: 39.2min
    "gemini-2.5-pro-preview",  # ECI: 148, METR: 38.7min
    "gemini-2.5-pro",  # ECI: 146
    "gpt-5-mini-2025-08-07",  # ECI: 144
    "gemini-2.5-flash",  # ECI: 142
    "grok-3",  # ECI: 140
    "gpt-4.1-2025-04-14",  # ECI: 137
    "magistral-medium-2509",
    "mistral-medium-2508",  # ECI: 135
    "llama-4-scout",  # ECI: 130
    "gpt-4o-2024-08-06",  # ECI: 129, METR: 9.2min
    "claude-3-5-haiku-20241022",  # ECI: 127
    "llama-4-maverick",  # ECI: 127
    "llama-3.3-70b-instruct",  # ECI: 127
    "llama-3.1-nemotron-ultra-253b-v1",
]

# Build lookup dict: model name -> rank (0 = most capable)
_MODEL_RANK_LOOKUP: dict[str, int] = {
    model: rank for rank, model in enumerate(MODEL_CAPABILITY_RANKING)
}


def get_model_rank(model_name: str) -> int:
    """Get capability rank for a model (lower = more capable).

    Args:
        model_name: Model name, with or without provider prefix.

    Returns:
        Rank (0 = most capable).

    Raises:
        ValueError: If model is not found in MODEL_CAPABILITY_RANKING.
    """
    # Direct lookup
    if model_name in _MODEL_RANK_LOOKUP:
        return _MODEL_RANK_LOOKUP[model_name]

    # Try without provider prefix (e.g., "anthropic/claude-opus-4-20250514" -> "claude-opus-4-20250514")
    if "/" in model_name:
        base_name = model_name.split("/", 1)[1]
        if base_name in _MODEL_RANK_LOOKUP:
            return _MODEL_RANK_LOOKUP[base_name]

        # Try stripping vendor prefix (e.g., "google_gemini-2.5-pro" -> "gemini-2.5-pro")
        if "_" in base_name:
            stripped_name = base_name.split("_", 1)[1]
            if stripped_name in _MODEL_RANK_LOOKUP:
                return _MODEL_RANK_LOOKUP[stripped_name]

    # Fail loudly for unknown models
    raise ValueError(
        f"Unknown model '{model_name}'. Add it to MODEL_CAPABILITY_RANKING in "
        f"lib/analysis/model_capabilities.py"
    )


def assign_capability_quartile(model_name: str, all_models: list[str]) -> str:
    """Assign a model to a capability quartile.

    Args:
        model_name: Name of the model.
        all_models: List of all unique models in the dataset.

    Returns:
        Quartile label: "q1" (least capable), "q2", "q3", or "q4" (most capable).
    """
    # Get ranks for all models (lower rank = more capable)
    ranked_models = [(m, get_model_rank(m)) for m in all_models]
    ranked_models.sort(key=lambda x: x[1])  # Sort by rank (best first)

    n = len(ranked_models)
    # Find which quartile this model belongs to
    model_rank = get_model_rank(model_name)

    # Find quartile boundaries from the ranked list
    q4_cutoff = ranked_models[n // 4][1]  # Top 25% (most capable)
    q3_cutoff = ranked_models[n // 2][1]  # Top 50%
    q2_cutoff = ranked_models[3 * n // 4][1]  # Top 75%

    if model_rank <= q4_cutoff:
        return "q4"  # Most capable
    elif model_rank <= q3_cutoff:
        return "q3"
    elif model_rank <= q2_cutoff:
        return "q2"
    else:
        return "q1"  # Least capable
