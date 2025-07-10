"""
Azure AI Agent Manager

This module provides the AgentManager class for managing Azure AI Agent lifecycle
and dependencies.
"""

import logging
from typing import Tuple

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, AsyncToolSet
from azure.ai.projects.aio import AIProjectClient
from azure.monitor.opentelemetry import configure_azure_monitor
from config import Config
from opentelemetry import trace
from utilities import Utilities

logger = logging.getLogger(__name__)

trace_scenario = "Zava Agent Initialization"
tracer = trace.get_tracer("zava_agent.tracing")


class AgentManager:
    """Manages Azure AI Agent lifecycle and dependencies."""

    def __init__(self) -> None:
        self.utilities = Utilities()
        self.agents_client: AgentsClient | None = None
        self.project_client: AIProjectClient | None = None
        self.agent: Agent | None = None
        self.thread: AgentThread | None = None
        self.mcp_tools: AsyncFunctionTool | None = None
        self.toolset = AsyncToolSet()

    async def setup_tools(self, mcp_tools: AsyncFunctionTool) -> None:
        """Setup tools for the agent. This method is called from app.py."""
        self.mcp_tools = mcp_tools
        self.toolset.add(self.mcp_tools)

    async def _create_agent(self, instructions: str) -> None:
        """Create the Azure AI agent with configured tools."""
        with tracer.start_as_current_span(trace_scenario):
            print("Creating agent...")
            self.agent = await self.agents_client.create_agent(
                model=Config.MODEL_DEPLOYMENT_NAME,
                name=Config.AGENT_NAME,
                instructions=instructions,
                toolset=self.toolset,
                temperature=Config.TEMPERATURE,
            )
            print(f"Created agent, ID: {self.agent.id}")

            self.agents_client.enable_auto_function_calls(tools=self.toolset)
            print("Enabled auto function calls.")

            print("Creating thread...")
            self.thread = await self.agents_client.threads.create()
            print(f"Created thread, ID: {self.thread.id}")

    async def initialize(self, instructions_file: str, telemetry_enabled: bool = False) -> bool:
        """Initialize the agent with tools and instructions."""
        try:
            # Validate configuration
            Config.validate_required_env_vars()

            # Validate Azure Entra ID Authentication
            credential = await self.utilities.validate_azure_authentication()
            print("✅ Azure Entra ID authentication successful!")

            # Create agent clients
            self.agents_client = AgentsClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            self.project_client = AIProjectClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            # Enable Azure Monitor Telemetry
            if telemetry_enabled:
                configure_azure_monitor(connection_string=await self.project_client.telemetry.get_connection_string())

            instructions = self.utilities.load_instructions(instructions_file)
            await self._create_agent(instructions)

            return True

        except Exception as e:
            logger.error("Agent initialization failed: %s", str(e))
            return False

    async def cleanup(self) -> None:
        """Clean up agent resources."""
        if self.agent and self.thread and self.agents_client:
            try:
                await self.utilities.cleanup_agent_resources(self.agent, self.thread, self.agents_client)
                print("Agent resources cleaned up.")
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")

    def get_dependencies(self) -> Tuple[AgentsClient, AIProjectClient, Agent, AgentThread, AsyncFunctionTool]:
        """Get all agent dependencies for injection."""
        if not all([self.agents_client, self.project_client, self.agent, self.thread, self.mcp_tools]):
            raise RuntimeError("Agent not properly initialized")

        return self.agents_client, self.project_client, self.agent, self.thread, self.mcp_tools

    @property
    def is_initialized(self) -> bool:
        """Check if agent is properly initialized."""
        return all([self.agents_client, self.project_client, self.agent, self.thread, self.mcp_tools])
