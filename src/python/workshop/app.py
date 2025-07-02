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
from fastapi import FastAPI
from terminal_colors import TerminalColors as tc
from utilities import Utilities
from web_interface import WebInterface

# Configure logging - suppress verbose Azure SDK logs
logging.basicConfig(level=logging.ERROR)
for logger_name in [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.ai.agents",
    "azure.ai.projects", 
    "azure.core",
    "azure.identity"
]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Configuration
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"

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
        print(f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    else:
        print(f"✅ Agent initialized successfully with ID: {agent_manager.agent.id}")
        
        # Inject dependencies into web interface
        if web_interface and agent_manager.is_initialized:
            web_interface.inject_dependencies(*agent_manager.get_dependencies())
    
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
