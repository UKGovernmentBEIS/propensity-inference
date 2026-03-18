# Note: We should be using lib/model_registry.py for everything from now on. This is legacy and still supported for run_scenarios.py, though.
from frozendict import frozendict

MODEL_CONFIGS = (
    frozendict(
        {
            "name": "openrouter/openai/gpt-oss-120b",
            "short_name": "GPT OSS 120b",
            "lab": "OpenAI",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openrouter/meta-llama/llama-4-scout",
            "short_name": "Llama 4 Scout",
            "lab": "Meta",
            "weight": 2,
        }
    ),
    frozendict(
        {
            "name": "openrouter/meta-llama/llama-4-maverick",
            "short_name": "Llama 4 Maverick",
            "lab": "Meta",
            "weight": 5,
        }
    ),
    frozendict(
        {
            "name": "openrouter/meta-llama/llama-3.3-70b-instruct",
            "short_name": "Llama 3.3 70b",
            "lab": "Meta",
            "weight": 3,
        }
    ),
    frozendict(
        {
            "name": "openrouter/google/gemini-2.5-flash",
            "short_name": "Gemini 2.5 Flash",
            "lab": "GDM",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openrouter/google/gemini-2.5-pro",
            "short_name": "Gemini 2.5 Pro",
            "lab": "GDM",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openrouter/google/gemini-2.5-pro-preview",
            "short_name": "Gemini 2.5 Pro Preview",
            "lab": "GDM",
            "weight": 8,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-sonnet-4-5-20250929",
            "short_name": "Sonnet 4.5",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-haiku-4-5-20251001",
            "short_name": "Haiku 4.5",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-opus-4-5-20251101",
            "short_name": "Opus 4.5",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-opus-4-1-20250805",
            "short_name": "Opus 4.1",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-sonnet-4-20250514",
            "short_name": "Sonnet 4",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-opus-4-20250514",
            "short_name": "Opus 4",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-3-7-sonnet-20250219",
            "short_name": "Sonnet 3.7",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "anthropic/claude-3-5-haiku-20241022",
            "short_name": "Haiku 3.5",
            "lab": "anthropic",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-4.1-2025-04-14",
            "short_name": "GPT-4.1",
            "lab": "openai",
            "weight": 10,
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-4o-2024-08-06",
            "short_name": "GPT-4o",
            "lab": "openai",
            "weight": 5,
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-5-2025-08-07",
            "short_name": "GPT-5",
            "lab": "openai",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-5-mini-2025-08-07",
            "short_name": "GPT-5 Mini",
            "lab": "openai",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-5-pro-2025-10-06",
            "short_name": "GPT-5 Pro",
            "lab": "openai",
            "weight": 4,  # this is really really slow to sample from
        }
    ),
    frozendict(
        {
            "name": "openai/gpt-5.2-2025-12-11",
            "short_name": "GPT-5.2",
            "lab": "openai",
            "weight": 20,
        }
    ),
    frozendict(
        {
            "name": "openai/o1-2024-12-17",
            "short_name": "o1",
            "lab": "openai",
            "weight": 10,
        }
    ),
    frozendict(
        {
            "name": "openai/o1-pro-2025-03-19",
            "short_name": "o1 Pro",
            "lab": "openai",
            "weight": 10,
        }
    ),
    frozendict(
        {
            "name": "openai/o3-2025-04-16",
            "short_name": "o3",
            "lab": "openai",
            "weight": 15,
        }
    ),
    frozendict(
        {
            "name": "openai/o3-pro-2025-06-10",
            "short_name": "o3 Pro",
            "lab": "openai",
            "weight": 15,
        }
    ),
    frozendict(
        {
            "name": "openai/o4-mini-2025-04-16",
            "short_name": "o4 Mini",
            "lab": "openai",
            "weight": 10,
        }
    ),
)
