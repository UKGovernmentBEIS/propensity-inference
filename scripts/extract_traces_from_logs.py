import shutil
from pathlib import Path

import fire

from lib.qa.task_serialisation import extract_traces_from_logs


def cli(log_dir_or_file: str, output_dir: str = "traces") -> None:
    """Serialise a trace from an .eval file."""
    traces = extract_traces_from_logs(log_dir_or_file)
    if Path(output_dir).exists():
        shutil.rmtree(output_dir)
    Path(output_dir).mkdir(parents=True)
    for idx, trace in enumerate(traces):
        fn = Path(output_dir) / f"trace_{idx}.txt"
        with open(fn, "w") as f:
            f.write(f"TRACE {idx}\n")
            f.write(trace)


if __name__ == "__main__":
    fire.Fire(cli)
