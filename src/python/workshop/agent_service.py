"""
Azure AI Agent Service

This service creates an AI agent that can interact with a PostgreSQL database
using Model Context Protocol (MCP) tools and provides a REST API for chat.

To run: python agent_service.py
REST API available at: http://127.0.0.1:8006
"""

import sys
from pathlib import Path

# Add the mcp_server directory to the path
sys.path.append(str(Path(__file__).parent.parent / "mcp_server"))

import asyncio
import contextlib
import logging
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, cast

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncToolSet, CodeInterpreterTool
from azure.ai.projects.aio import AIProjectClient
from azure.monitor.opentelemetry import configure_azure_monitor
from config import Config
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from mcp_client import MCPClient  # type: ignore
from opentelemetry import trace
from pydantic import BaseModel
from stream_event_handler import WebStreamEventHandler
from terminal_colors import TerminalColors as tc
from utilities import Utilities

# Configure logging - suppress verbose Azure SDK logs
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)
Utilities.suppress_logs()

# Agent Instructions
INSTRUCTIONS_FILE = "instructions/mcp_server_tools.txt"
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"

RESPONSE_TIMEOUT_SECONDS = 60

trace_scenario = "Zava Agent Initialization"
tracer = trace.get_tracer("zava_agent.tracing")
mcp_client = MCPClient.create_default()

tools = [
    {"type": "mcp", "server_label": "ZavaMcpServer", "server_url": Config.DEV_TUNNEL_URL, "require_approval": "never"},
    {
        "type": "code_interpreter",
    },
]


# Pydantic models for API
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    content: Optional[str] = None
    file_info: Optional[Dict] = None
    error: Optional[str] = None
    done: bool = False


class AgentManager:
    """Manages Azure AI Agent lifecycle and dependencies."""

    async def _setup_tools(self) -> None:
        """Setup MCP tools and code interpreter."""

        mcp_tools = await mcp_client.build_function_tools()
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
            configure_azure_monitor(connection_string=await self.project_client.telemetry.get_connection_string())

            with tracer.start_as_current_span(trace_scenario):
                # Create agent
                print("Creating agent...")
                if not Config.MODEL_DEPLOYMENT_NAME:
                    raise ValueError("Config.MODEL_DEPLOYMENT_NAME must not be None")
                self.agent = await self.agents_client.create_agent(
                    model=Config.MODEL_DEPLOYMENT_NAME,
                    name=Config.AGENT_NAME,
                    instructions=instructions,
                    toolset=self.toolset,
                    # tools=tools,
                    temperature=Config.TEMPERATURE,
                )
                print(f"Created agent, ID: {self.agent.id}")

                # Enable auto function calls
                try:
                    self.agents_client.enable_auto_function_calls(tools=self.toolset)
                    print("Enabled auto function calls.")
                except Exception as e:
                    pass  # Ignore as there may be no tools

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
        await mcp_client.close_session()

        # Clean up agent resources
        if self.agent and self.thread and self.agents_client:
            try:
                await self.utilities.cleanup_agent_resources(self.agent, self.thread, self.agents_client)
                print("Agent resources cleaned up.")
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")

    @property
    def is_initialized(self) -> bool:
        """Check if agent is properly initialized."""
        return all([self.agents_client, self.project_client, self.agent, self.thread])


