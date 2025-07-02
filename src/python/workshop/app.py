import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Tuple

# from agent_manager import AgentManager
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, AsyncToolSet, CodeInterpreterTool
from azure.ai.projects.aio import AIProjectClient
from config import Config
from fastapi import FastAPI
from mcp_client import fetch_and_build_mcp_tools
from terminal_colors import TerminalColors as tc
from utilities import Utilities
from web_interface import WebInterface

# Configure logging to suppress verbose Azure SDK logs
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Specifically suppress Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.ai.agents").setLevel(logging.WARNING)
logging.getLogger("azure.ai.projects").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

# Configuration
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"

class AgentManager:
    """Manages Azure AI Agent initialization, configuration, and lifecycle."""
    
    def __init__(self, utilities: Utilities, instructions_file: str) -> None:
        """Initialize the agent manager."""
        self.utilities = utilities
        self.instructions_file = instructions_file
        self.toolset = AsyncToolSet()
        
        # Agent-related resources
        self.agents_client: AgentsClient | None = None
        self.project_client: AIProjectClient | None = None
        self.agent: Agent | None = None
        self.thread: AgentThread | None = None
        self.mcp_tools: AsyncFunctionTool | None = None
    
    async def initialize_agent(self) -> Tuple[Agent | None, AgentThread | None]:
        """Initialize the agent with the MCP tools and instructions."""
        if not self.instructions_file:
            return None, None

        try:
            # Validate configuration first
            Config.validate_required_env_vars()

            # Validate Azure authentication
            print("🔐 Validating Azure authentication...")
            credential = await self.utilities.validate_azure_authentication()
            print("✅ Azure authentication successful!")

            # Create clients after authentication is validated
            self.agents_client = AgentsClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            self.project_client = AIProjectClient(
                credential=credential,
                endpoint=Config.PROJECT_ENDPOINT,
            )

            await self._add_agent_tools()

            instructions = self.utilities.load_instructions(self.instructions_file)

            if not Config.API_DEPLOYMENT_NAME:
                raise ValueError("MODEL_DEPLOYMENT_NAME environment variable is required")

            print("Creating agent...")
            self.agent = await self.agents_client.create_agent(
                model=Config.API_DEPLOYMENT_NAME,
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

            return self.agent, self.thread

        except Exception as e:
            logger.error("An error occurred initializing the agent: %s", str(e))
            logger.error("Please ensure you've enabled an instructions file.")
            return None, None
    
    async def _add_agent_tools(self) -> None:
        """Add tools for the agent."""
        # Fetch and build MCP tools dynamically
        self.mcp_tools = await fetch_and_build_mcp_tools()

        # Add the MCP tools to the toolset
        self.toolset.add(self.mcp_tools)

        # Add the code interpreter tool
        code_interpreter = CodeInterpreterTool()
        self.toolset.add(code_interpreter)
    
    async def cleanup_resources(self) -> None:
        """Clean up agent resources."""
        if self.agent and self.thread and self.agents_client:
            try:
                await self.utilities.cleanup_agent_resources(self.agent, self.thread, self.agents_client)
                print("Agent resources cleaned up.")
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")
    
    def get_dependencies(self) -> Tuple[AgentsClient, AIProjectClient, Agent, AgentThread, AsyncFunctionTool]:
        """Get all agent dependencies for injection into other components."""
        if not all([self.agents_client, self.project_client, self.agent, self.thread, self.mcp_tools]):
            raise RuntimeError("Agent not properly initialized")
        
        return self.agents_client, self.project_client, self.agent, self.thread, self.mcp_tools

# Global components
utilities = Utilities()
agent_manager: AgentManager | None = None
web_interface: WebInterface | None = None




@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    global agent_manager, web_interface
    
    # Startup
    print("Initializing agent on startup...")
    agent_manager = AgentManager(utilities, INSTRUCTIONS_FILE)
    agent, thread = await agent_manager.initialize_agent()
    
    if not agent or not thread:
        print(f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    else:
        print(f"✅ Agent initialized successfully with ID: {agent.id}")
        
        # Inject dependencies into web interface
        if web_interface:
            web_interface.inject_dependencies(*agent_manager.get_dependencies())
    
    yield
    
    # Shutdown
    if agent_manager:
        await agent_manager.cleanup_resources()


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
