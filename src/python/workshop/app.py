"""
Azure AI Agent Chat Application

This application creates an AI agent that can interact with a PostgreSQL database
using Model Context Protocol (MCP) tools and provides a web interface for chat.

To run: python app.py
Web interface available at: http://127.0.0.1:8005
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Tuple

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, AsyncToolSet, CodeInterpreterTool
from azure.ai.projects.aio import AIProjectClient
from azure.monitor.opentelemetry import configure_azure_monitor
from config import Config
from fastapi import FastAPI
from mcp_client import fetch_and_build_mcp_tools
from opentelemetry import trace
from terminal_colors import TerminalColors as tc
from utilities import Utilities
from web_interface import WebInterface

# Configure logging - suppress verbose Azure SDK logs
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)
Utilities.suppress_logs()

# Agent Instructions
INSTRUCTIONS_FILE = "instructions/mcp_server_tools.txt"
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"
AZURE_TELEMETRY_ENABLED = False


trace_scenario = "Zava Agent Initialization"
tracer = trace.get_tracer("zava_agent.tracing")


class AgentManager:
    """Manages Azure AI Agent lifecycle and dependencies."""

    async def _setup_tools(self) -> None:
        """Setup MCP tools and code interpreter."""
        # Fetch and build MCP tools dynamically
        self.mcp_tools = await fetch_and_build_mcp_tools()
        self.toolset.add(self.mcp_tools)

        # Add code interpreter tool
        code_interpreter = CodeInterpreterTool()
        self.toolset.add(code_interpreter)

    def __init__(self) -> None:
        self.utilities = Utilities()
        self.agents_client: AgentsClient | None = None
        self.project_client: AIProjectClient | None = None
        self.agent: Agent | None = None
        self.thread: AgentThread | None = None
        self.mcp_tools: AsyncFunctionTool | None = None
        self.toolset = AsyncToolSet()

    async def initialize(self, instructions_file: str) -> bool:
        """Initialize the agent with tools and instructions."""
        try:
            # Validate configuration
            Config.validate_required_env_vars()

            # Load instructions
            instructions = self.utilities.load_instructions(instructions_file)

            # Validate Azure Entra ID Authentication
            credential = await self.utilities.validate_azure_authentication()
            print("✅ Azure Entra ID authentication successful!")

            # Create clients
            self.agents_client = AgentsClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            self.project_client = AIProjectClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            # Setup tools
            await self._setup_tools()

            # Enable Azure Monitor Telemetry
            if AZURE_TELEMETRY_ENABLED:
                configure_azure_monitor(connection_string=await self.project_client.telemetry.get_connection_string())

            with tracer.start_as_current_span(trace_scenario):
                # Create agent
                print("Creating agent...")
                self.agent = await self.agents_client.create_agent(
                    model=Config.API_DEPLOYMENT_NAME,
                    name=Config.AGENT_NAME,
                    instructions=instructions,
                    toolset=self.toolset,
                    temperature=Config.TEMPERATURE,
                )
                print(f"Created agent, ID: {self.agent.id}")

                # Enable auto function calls
                self.agents_client.enable_auto_function_calls(tools=self.toolset)
                print("Enabled auto function calls.")

                # Create thread
                print("Creating thread...")
                self.thread = await self.agents_client.threads.create()
                print(f"Created thread, ID: {self.thread.id}")

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


# Application components
agent_manager = AgentManager()
utilities = Utilities()
web_interface: WebInterface | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    # Startup
    print("Initializing agent on startup...")

    # Initialize agent
    success = await agent_manager.initialize(INSTRUCTIONS_FILE)

    if not success:
        print(f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    elif agent_manager.is_initialized:
        print(f"✅ Agent initialized successfully with ID: {agent_manager.agent.id}")
        web_interface.inject_dependencies(*agent_manager.get_dependencies())

    yield

    # Shutdown
    await agent_manager.cleanup()


# FastAPI app with lifespan
app = FastAPI(title="Azure AI Agent Chat", lifespan=lifespan)

# Initialize web interface
web_interface = WebInterface(app, utilities, tracer)


if __name__ == "__main__":
    import uvicorn

    print("Starting web server...")
    uvicorn.run(app, host="127.0.0.1", port=8005)