class AgentService:
    """REST API service for the Azure AI Agent."""

    def __init__(self) -> None:
        self.agent_manager = AgentManager()
        self.utilities = Utilities()
        self.chat_sessions: Dict[str, List[Dict]] = {}

    async def process_chat_message(self, request: ChatRequest) -> AsyncGenerator[ChatResponse, None]:
        """Process chat message and stream responses."""
        if not request.message.strip():
            yield ChatResponse(error="Empty message")
            return

        if not self.agent_manager.is_initialized:
            yield ChatResponse(error="Agent not initialized")
            return

        # Type guards - ensure all required components are available
        if not self.agent_manager.agents_client or not self.agent_manager.agent or not self.agent_manager.thread:
            yield ChatResponse(error="Agent components not properly initialized")
            return

        # Get or create session
        session_id = request.session_id or "default"
        if session_id not in self.chat_sessions:
            self.chat_sessions[session_id] = []

        # Add user message to session
        self.chat_sessions[session_id].append({"role": "user", "content": request.message})

        try:
            # Create the web streaming event handler
            web_handler = WebStreamEventHandler(self.utilities, self.agent_manager.agents_client)

            # Create a span for this chat request
            message_preview = request.message[:50] + "..." if len(request.message) > 50 else request.message
            span_name = f"Zava Agent Chat Request: {message_preview}"

            with tracer.start_as_current_span(span_name) as span:
                # Add some attributes to the span for better observability
                span.set_attribute("user_message", request.message)
                span.set_attribute("operation_type", "chat_request")
                span.set_attribute("agent_id", self.agent_manager.agent.id)
                span.set_attribute("thread_id", self.agent_manager.thread.id)

                # Create message in thread
                with tracer.start_as_current_span("create_user_message") as message_span:
                    await self.agent_manager.agents_client.messages.create(
                        thread_id=self.agent_manager.thread.id,
                        role="user",
                        content=request.message,
                    )
                    message_span.set_attribute("thread_id", self.agent_manager.thread.id)

                # Start the agent stream
                with tracer.start_as_current_span("agent_stream_processing") as stream_span:
                    # Start the stream in a background task
                    async def run_stream() -> None:
                        # Capture references with type casts since we've already checked they're not None
                        agents_client = cast(AgentsClient, self.agent_manager.agents_client)
                        agent = cast(Agent, self.agent_manager.agent)
                        thread = cast(AgentThread, self.agent_manager.thread)

                        try:
                            async with await agents_client.runs.stream(
                                thread_id=thread.id,
                                agent_id=agent.id,
                                event_handler=web_handler,
                                max_completion_tokens=Config.MAX_COMPLETION_TOKENS,
                                max_prompt_tokens=Config.MAX_PROMPT_TOKENS,
                                temperature=Config.TEMPERATURE,
                                top_p=Config.TOP_P,
                                instructions=agent.instructions,
                            ) as stream:
                                await stream.until_done()
                            stream_span.set_attribute("agent_id", agent.id)
                            stream_span.set_attribute("max_completion_tokens", Config.MAX_COMPLETION_TOKENS)
                        except Exception as e:
                            print(f"❌ Error in agent stream: {e}")
                            traceback.print_exc()
                            # Send error to client
                            await web_handler.token_queue.put({"type": "error", "error": str(e)})
                            span.set_attribute("error", True)
                            span.set_attribute("error_message", str(e))
                            stream_span.set_attribute("error", True)
                            stream_span.set_attribute("error_message", str(e))
                        finally:
                            # Signal end of stream
                            await web_handler.token_queue.put(None)

                    # Start the stream task
                    stream_task = asyncio.create_task(run_stream())

            # Stream tokens as they arrive
            try:
                while True:
                    try:
                        # Wait for next token with timeout
                        item = await asyncio.wait_for(web_handler.token_queue.get(), timeout=RESPONSE_TIMEOUT_SECONDS)
                        if item is None:  # End of stream signal
                            break

                        # Yield response based on type
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                yield ChatResponse(content=item["content"])
                            elif item.get("type") == "file":
                                yield ChatResponse(file_info=item["file_info"])
                            elif item.get("type") == "error":
                                yield ChatResponse(error=item["error"])
                        else:
                            # Backwards compatibility for plain text
                            yield ChatResponse(content=str(item))

                    except asyncio.TimeoutError:
                        yield ChatResponse(error="Response timeout after 60 seconds")
                        break
            finally:
                # Ensure the stream task is properly cleaned up
                if not stream_task.done():
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task

            # Add complete message to session
            if web_handler.assistant_message:
                self.chat_sessions[session_id].append({"role": "assistant", "content": web_handler.assistant_message})

            # Send completion signal
            yield ChatResponse(done=True)

        except Exception as e:
            yield ChatResponse(error=f"Streaming error: {e!s}")


# Global service instance
agent_service = AgentService()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    # Startup
    print("Initializing agent service on startup...")

    # Initialize agent
    success = await agent_service.agent_manager.initialize(INSTRUCTIONS_FILE)

    if not success:
        print(f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    elif agent_service.agent_manager.is_initialized and agent_service.agent_manager.agent:
        print(f"✅ Agent initialized successfully with ID: {agent_service.agent_manager.agent.id}")

    yield

    # Shutdown
    await agent_service.agent_manager.cleanup()


# FastAPI app with lifespan
app = FastAPI(title="Azure AI Agent Service", lifespan=lifespan)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_initialized": agent_service.agent_manager.is_initialized,
        "agent_id": agent_service.agent_manager.agent.id if agent_service.agent_manager.agent else None,
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
        raise HTTPException(status_code=404, detail="File not found")

    # Security check: ensure the file is within the files directory
    try:
        file_path.resolve().relative_to(files_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    return FileResponse(path=str(file_path))


if __name__ == "__main__":
    import uvicorn

    print("Starting agent service...")
    uvicorn.run(app, host="127.0.0.1", port=8006)
