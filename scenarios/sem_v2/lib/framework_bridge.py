"""Bridge between ParameterSpace framework and SEM implementation."""

from typing import Any

from inspect_ai import Task

from scenarios.sem_v2.lib.content_assembler import SEMContentAssembler
from scenarios.sem_v2.lib.task_factory import sem_v2


def params_to_task(assembler: SEMContentAssembler, params: dict[str, Any]) -> Task:
    """Convert parameter dictionary to Inspect Task."""
    content = assembler.assemble(params)
    task = sem_v2(content, params)
    return task
