"""Email assistant tools for GPU Decision Email Assistant scenario.

Defines tools for drafting, sending, and managing emails.

Tool descriptions are loaded from templates/tools/ by task_factory.py

State Management:
    Uses inspect_ai's store() for per-sample isolated state. Each task sample
    gets its own drafts dictionary, preventing cross-task interference when
    running evaluations in parallel.
"""

from inspect_ai.tool import Tool, tool
from inspect_ai.util import store


def _get_drafts() -> dict[str, dict[str, str | bool]]:
    """Get drafts dict from per-sample store, initializing if needed."""
    return store().get("email_drafts", {})


def _set_drafts(drafts: dict[str, dict[str, str | bool]]) -> None:
    """Set drafts dict in per-sample store."""
    store().set("email_drafts", drafts)


def _get_next_draft_id() -> int:
    """Get next draft ID from per-sample store, initializing if needed."""
    return store().get("next_draft_id", 1)


def _set_next_draft_id(draft_id: int) -> None:
    """Set next draft ID in per-sample store."""
    store().set("next_draft_id", draft_id)


def create_draft_email(description: str) -> Tool:
    """Create the draft_email tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for drafting emails
    """

    @tool(name="draft_email")
    def draft_email_tool() -> Tool:
        async def execute(to: str, subject: str, body: str) -> str:
            drafts = _get_drafts()
            next_id = _get_next_draft_id()

            draft_id = f"draft_{next_id}"
            _set_next_draft_id(next_id + 1)

            drafts[draft_id] = {
                "to": to,
                "subject": subject,
                "body": body,
                "sent": False,
            }
            _set_drafts(drafts)

            return f'Draft created with ID: {draft_id}. To send this email, call send_email(draft_id="{draft_id}").'

        # Set description from template
        execute.__doc__ = description
        return execute

    return draft_email_tool()


def create_send_email(description: str) -> Tool:
    """Create the send_email tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for sending draft emails
    """

    @tool(name="send_email")
    def send_email_tool() -> Tool:
        async def execute(draft_id: str) -> str:
            drafts = _get_drafts()

            if draft_id not in drafts:
                return f"Error: Draft {draft_id} not found. Use list_drafts() to see available drafts."

            if drafts[draft_id]["sent"]:
                return f"Error: Draft {draft_id} has already been sent."

            drafts[draft_id]["sent"] = True
            _set_drafts(drafts)
            draft = drafts[draft_id]

            return f"Email sent to {draft['to']} with subject: {draft['subject']}"

        # Set description from template
        execute.__doc__ = description
        return execute

    return send_email_tool()


def create_list_drafts(description: str) -> Tool:
    """Create the list_drafts tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for listing drafts
    """

    @tool(name="list_drafts")
    def list_drafts_tool() -> Tool:
        async def execute() -> str:
            drafts = _get_drafts()

            if not drafts:
                return "No drafts found."

            result = "Current drafts:\n"
            for draft_id, draft in drafts.items():
                status = "sent" if draft["sent"] else "unsent"
                result += f"- {draft_id}: To: {draft['to']}, Subject: {draft['subject']} ({status})\n"

            return result

        # Set description from template
        execute.__doc__ = description
        return execute

    return list_drafts_tool()


def create_mark_read(description: str) -> Tool:
    """Create the mark_read tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for marking emails as read
    """

    @tool(name="mark_read")
    def mark_read_tool() -> Tool:
        async def execute(email_id: str) -> str:
            return f"Marked email as read: {email_id}"

        # Set description from template
        execute.__doc__ = description
        return execute

    return mark_read_tool()


def create_message_user(description: str) -> Tool:
    """Create the message_user tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for sending messages to Marcus
    """

    @tool(name="message_user")
    def message_user_tool() -> Tool:
        async def execute(message: str) -> str:
            return f"Message sent to Marcus: '{message}'"

        # Set description from template
        execute.__doc__ = description
        return execute

    return message_user_tool()


def create_wait(description: str) -> Tool:
    """Create the wait tool with given description.

    Args:
        description: Tool description from template

    Returns:
        Tool for signaling completion and waiting
    """

    @tool(name="wait")
    def wait_tool() -> Tool:
        async def execute() -> str:
            return "Waiting for next request from Marcus..."

        # Set description from template
        execute.__doc__ = description
        return execute

    return wait_tool()
