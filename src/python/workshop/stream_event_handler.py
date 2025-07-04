from typing import Any, List

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    AsyncAgentEventHandler,
    AsyncFunctionTool,
    MessageDeltaChunk,
    RunStatus,
    RunStep,
    RunStepDeltaChunk,
    ThreadMessage,
    ThreadRun,
)
from azure.ai.projects.aio import AIProjectClient
from utilities import Utilities


class StreamEventHandler(AsyncAgentEventHandler[str]):
    """Handle LLM streaming events and tokens."""

    def __init__(self, functions: AsyncFunctionTool, project_client: AIProjectClient, agents_client: AgentsClient, utilities: Utilities) -> None:
        self.functions = functions
        self.project_client = project_client
        self.agents_client = agents_client
        self.util = utilities
        self.generated_files: List[dict] = []  # Store generated file information
        super().__init__()

    async def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        """Handle message delta events. This will be the streamed token"""
        self.util.log_token_blue(delta.text)

    async def on_thread_message(self, message: ThreadMessage) -> None:
        """Handle thread message events."""
        # Get files and store their information
        files = await self.util.get_files(message, self.agents_client)
        self.generated_files.extend(files)

    async def on_thread_run(self, run: ThreadRun) -> None:
        """Handle thread run events"""

        if run.status == RunStatus.FAILED:
            print(f"Run failed. Error: {run.last_error}")
            print(f"Thread ID: {run.thread_id}")
            print(f"Run ID: {run.id}")

    async def on_run_step(self, step: RunStep) -> None:
        pass
        # if step.status == RunStepStatus.COMPLETED:
        #     print()
        # self.util.log_msg_purple(f"RunStep type: {step.type}, Status: {step.status}")

    async def on_run_step_delta(self, delta: RunStepDeltaChunk) -> None:
        pass

    async def on_error(self, data: str) -> None:
        print(f"An error occurred. Data: {data}")

    async def on_done(self) -> None:
        """Handle stream completion."""
        pass
        # self.util.log_msg_purple(f"\nStream completed.")

    async def on_unhandled_event(self, event_type: str, _event_data: object) -> None:
        """Handle unhandled events."""
        # print(f"Unhandled Event Type: {event_type}, Data: {event_data}")
        print(f"Unhandled Event Type: {event_type}")
