"""Model registry - single source of truth for model metadata.

This module provides:
- Model name conversion: api_name_to_s3_name, s3_name_to_api_name
- Model metadata reference: MODEL_REGISTRY list

Note: We still have lib/model_configs.py; I keep it since it's being used for
    run_scenarios.py sample
even though it'd be ideal to use the same setup for that. We should use this file for
anything new (and add fields to this file in case they are not currently sufficient).

Usage:
    from lib.model_registry import api_name_to_s3_name, s3_name_to_api_name

    # Convert API name to S3-safe name
    s3_name = api_name_to_s3_name("openai/o4-mini-2025-04-16")
    # Returns: "openai_o4-mini-2025-04-16"

    # Convert back to API name
    api_name = s3_name_to_api_name("openai_o4-mini-2025-04-16")
    # Returns: "openai/o4-mini-2025-04-16"
"""

from dataclasses import dataclass
from typing import Literal

Provider = Literal["openai", "anthropic", "google", "xai", "meta", "mistral", "other"]


@dataclass(frozen=True)
class ModelInfo:
    """Complete metadata for a model."""

    # Unique identifier (short, human-readable): "o4-mini", "claude-sonnet-4-5"
    id: str

    # Full API name for evaluation: "openai/o4-mini-2025-04-16"
    api_name: str

    # Display name for reports/plots: "o4 Mini"
    display_name: str

    # Provider/lab
    provider: Provider

    # Capability rank (0 = most capable, higher = less capable)
    capability_rank: int

    # Cost per 1M input tokens in USD (None if unknown)
    input_cost: float | None = None

    # Cost per 1M output tokens in USD (None if unknown)
    output_cost: float | None = None

    @property
    def s3_name(self) -> str:
        """S3-safe name: replaces '/' with '_'."""
        return self.api_name.replace("/", "_")

    @property
    def base_name(self) -> str:
        """Model name without provider prefix."""
        if "/" in self.api_name:
            return self.api_name.split("/", 1)[1]
        return self.api_name


# =============================================================================
# MODEL REGISTRY
# =============================================================================
# Models ordered by capability (most capable first).
# This list is the single source of truth for all model metadata.
#
# Cost notes:
# - Costs are per 1M tokens in USD
# - For tiered pricing (e.g., Gemini), we use the lower tier (prompts <= 200k)
# - None indicates pricing not yet added (marked with TODO comments)
# - OpenAI and xAI pricing pages seem to block Claude / curl so you have to do them by hand

