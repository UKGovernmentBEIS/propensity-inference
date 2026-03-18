import random
from pathlib import Path

from inspect_ai.log import EvalLog, EvalLogInfo, list_eval_logs, read_eval_log

from lib.trace_formatting import format_trace


def extract_traces_from_logs(log_dir_or_file: str) -> list[str]:
    """Convert an inspect Task object to a string that can be easily read by an LLM."""
    log_files: list[EvalLogInfo] | list[str]
    if log_dir_or_file.endswith(".eval"):
        log_files = [log_dir_or_file]
    else:
        # treat it as a directory
        log_files = list_eval_logs(log_dir_or_file)
    logs = [read_eval_log(fn) for fn in log_files]

    traces: list[str] = []
    for log in logs:
        assert log.samples, f"failed to find samples in log file: {log.location}"
        for sample in log.samples:
            traces.append(format_trace(sample.messages))

    return traces


def _get_repo_base_dir() -> Path:
    return Path(__file__).parent.parent.parent


def _get_scenario_base_dir(name: str) -> Path:
    return _get_repo_base_dir() / "scenarios" / name


def list_scenario_template_filenames(scenario_name: str) -> list[str]:
    output: list[str] = []

    repo_base_dir = _get_repo_base_dir()
    base_dir = _get_scenario_base_dir(scenario_name)
    readme_filename = base_dir / "README.md"

    # Support both .md and .txt files as mentioned in comment
    for pattern in ["**/*.md", "**/*.txt"]:
        for fn in base_dir.glob(pattern):
            if fn != readme_filename:
                output.append(str(fn.relative_to(repo_base_dir)))

    return output


def list_scenario_code_filenames(scenario_name: str) -> list[str]:
    output: list[str] = []

    repo_base_dir = _get_repo_base_dir()
    base_dir = _get_scenario_base_dir(scenario_name)

    for fn in base_dir.glob("**/*.py"):
        output.append(str(fn.relative_to(repo_base_dir)))

    return output


def scenario_files_to_string(
    scenario_name: str,
    include_templates: bool = True,
    include_code: bool = True,
    shuffle_file_order: bool = False,
    shuffle_seed: int = 0,
) -> str:
    """Serialise all the files in a scenario to one big string than an LLM can read."""
    repo_base_dir = _get_repo_base_dir()
    base_dir = _get_scenario_base_dir(scenario_name)
    if not base_dir.exists():
        raise ValueError(
            f"Invalid scenario name {scenario_name}: scenarios/{scenario_name} directory does not exist"
        )
    output = ""

    readme_filename = base_dir / "README.md"
    if readme_filename.exists():
        with open(readme_filename, "r") as f:
            s = f.read()
            fn = readme_filename.relative_to(repo_base_dir)
            output += f"<readme filename={fn}>\n{s}\n</readme>\n\n"

    if include_code:
        fns = list_scenario_code_filenames(scenario_name)
        if shuffle_file_order:
            random.seed(shuffle_seed)
            random.shuffle(fns)
        for fn in fns:
            with open(fn, "r") as f:
                s = f.read()
                output += f"<code filename={fn}>\n{s}\n</code>\n\n"

    if include_templates:
        # Support both .md and .txt files as mentioned in comment
        fns = list_scenario_template_filenames(scenario_name)
        if shuffle_file_order:
            random.seed(shuffle_seed)
            random.shuffle(fns)
        for fn in fns:
            with open(fn, "r") as f:
                s = f.read()
                output += f"<template filename={fn}>\n{s}\n</template>\n\n"

    return output


def load_eval_logs(log_dir_or_file: str) -> list[EvalLog]:
    log_files: list[EvalLogInfo] | list[str]
    if log_dir_or_file.endswith(".eval"):
        log_files = [log_dir_or_file]
    else:
        # treat it as a directory
        log_files = [i.name for i in list_eval_logs(log_dir_or_file)]
    # list files deterministically
    log_files = list(sorted(log_files))
    logs = [read_eval_log(fn) for fn in log_files]
    return logs


def extract_traces(logs: list[EvalLog]) -> list[str]:
    traces: list[str] = []
    for log in logs:
        assert log.samples, f"failed to find samples in log file: {log.location}"
        for sample in log.samples:
            traces.append(format_trace(sample.messages))
    return traces


def extract_scenario_names(logs: list[EvalLog]) -> list[str]:
    names: list[str] = []
    for log in logs:
        assert log.samples, f"failed to find samples in log file: {log.location}"
        for sample in log.samples:
            names.append(sample.metadata["scenario_name"])
    return names
