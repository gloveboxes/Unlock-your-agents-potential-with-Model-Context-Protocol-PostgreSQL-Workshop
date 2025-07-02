"""
Agent Manager - Handles Azure AI Agent initialization and lifecycle.
"""

import logging
from typing import Tuple

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, AsyncToolSet, CodeInterpreterTool
from azure.ai.projects.aio import AIProjectClient
from config import Config
from mcp_client import fetch_and_build_mcp_tools
from utilities import Utilities

logger = logging.getLogger(__name__)


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
    
    async def _setup_tools(self) -> None:
        """Setup MCP tools and code interpreter."""
        # Fetch and build MCP tools dynamically
        self.mcp_tools = await fetch_and_build_mcp_tools()
        self.toolset.add(self.mcp_tools)
        
        # Add code interpreter tool
        code_interpreter = CodeInterpreterTool()
        self.toolset.add(code_interpreter)
    
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
