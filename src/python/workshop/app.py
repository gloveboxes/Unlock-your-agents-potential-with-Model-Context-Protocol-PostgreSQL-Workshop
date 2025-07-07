"""
Azure AI Agent Chat Application

This application creates an AI agent that can interact with a PostgreSQL database
using Model Context Protocol (MCP) tools and provides a web interface for chat.

To run: python app.py
Web interface available at: http://127.0.0.1:8005
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from agent_manager import AgentManager
from azure.ai.agents.models import CodeInterpreterTool
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
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"
TELEMETRY_ENABLED = False

tracer = trace.get_tracer("zava_agent.tracing")


async def setup_tools(agent_manager: AgentManager) -> None:
    """Setup MCP tools and code interpreter for the agent."""
    # Fetch and build MCP tools dynamically
    mcp_tools = await fetch_and_build_mcp_tools()
    
    # Add code interpreter tool to the toolset
    code_interpreter = CodeInterpreterTool()
    agent_manager.toolset.add(code_interpreter)
    
    # Setup tools in agent manager
    await agent_manager.setup_tools(mcp_tools)


# Application components
agent_manager = AgentManager()
utilities = Utilities()
web_interface: WebInterface | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    # Startup
    print("Initializing agent on startup...")
    
    # Setup tools first
    await setup_tools(agent_manager)
    
    # Initialize agent
    success = await agent_manager.initialize(INSTRUCTIONS_FILE, TELEMETRY_ENABLED)

    if not success:
        print(
            f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    elif agent_manager.is_initialized:
        print(
            f"✅ Agent initialized successfully with ID: {agent_manager.agent.id}")
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
