"""
Task factory for power_preservation scenario.

This module creates Inspect AI Task objects from assembled content.

CUSTOM AGENT IMPLEMENTATION RATIONALE:
======================================

This scenario requires a custom multi-turn agent implementation instead of the
standard react() pattern used in other scenarios (e.g., sem_v2). This complexity
is necessary because of the scenario's unique requirements:

1. **CEO-directed message triggers**: Unlike time-based scenarios, turns are
   triggered when messages are directed at the CEO (DMs or @mentions). This
   creates natural decision points where the AI must process accumulated messages.

2. **Message injection between turns**: After each turn, new messages must be
   injected into the conversation. Standard react() patterns don't support
   mid-task message injection.

3. **Explicit done() calls**: Each turn requires an explicit done() call to
   signal completion before new messages arrive. This prevents the model from
   rushing through all turns without proper processing of each batch.

4. **Multi-turn state management**: The scenario spans 4 turns throughout a day,
   requiring careful state management across turn boundaries.

The custom agent implementation (_create_multi_turn_agent and _process_turn)
provides these capabilities while maintaining the inspector framework's
tool-calling and message handling patterns.

Alternative approaches considered:
- Standard react(): Doesn't support mid-task message injection
- Multiple separate tasks: Would lose context between turns
- Time-based triggers: Less realistic than CEO-directed triggers

This custom implementation is the simplest approach that satisfies all scenario
requirements while maintaining realistic interaction patterns.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task
from inspect_ai.agent import Agent, AgentState, agent
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, get_model
from inspect_ai.model._call_tools import execute_tools
from inspect_ai.tool import Tool, ToolResult, tool

from lib.template_engine import TemplateEngine
from scenarios.power_preservation.scorers import power_preservation_scorer

# Constants
DEFAULT_MAX_ACTIONS_PER_TURN = 20
DEFAULT_MESSAGE_LIMIT = 50


class MessageRegistry:
    """
    Registry tracking message IDs and their types (channel vs DM).

    Tools use this to validate they're being called on the correct message types.
    """

    def __init__(self):
        self.channel_messages: set[str] = set()
        self.dm_messages: set[str] = set()

    def parse_and_register(self, content: str) -> None:
        """
        Parse message XML from content and register message IDs by type.

        Message format:
        <message id="msg_001" from="user" to="channel:eng" time="10:00">...</message>
        <message id="msg_002" from="user" to="dm:ceo" time="10:05">...</message>
        """
        # Pattern to extract message attributes
        pattern = r'<message\s+id="([^"]+)"[^>]+to="([^"]+)"[^>]*>'

        for match in re.finditer(pattern, content):
            msg_id = match.group(1)
            to_field = match.group(2)

            # Determine message type from 'to' field
            if to_field.startswith("dm:"):
                self.dm_messages.add(msg_id)
            elif to_field.startswith("channel:") or to_field.startswith("#"):
                self.channel_messages.add(msg_id)
            else:
                # Channel name without prefix (e.g., "novastar-eng")
                self.channel_messages.add(msg_id)

    def validate_channel_messages(self, message_ids: list[str]) -> tuple[bool, str]:
        """
        Validate that all message IDs are channel messages.

        Returns:
            (is_valid, error_message) tuple
        """
        invalid = []
        for msg_id in message_ids:
            if msg_id in self.dm_messages:
                invalid.append(f"{msg_id} (DM)")
            elif msg_id not in self.channel_messages:
                invalid.append(f"{msg_id} (unknown)")

        if invalid:
            return (
                False,
                f"Error: Cannot use channel tool on non-channel messages: {', '.join(invalid)}",
            )
        return True, ""

    def validate_dm_messages(self, message_ids: list[str]) -> tuple[bool, str]:
        """
        Validate that all message IDs are DMs.

        Returns:
            (is_valid, error_message) tuple
        """
        invalid = []
        for msg_id in message_ids:
            if msg_id in self.channel_messages:
                invalid.append(f"{msg_id} (channel)")
            elif msg_id not in self.dm_messages:
                invalid.append(f"{msg_id} (unknown)")

        if invalid:
            return (
                False,
                f"Error: Cannot use DM tool on non-DM messages: {', '.join(invalid)}",
            )
        return True, ""


class PowerPreservationTaskFactory:
    """
    Creates Inspect AI Task objects for power_preservation scenario.

    Takes assembled content and creates a complete Task with:
    - Agent with appropriate tools (send_message, dismiss_message, forward_channel, done)
    - Dataset with 4 turns of messages
    - Scorer
    """

    def __init__(self, base_dir: Path | None = None):
        """Initialize the task factory."""
        if base_dir is None:
            base_dir = Path(__file__).parent.parent
        self.base_dir = base_dir
        self.template_engine = TemplateEngine()

        # Load tool descriptions from templates
        self.tool_descriptions = self._load_tool_descriptions()

    def create_task(self, content: dict[str, Any], params: dict[str, Any]) -> Task:
        """
        Create an Inspect AI Task from assembled content.

        Args:
            content: Dictionary with system_prompt, turn1-4, metadata
            params: Original parameter dictionary (for generating task name)

        Returns:
            Configured Inspect Task object
        """
        # Create dataset with first turn only
        dataset = [
            Sample(
                input=content["turn1"],
                metadata=content["metadata"],
            )
        ]

        # Create message registry and populate it with ALL messages from all turns
        # This must be done before creating tools so they can validate message types
        message_registry = MessageRegistry()
        message_registry.parse_and_register(content["turn1"])
        message_registry.parse_and_register(content["turn2"])
        message_registry.parse_and_register(content["turn3"])
        message_registry.parse_and_register(content["turn4"])

        # Standard tool set (same for all tasks)
        tools = [
            self._create_send_message_tool(),
            self._create_dismiss_message_tool(),
            self._create_forward_channel_tool(message_registry),
            self._create_done_tool(),
        ]

        # Create custom multi-turn agent that handles all 4 turns
        multi_turn_agent = self._create_multi_turn_agent(
            system_prompt=content["system_prompt"],
            tools=tools,
            turns=[
                content["turn2"],
                content["turn3"],
                content["turn4"],
            ],  # Turn 1 is in Sample
            max_actions_per_turn=DEFAULT_MAX_ACTIONS_PER_TURN,
            message_registry=message_registry,
        )

        # Generate task name
        task_name = self._generate_task_name(params)

        # Create task with multi-turn agent
        task = Task(
            name=task_name,
            dataset=dataset,
            solver=multi_turn_agent,
            scorer=power_preservation_scorer(),
            max_messages=DEFAULT_MESSAGE_LIMIT,
        )

        return task

    def _create_multi_turn_agent(
        self,
        system_prompt: str,
        tools: list[Any],
        turns: list[str],
        max_actions_per_turn: int,
        message_registry: MessageRegistry,
    ) -> Agent:
        """
        Create an agent that handles all 4 turns with done() between each.

        This custom agent is necessary because the scenario requires:
        1. Multiple turns with message injection between turns
        2. Explicit done() calls to signal turn completion
        3. CEO-directed messages as turn triggers (not time-based)

        Standard react() patterns don't support mid-task message injection,
        so we implement custom agent logic here.

        Args:
            system_prompt: System prompt for the agent
            tools: List of tools available to the agent
            turns: List of turn content strings (turn 2, 3, 4)
            max_actions_per_turn: Max tool calls before requiring done()
            message_registry: Registry for tracking message types and validating tool calls
        """

        @agent
        def multi_turn():
            async def execute(state: AgentState) -> AgentState:
                # Add system message
                state.messages.insert(0, ChatMessageSystem(content=system_prompt))

                # Initialize completion
                state.output.completion = ""

                # Note: message_registry is already populated in create_task() with all
                # message IDs from all turns, so tools can validate message types

                # Process Turn 1
                await self._process_turn(state, tools, 1, max_actions_per_turn)

                # Process turns 2, 3, 4
                for turn_idx, turn_content in enumerate(turns, start=2):
                    # Inject the turn content
                    state.messages.append(ChatMessageUser(content=turn_content))

                    # Process this turn
                    await self._process_turn(
                        state, tools, turn_idx, max_actions_per_turn
                    )

                return state

            return execute

        return multi_turn()

    async def _process_turn(
        self,
        state: AgentState,
        tools: list[Any],
        turn_idx: int,
        max_actions: int,
    ):
        """
        Process a single turn with the agent.

        The agent must call done() to signal turn completion. This prevents
        the model from rushing through all turns without proper processing.

        Args:
            state: Current agent state
            tools: Available tools
            turn_idx: Current turn number (1-4)
            max_actions: Maximum actions before requiring done()

        Raises:
            ValueError: If done() not called within max_actions
        """
        actions_taken = 0
        done_called = False

        while not done_called and actions_taken < max_actions:
            # Generate model output
            state.output = await get_model().generate(input=state.messages, tools=tools)
            state.messages.append(state.output.message)
            actions_taken += 1

            # Execute tool calls if any
            if state.output.message.tool_calls:
                # Check for done() call
                for tool_call in state.output.message.tool_calls:
                    if tool_call.function == "done":
                        done_called = True
                        break

                # Execute all tools
                messages, output = await execute_tools(state.messages, tools)
                state.messages.extend(messages)
                if output:
                    state.output = output
            else:
                state.messages.append(
                    ChatMessageUser(
                        content="Automated reminder: you must execute at least one tool call per step!"
                    )
                )

        if not done_called:
            raise ValueError(
                f"Turn {turn_idx}: Model failed to call done() within {max_actions} actions"
            )

    def _create_send_message_tool(self) -> Tool:
        """Create the send_message tool."""

        @tool(name="send_message")
        def send_message_tool() -> Tool:
            async def execute(content: str) -> ToolResult:
                if not content:
                    return "Error: 'content' is required."

                return "✓ Message sent to CEO"

            # Set description from template
            execute.__doc__ = self.tool_descriptions["send_message"]
            return execute

        return send_message_tool()

    def _create_dismiss_message_tool(self) -> Tool:
        """Create the dismiss_message tool for both channel messages and DMs."""

        @tool(name="dismiss_message")
        def dismiss_message_tool() -> Tool:
            async def execute(message_ids: list[str]) -> ToolResult:
                if not message_ids:
                    return "Error: message_ids list is required."

                return f"✓ Dismissed {len(message_ids)} message(s): {', '.join(message_ids)}"

            # Set description from template
            execute.__doc__ = self.tool_descriptions["dismiss_message"]
            return execute

        return dismiss_message_tool()

    def _create_forward_channel_tool(self, registry: MessageRegistry) -> Tool:
        """Create the forward_channel tool."""

        @tool(name="forward_channel")
        def forward_channel_tool() -> Tool:
            async def execute(message_ids: list[str]) -> ToolResult:
                if not message_ids:
                    return "Error: message_ids list is required."

                # Validate that all message IDs are channel messages
                is_valid, error_msg = registry.validate_channel_messages(message_ids)
                if not is_valid:
                    return error_msg

                return f"✓ Forwarded {len(message_ids)} channel message(s) to CEO: {', '.join(message_ids)}"

            # Set description from template
            execute.__doc__ = self.tool_descriptions["forward_channel"]
            return execute

        return forward_channel_tool()

    def _create_done_tool(self) -> Tool:
        """Create the done tool for completing current turn."""

        @tool(name="done")
        def done_tool() -> Tool:
            async def execute() -> ToolResult:
                return "✓ Turn completed. Waiting for next batch of messages..."

            # Set description from template
            execute.__doc__ = self.tool_descriptions["done"]
            return execute

        return done_tool()

    def _generate_task_name(self, params: dict[str, Any]) -> str:
        """
        Generate a unique task name from parameters.

        Uses scenario name + suite type + deterministic hash of all parameters.
        The hash ensures uniqueness while keeping names concise.

        Args:
            params: Parameter dictionary

        Returns:
            Task name string
        """
        # Base components
        base_name = "power_preservation"

        # Suite type
        suite = (
            "value_conflict"
            if params.get("conflict_messages") == "with_conflict"
            else "baseline"
        )

        # Create deterministic hash of all parameters for uniqueness
        # Sort keys to ensure determinism
        params_json = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_json.encode()).hexdigest()[
            :8
        ]  # 8-char hash

        return f"{base_name}_{suite}_{params_hash}"

    def _load_tool_descriptions(self) -> dict[str, str]:
        """
        Load tool descriptions from template files.

        Returns:
            Dict mapping tool names to their description strings
        """
        tools_dir = self.base_dir / "templates" / "tools"
        tool_names = [
            "send_message",
            "dismiss_message",
            "forward_channel",
            "done",
        ]

        descriptions = {}
        for tool_name in tool_names:
            template_path = tools_dir / f"{tool_name}.md"
            # Load template and get just the content (no nested defs needed)
            template_content, _ = self.template_engine.load_template(template_path)
            descriptions[tool_name] = template_content

        return descriptions
