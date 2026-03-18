"""
Shared transcript formatting utilities for scorers.

This module provides functions to format conversation trajectories as structured XML,
making it easier for LLM judges to understand what happened during task execution.
"""

from html import escape

from inspect_ai.model import ContentText
from inspect_ai.solver import TaskState


def format_trajectory_xml(state: TaskState) -> str:
    """Format the conversation trajectory as structured XML.

    This formats messages in a way that preserves structure and relationships,
    making it easier for an LLM judge to understand what happened.

    Handles malformed tool calls gracefully by using "unknown" for missing fields.

    Inspired by control-arena's full_trajectory_prompt_formatter_xml.

    Args:
        state: Task state containing messages

    Returns:
        XML-formatted conversation transcript
    """
    lines = ["<transcript>"]

    for message in state.messages:
        if message.role == "assistant":
            lines.append('  <message role="assistant">')
            lines.append("    <content>")

            # Handle content
            if isinstance(message.content, str):
                lines.append(f"      <text>{escape(message.content)}</text>")
            elif isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, ContentText):
                        lines.append(f"      <text>{escape(item.text)}</text>")

            lines.append("    </content>")

            # Add tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                lines.append("    <tool_calls>")
                for tc in message.tool_calls:
                    tc_id = escape(tc.id) if hasattr(tc, "id") and tc.id else "unknown"
                    tc_func = (
                        escape(tc.function)
                        if hasattr(tc, "function") and tc.function
                        else "unknown"
                    )
                    lines.append(f'      <tool_call id="{tc_id}" function="{tc_func}">')

                    # Add arguments if present
                    if hasattr(tc, "arguments") and tc.arguments:
                        lines.append("        <arguments>")
                        # Handle arguments as dict or string
                        if isinstance(tc.arguments, dict):
                            for key, value in tc.arguments.items():
                                lines.append(
                                    f'          <arg name="{escape(str(key))}">'
                                )
                                lines.append(f"            {escape(str(value))}")
                                lines.append("          </arg>")
                        else:
                            lines.append(f"          {escape(str(tc.arguments))}")
                        lines.append("        </arguments>")

                    lines.append("      </tool_call>")
                lines.append("    </tool_calls>")

            lines.append("  </message>")

        elif message.role == "tool":
            # Tool result message
            tc_id = (
                escape(message.tool_call_id)
                if hasattr(message, "tool_call_id") and message.tool_call_id
                else "unknown"
            )
            func = (
                escape(message.function)
                if hasattr(message, "function") and message.function
                else "unknown"
            )
            lines.append(
                f'  <message role="tool" tool_call_id="{tc_id}" function="{func}">'
            )
            lines.append("    <content>")

            # Handle content
            if isinstance(message.content, str):
                # Truncate very long tool outputs to avoid overwhelming the judge
                content = message.content
                if len(content) > 10000:
                    content = (
                        content[:5000]
                        + f"\n\n[... truncated {len(content) - 10000} chars ...]\n\n"
                        + content[-5000:]
                    )
                lines.append(f"      <text>{escape(content)}</text>")
            elif isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, ContentText):
                        content = item.text
                        if len(content) > 10000:
                            content = (
                                content[:5000]
                                + f"\n\n[... truncated {len(content) - 10000} chars ...]\n\n"
                                + content[-5000:]
                            )
                        lines.append(f"      <text>{escape(content)}</text>")

            lines.append("    </content>")
            lines.append("  </message>")

        elif message.role == "user":
            # User messages
            lines.append('  <message role="user">')
            lines.append("    <content>")

            if isinstance(message.content, str):
                lines.append(f"      <text>{escape(message.content)}</text>")
            elif isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, ContentText):
                        lines.append(f"      <text>{escape(item.text)}</text>")

            lines.append("    </content>")
            lines.append("  </message>")

    lines.append("</transcript>")
    return "\n".join(lines)
