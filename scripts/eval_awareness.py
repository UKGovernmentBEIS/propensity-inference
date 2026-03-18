import json
from datetime import datetime
from pathlib import Path
from pprint import pprint

import fire

from lib.eval_awareness.prompted_eval_awareness_claude import (
    measure_claude_prompted_eval_awareness,
)


async def cli(
    eval_file: str,
    output_filename: str | None = None,
    num_rephrasings: int = 5,
    num_epochs: int = 5,
    max_concurrency: int = 10,
) -> None:
    """
    CLI for measuring eval awareness using the methodology by Needham et al (https://arxiv.org/abs/2505.23836).

    Example usage:

    uv run ./scripts/eval_awareness.py <eval_file> [optional flags, see --help]
    """
    if not output_filename:
        # generate an output path
        output_filename = (
            "eval_awareness_results_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".json"
        )

    # ensure output filename is writeable
    if Path(output_filename).exists():
        print("output_filename already exists. Aborting!")
        exit(1)
    Path(output_filename).parent.mkdir(exist_ok=True, parents=True)
    with open(output_filename, "w") as f:
        f.write("{}")

    results = await measure_claude_prompted_eval_awareness(
        eval_file,
        num_rephrasings=num_rephrasings,
        num_epochs=num_epochs,
        max_concurrency=max_concurrency,
    )
    pprint(results.summary.model_dump())
    if output_filename:
        with open(output_filename, "w") as f:
            json.dump(results.model_dump(), f, indent=4)


if __name__ == "__main__":
    fire.Fire(cli)
