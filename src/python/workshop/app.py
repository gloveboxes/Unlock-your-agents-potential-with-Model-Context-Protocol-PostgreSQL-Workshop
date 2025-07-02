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
from config import Config

# from agent_manager import AgentManager
from fastapi import FastAPI
from mcp_client import fetch_and_build_mcp_tools
from terminal_colors import TerminalColors as tc
from utilities import Utilities
from web_interface import WebInterface

logger = logging.getLogger(__name__)
# Configure logging - suppress verbose Azure SDK logs
logging.basicConfig(level=logging.ERROR)
for logger_name in [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.ai.agents",
    "azure.ai.projects",
    "azure.core",
    "azure.identity",
    "uvicorn.access"  # Suppress uvicorn access logs
]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Configuration
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"


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

            # Authenticate
            print("🔐 Validating Azure authentication...")
            credential = await self.utilities.validate_azure_authentication()
            print("✅ Azure authentication successful!")

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

            # Load instructions
            instructions = self.utilities.load_instructions(instructions_file)

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
                await self.utilities.cleanup_agent_resources(
                    self.agent, self.thread, self.agents_client
                )
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
    success = await agent_manager.initialize(INSTRUCTIONS_FILE)

    if not success:
        print(
            f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    else:
        print(
            f"✅ Agent initialized successfully with ID: {agent_manager.agent.id}")

        # Inject dependencies into web interface
        if web_interface and agent_manager.is_initialized:
            web_interface.inject_dependencies(
                *agent_manager.get_dependencies())

    yield

    # Shutdown
    await agent_manager.cleanup()


# FastAPI app with lifespan
app = FastAPI(title="Azure AI Agent Chat", lifespan=lifespan)

# Initialize web interface
web_interface = WebInterface(app, utilities)


async def main() -> None:
    """
    Run the FastAPI web application.
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
    """
    print("Starting Azure AI Agent Web Chat...")
    print("The web interface will be available at http://127.0.0.1:8005")
    print("Access the chat interface in your browser after startup completes.")


if __name__ == "__main__":
    import uvicorn

    print("Starting web server...")
    uvicorn.run(app, host="127.0.0.1", port=8005)
