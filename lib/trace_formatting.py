from typing import assert_never

from inspect_ai._util.format import format_function_call  # type: ignore
from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
)

from lib.qa.verifier_agent import remove_verification_instructions_from_text


def format_message(message: ChatMessage) -> str:
    if isinstance(message, ChatMessageSystem):
        return f"System: {message.text}"
    elif isinstance(message, ChatMessageUser):
        return f"User: {message.text}"
    elif isinstance(message, ChatMessageAssistant):
        text_parts: list[str] = []
        if isinstance(message.content, str):
            text_parts.append(message.content)
        else:
            for block in message.content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "reasoning":
                    text_parts.append(block.reasoning)
        assert isinstance(text_parts, list)
        text = "\n".join(text_parts)
        assistant_message = [text]
        if message.tool_calls:
            assistant_message.extend(
                [
                    format_function_call(tool_call.function, tool_call.arguments)
                    for tool_call in message.tool_calls
                ]
            )
        return "Assistant: " + "\n\n".join(assistant_message)
    elif isinstance(message, ChatMessageTool):
        error_message = (
            f"{message.error.type}: {message.error.message}" if message.error else ""
        )
        return f"Tool ({message.function}): {error_message}{message.text}"
    else:
        assert_never(message)


def format_trace(
    messages: str | list[ChatMessage],
    remove_verification_instructions: bool = True,
) -> str:
    if isinstance(messages, str):
        s = messages
    else:
        s = ""
        for m in messages:
            s += format_message(m).strip() + "\n\n"
    if remove_verification_instructions:
        s = remove_verification_instructions_from_text(s)
    return s.strip()
