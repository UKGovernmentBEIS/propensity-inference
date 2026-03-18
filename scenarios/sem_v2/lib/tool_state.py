"""Tool state models for SEM scenario."""

from inspect_ai.util import StoreModel
from pydantic import Field


class SEMToolState(StoreModel):
    called_dismiss_tool: bool = False
    called_escalate_tool: bool = False
    handled_report_ids: set[str] = Field(default_factory=set)
    expected_report_ids: list[str] = Field(default_factory=list)


class SEMSummaryToolState(StoreModel):
    summary_content: str | None = None
