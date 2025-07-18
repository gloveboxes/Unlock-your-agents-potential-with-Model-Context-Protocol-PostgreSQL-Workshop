"""
Azure AI Agent Web Application

This web application creates an AI agent that can interact with a PostgreSQL database
using Model Context Protocol (MCP) tools and provides a REST API for chat.

To run: python app.py
REST API available at: http://127.0.0.1:8006
"""

import logging
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "mcp_server"))
sys.path.append(str(Path(__file__).parent.parent / "shared"))

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncToolSet, CodeInterpreterTool, McpTool
from azure.ai.projects.aio import AIProjectClient
from azure.monitor.opentelemetry import configure_azure_monitor
from chat_manager import ChatManager, ChatRequest
from config import Config
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from mcp_client_sales_analysis import MCPClient  # type: ignore
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from otlp import configure_oltp_grpc_tracing  # type: ignore
from terminal_colors import TerminalColors as tc
from utilities import Utilities

# Configure logging - suppress verbose Azure SDK logs
# Auto-detection of insecure mode will happen based on endpoint
tracer = configure_oltp_grpc_tracing()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Suppress verbose Azure SDK logs if OTEL endpoint is not configured (since we're logging to console)
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") is None:
    Utilities.suppress_logs()

# Agent Instructions
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"

RESPONSE_TIMEOUT_SECONDS = 60

trace_scenario = "Zava Agent Initialization"
tracer = trace.get_tracer("zava_agent.tracing")
mcp_client = MCPClient.create_default()


class AgentManager:
    """Manages Azure AI Agent lifecycle and dependencies."""

    async def _setup_tools(self) -> None:
        """Setup MCP tools and code interpreter."""

        if Config.MAP_MCP_FUNCTIONS:
            function_tools = await mcp_client.build_function_tools()
            self.toolset.add(function_tools)
        else:
            mcp_tools = McpTool(
                server_label="ZavaSalesAnalysisMcpServer",
                server_url=Config.DEV_TUNNEL_URL,
                allowed_tools=[
                    "get_multiple_table_schemas",
                    "execute_sales_query",
                    "get_current_utc_date",
                ],
            )
            # PostgreSQL Row Level Security (RLS) User ID header
            mcp_tools.update_headers("x-rls-user-id", Config.RLS_USER_ID)
            # Disabled as specified in allowed tools
            mcp_tools.set_approval_mode("never")
            self.toolset.add(mcp_tools)

        # Add code interpreter tool
        code_interpreter = CodeInterpreterTool()
        self.toolset.add(code_interpreter)

    def __init__(self) -> None:
        self.utilities = Utilities()
        self.agents_client: AgentsClient | None = None
        self.project_client: AIProjectClient | None = None
        self.agent: Agent | None = None
        self.thread: AgentThread | None = None
        self.toolset = AsyncToolSet()
        self.mcp_tools = None

    async def initialize(self, instructions_file: str) -> bool:
        """Initialize the agent with tools and instructions."""
        try:
            # Validate configuration
            Config.validate_required_env_vars()

            # Load LLM instructions
            instructions = self.utilities.load_instructions(instructions_file)

            # Validate Azure Entra ID Authentication
            credential = await self.utilities.validate_azure_authentication()
            logger.info("✅ Azure Entra ID authentication successful!")

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
            logger.info("Setting up MCP tools...")
            await self._setup_tools()

            # Enable Azure Monitor Telemetry
            configure_azure_monitor(connection_string=await self.project_client.telemetry.get_connection_string())

            with tracer.start_as_current_span(trace_scenario):
                # Create agent
                logger.info("Creating agent...")
                if not Config.MODEL_DEPLOYMENT_NAME:
                    logger.error("Config.MODEL_DEPLOYMENT_NAME must not be None")
                    raise ValueError("Config.MODEL_DEPLOYMENT_NAME must not be None")
                self.agent = await self.agents_client.create_agent(
                    model=Config.MODEL_DEPLOYMENT_NAME,
                    name=Config.AGENT_NAME,
                    instructions=instructions,
                    toolset=self.toolset,
                    temperature=Config.TEMPERATURE,
                )
                logger.info("Created agent, ID: %s", self.agent.id)
                logger.info("Agent using MCP server at: %s", Config.DEV_TUNNEL_URL)

                # Enable auto function calls
                if self.toolset.definitions and Config.MAP_MCP_FUNCTIONS:
                    self.agents_client.enable_auto_function_calls(tools=self.toolset)
                    logger.info("Enabled auto function calls.")

                # Create thread
                logger.info("Creating thread...")
                self.thread = await self.agents_client.threads.create()
                logger.info("Created thread, ID: %s", self.thread.id)

            return True

        except Exception as e:
            logger.error("Agent initialization failed: %s", str(e))
            return False

    async def cleanup(self) -> None:
        """Clean up agent resources."""
        await mcp_client.close_session()

        # Clean up agent resources
        if self.agent and self.thread and self.agents_client:
            try:
                await self.utilities.cleanup_agent_resources(self.agent, self.thread, self.agents_client)
                logger.info("Agent resources cleaned up.")
            except Exception as e:
                logger.error("Error during cleanup: %s", e)

    @property
    def is_initialized(self) -> bool:
        """Check if agent is properly initialized."""
        return all([self.agents_client, self.project_client, self.agent, self.thread])


# Global service instance
agent_manager = AgentManager()
agent_service = ChatManager(agent_manager)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    # Startup
    logger.info("Initializing agent service on startup...")

    # Initialize agent
    success = await agent_manager.initialize(INSTRUCTIONS_FILE)

    if not success:
        logger.error("Agent initialization failed. Check your configuration.")
    elif agent_manager.is_initialized and agent_manager.agent:
        logger.info("✅ Agent initialized successfully with ID: %s", agent_manager.agent.id)

    yield

    # Shutdown
    await agent_manager.cleanup()


# FastAPI app with lifespan
app = FastAPI(title="Azure AI Agent Service", lifespan=lifespan)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_initialized": agent_manager.is_initialized,
        "agent_id": agent_manager.agent.id if agent_manager.agent else None,
    }


@app.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """Stream chat responses."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        async for response in agent_service.process_chat_message(request):
            yield f"data: {response.model_dump_json()}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Content-Encoding": "identity",
        },
    )


@app.get("/files/{filename}")
async def serve_file(filename: str) -> FileResponse:
    """Serve files from the shared files directory."""
    files_dir = Path(agent_service.utilities.shared_files_path) / "files"
    file_path = files_dir / filename

    if not file_path.exists() or not file_path.is_file():
        logger.error("File not found: %s", filename)
        raise HTTPException(status_code=404, detail="File not found")

    # Security check: ensure the file is within the files directory
    try:
        file_path.resolve().relative_to(files_dir.resolve())
    except ValueError as exc:
        logger.error("Access denied for file: %s", filename)
        raise HTTPException(status_code=403, detail="Access denied") from exc

    return FileResponse(path=str(file_path))


FastAPIInstrumentor.instrument_app(app)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8006))
    logger.info("Starting agent service on port %d", port)
    uvicorn.run(app, host="127.0.0.1", port=port)
