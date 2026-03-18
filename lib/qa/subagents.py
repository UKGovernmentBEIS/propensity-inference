import asyncio
from pathlib import Path

from inspect_ai.model import ModelOutput, get_model
from tqdm import tqdm


def run_parallel_llm_queries(
    prompts: list[str],
    model: str,
    pbar_description: str = "processing llm queries",
) -> list[str]:
    """Given a list of prompts, run them all and output a list of completions."""
    assert len(prompts) > 0

    async def _run_queries():
        work = [get_model(model).generate(prompt) for prompt in prompts]

        results: list[ModelOutput] = []
        for coro in tqdm(
            asyncio.as_completed(work),
            total=len(work),
            desc=pbar_description,
            disable=len(prompts) == 1,
        ):
            results.append(await coro)

        return results

    outputs = asyncio.run(_run_queries())
    completions = [o.completion for o in outputs]
    return completions


def load_claudemd() -> str:
    fn = Path(__file__).parent.parent.parent / ".claude/CLAUDE.md"
    with open(fn, "r") as f:
        return f.read()