MODEL_REGISTRY: list[ModelInfo] = [
    # OpenAI - https://platform.openai.com/docs/pricing/
    ModelInfo(
        id="gpt-5.2",
        api_name="openai/gpt-5.2-2025-12-11",
        display_name="GPT 5.2",
        provider="openai",
        capability_rank=0,
        input_cost=1.75,  # https://platform.openai.com/docs/pricing/
        output_cost=14.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="gpt-5-pro",
        api_name="openai/gpt-5-pro-2025-10-06",
        display_name="GPT 5 Pro",
        provider="openai",
        capability_rank=2,
        input_cost=15.00,  # https://platform.openai.com/docs/pricing/
        output_cost=120.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="gpt-5",
        api_name="openai/gpt-5-2025-08-07",
        display_name="GPT 5",
        provider="openai",
        capability_rank=3,
        input_cost=1.25,  # https://platform.openai.com/docs/pricing/
        output_cost=10.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="o3-pro",
        api_name="openai/o3-pro-2025-06-10",
        display_name="o3 Pro",
        provider="openai",
        capability_rank=5,
        input_cost=20.00,  # https://platform.openai.com/docs/pricing/
        output_cost=80.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="o3",
        api_name="openai/o3-2025-04-16",
        display_name="o3",
        provider="openai",
        capability_rank=6,
        input_cost=2.00,  # https://platform.openai.com/docs/pricing/
        output_cost=8.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="o4-mini",
        api_name="openai/o4-mini-2025-04-16",
        display_name="o4 Mini",
        provider="openai",
        capability_rank=8,
        input_cost=1.10,  # https://platform.openai.com/docs/pricing/
        output_cost=4.40,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="o1",
        api_name="openai/o1-2024-12-17",
        display_name="o1",
        provider="openai",
        capability_rank=14,
        input_cost=15.00,  # https://platform.openai.com/docs/pricing/
        output_cost=60.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="gpt-5-mini",
        api_name="openai/gpt-5-mini-2025-08-07",
        display_name="GPT 5 Mini",
        provider="openai",
        capability_rank=17,
        input_cost=0.25,  # https://platform.openai.com/docs/pricing/
        output_cost=2.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="gpt-4.1",
        api_name="openai/gpt-4.1-2025-04-14",
        display_name="GPT 4.1",
        provider="openai",
        capability_rank=22,
        input_cost=2.00,  # https://platform.openai.com/docs/pricing/
        output_cost=8.00,  # https://platform.openai.com/docs/pricing/
    ),
    ModelInfo(
        id="gpt-4o",
        api_name="openai/gpt-4o-2024-08-06",
        display_name="GPT 4o",
        provider="openai",
        capability_rank=25,
        input_cost=2.50,  # https://platform.openai.com/docs/pricing/
        output_cost=10.00,  # https://platform.openai.com/docs/pricing/
    ),
    # Anthropic - https://platform.claude.com/docs/en/about-claude/pricing
    ModelInfo(
        id="claude-opus-4-5",
        api_name="anthropic/claude-opus-4-5-20251101",
        display_name="Claude Opus 4.5",
        provider="anthropic",
        capability_rank=3,
        input_cost=5.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=25.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-sonnet-4-5",
        api_name="anthropic/claude-sonnet-4-5-20250929",
        display_name="Claude Sonnet 4.5",
        provider="anthropic",
        capability_rank=4,
        input_cost=3.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=15.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-opus-4-1",
        api_name="anthropic/claude-opus-4-1-20250805",
        display_name="Claude Opus 4.1",
        provider="anthropic",
        capability_rank=7,
        input_cost=15.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=75.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-opus-4",
        api_name="anthropic/claude-opus-4-20250514",
        display_name="Claude Opus 4",
        provider="anthropic",
        capability_rank=9,
        input_cost=15.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=75.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-haiku-4-5",
        api_name="anthropic/claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        provider="anthropic",
        capability_rank=10,
        input_cost=1.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=5.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-sonnet-4",
        api_name="anthropic/claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        provider="anthropic",
        capability_rank=11,
        input_cost=3.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=15.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-3-7-sonnet",
        api_name="anthropic/claude-3-7-sonnet-20250219",
        display_name="Claude 3.7 Sonnet",
        provider="anthropic",
        capability_rank=13,
        input_cost=3.00,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=15.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    ModelInfo(
        id="claude-3-5-haiku",
        api_name="anthropic/claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        provider="anthropic",
        capability_rank=26,
        input_cost=0.80,  # https://platform.claude.com/docs/en/about-claude/pricing
        output_cost=4.00,  # https://platform.claude.com/docs/en/about-claude/pricing
    ),
    # Google (via OpenRouter)
    ModelInfo(
        id="gemini-3-pro",
        api_name="openrouter/google/gemini-3-pro-preview",
        display_name="Gemini 3 Pro",
        provider="google",
        capability_rank=3,
        input_cost=2.00,  # https://openrouter.ai/google/gemini-3-pro-preview
        output_cost=12.00,  # https://openrouter.ai/google/gemini-3-pro-preview
    ),
    ModelInfo(
        id="gemini-2.5-pro-preview",
        api_name="openrouter/google/gemini-2.5-pro-preview",
        display_name="Gemini 2.5 Pro Preview",
        provider="google",
        capability_rank=15,
        input_cost=1.25,  # https://openrouter.ai/google/gemini-2.5-pro-preview
        output_cost=10.00,  # https://openrouter.ai/google/gemini-2.5-pro-preview
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        api_name="openrouter/google/gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider="google",
        capability_rank=16,
        input_cost=1.25,  # https://openrouter.ai/google/gemini-2.5-pro
        output_cost=10.00,  # https://openrouter.ai/google/gemini-2.5-pro
    ),
    ModelInfo(
        id="gemini-2.5-flash",
        api_name="openrouter/google/gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        provider="google",
        capability_rank=19,
        input_cost=0.30,  # https://openrouter.ai/google/gemini-2.5-flash
        output_cost=2.50,  # https://openrouter.ai/google/gemini-2.5-flash
    ),
    # xAI - https://docs.x.ai/docs/models
    ModelInfo(
        id="grok-4-1-fast",
        api_name="xai/grok-4-1-fast-reasoning",
        display_name="Grok 4.1 Fast",
        provider="xai",
        capability_rank=5,
        input_cost=0.20,  # https://docs.x.ai/docs/models
        output_cost=0.50,  # https://docs.x.ai/docs/models
    ),
    ModelInfo(
        id="grok-4",
        api_name="xai/grok-4-0709",
        display_name="Grok 4",
        provider="xai",
        capability_rank=6,
        input_cost=3.00,  # https://docs.x.ai/docs/models
        output_cost=15.00,  # https://docs.x.ai/docs/models
    ),
    ModelInfo(
        id="grok-3",
        api_name="xai/grok-3",
        display_name="Grok 3",
        provider="xai",
        capability_rank=20,
        input_cost=3.00,  # https://docs.x.ai/docs/models
        output_cost=15.00,  # https://docs.x.ai/docs/models
    ),
    # Meta - https://openrouter.ai/meta-llama/llama-4-scout
    ModelInfo(
        id="llama-4-scout",
        api_name="openrouter/meta-llama/llama-4-scout",
        display_name="Llama 4 Scout",
        provider="meta",
        capability_rank=24,
        input_cost=0.08,  # https://openrouter.ai/meta-llama/llama-4-scout (DeepInfra)
        output_cost=0.30,  # https://openrouter.ai/meta-llama/llama-4-scout (DeepInfra)
    ),
    ModelInfo(
        id="llama-4-maverick",
        api_name="openrouter/meta-llama/llama-4-maverick",
        display_name="Llama 4 Maverick",
        provider="meta",
        capability_rank=27,
        input_cost=0.15,  # https://openrouter.ai/meta-llama/llama-4-maverick (DeepInfra)
        output_cost=0.60,  # https://openrouter.ai/meta-llama/llama-4-maverick (DeepInfra)
    ),
    ModelInfo(
        id="llama-3.3-70b",
        api_name="openrouter/meta-llama/llama-3.3-70b-instruct",
        display_name="Llama 3.3 70B",
        provider="meta",
        capability_rank=28,
        input_cost=0.10,  # https://openrouter.ai/meta-llama/llama-3.3-70b-instruct
        output_cost=0.32,  # https://openrouter.ai/meta-llama/llama-3.3-70b-instruct
    ),
    # Mistral (via OpenRouter)
    ModelInfo(
        id="mistral-medium",
        api_name="openrouter/mistralai/mistral-medium-3.1",
        display_name="Mistral Medium 3.1",
        provider="mistral",
        capability_rank=23,
        input_cost=0.40,  # https://openrouter.ai/mistralai/mistral-medium-3.1
        output_cost=2.00,  # https://openrouter.ai/mistralai/mistral-medium-3.1
    ),
    # Other open-weight models
    ModelInfo(
        id="gpt-oss-120b",
        api_name="openrouter/openai/gpt-oss-120b",
        display_name="GPT OSS 120B",
        provider="other",
        capability_rank=29,
        input_cost=0.039,  # https://openrouter.ai/openai/gpt-oss-120b (DeepInfra)
        output_cost=0.19,  # https://openrouter.ai/openai/gpt-oss-120b (DeepInfra)
    ),
]


# =============================================================================
# CONVERSION FUNCTIONS
# =============================================================================


def api_name_to_s3_name(api_name: str) -> str:
    """Convert API name to S3-safe name.

    Args:
        api_name: Full API name (e.g., "openai/o4-mini-2025-04-16")

    Returns:
        S3-safe name (e.g., "openai_o4-mini-2025-04-16")

    Note:
        This works for any API name, even ones not in the registry.
    """
    return api_name.replace("/", "_")


def s3_name_to_api_name(s3_name: str) -> str:
    """Convert S3-safe name back to API name.

    Args:
        s3_name: S3-safe name (e.g., "openai_o4-mini-2025-04-16")

    Returns:
        API name (e.g., "openai/o4-mini-2025-04-16")

    Note:
        Assumes the provider is the first underscore-separated component.
    """
    parts = s3_name.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return s3_name


# =============================================================================
# LOOKUP HELPERS
# =============================================================================


def get_model_by_id(model_id: str) -> ModelInfo | None:
    """Look up a model by its short ID."""
    for model in MODEL_REGISTRY:
        if model.id == model_id:
            return model
    return None


def get_model_by_api_name(api_name: str) -> ModelInfo | None:
    """Look up a model by its full API name."""
    for model in MODEL_REGISTRY:
        if model.api_name == api_name:
            return model
    return None
