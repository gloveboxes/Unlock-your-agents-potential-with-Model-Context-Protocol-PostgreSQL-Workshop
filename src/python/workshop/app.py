import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Dict, List

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    Agent,
    AgentThread,
    AsyncFunctionTool,
    AsyncToolSet,
    CodeInterpreterTool,
    MessageDeltaChunk,
)
from azure.ai.projects.aio import AIProjectClient
from azure.core.exceptions import ClientAuthenticationError
from config import Config
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp_client import cleanup_global_mcp_client, fetch_and_build_mcp_tools
from stream_event_handler import StreamEventHandler
from terminal_colors import TerminalColors as tc
from utilities import Utilities

# Configure logging to suppress verbose Azure SDK logs
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Specifically suppress Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.ai.agents").setLevel(logging.WARNING)
logging.getLogger("azure.ai.projects").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

INSTRUCTIONS_FILE = None

toolset = AsyncToolSet()
utilities = Utilities()

# Global clients and resources
agents_client = None
project_client = None
agent = None
thread = None
mcp_tools = None  # Will be populated dynamically with MCP tools

# Store chat sessions (in production, use a database)
chat_sessions: Dict[str, List[Dict]] = {}

INSTRUCTIONS_FILE = "instructions/mcp_server_tools.txt"
INSTRUCTIONS_FILE = "instructions/mcp_server_tools_with_code_interpreter.txt"


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events"""
    # Startup
    global agent, thread
    print("Initializing agent on startup...")
    agent, thread = await initialize_agent()
    if not agent or not thread:
        print(f"{tc.BG_BRIGHT_RED}Agent initialization failed. Check your configuration.{tc.RESET}")
    else:
        print(f"✅ Agent initialized successfully with ID: {agent.id}")
    
    yield
    
    # Shutdown
    if agent and thread and agents_client:
        try:
            await cleanup(agent, thread, agents_client)
            print("Agent resources cleaned up.")
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")


# FastAPI app with lifespan
app = FastAPI(title="Azure AI Agent Chat", lifespan=lifespan)

# Mount static files
static_dir = Path(__file__).parent.parent.parent / "shared" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


async def add_agent_tools() -> None:
    """Add tools for the agent."""
    global mcp_tools

    # Fetch and build MCP tools dynamically
    mcp_tools = await fetch_and_build_mcp_tools()

    # Add the MCP tools to the toolset
    toolset.add(mcp_tools)

    # Add the code interpreter tool
    code_interpreter = CodeInterpreterTool()
    toolset.add(code_interpreter)


async def initialize_agent() -> tuple[Agent | None, AgentThread | None]:
    """Initialize the agent with the MCP tools and instructions."""
    global agents_client, project_client, agent, thread

    if not INSTRUCTIONS_FILE:
        return None, None

    try:
        # Validate configuration first
        Config.validate_required_env_vars()

        # Validate Azure authentication
        print("🔐 Validating Azure authentication...")
        credential = await utilities.validate_azure_authentication()
        print("✅ Azure authentication successful!")

        # Create clients after authentication is validated
        agents_client = AgentsClient(
            credential=credential,
            endpoint=Config.PROJECT_ENDPOINT,
        )

        project_client = AIProjectClient(
            credential=credential,
            endpoint=Config.PROJECT_ENDPOINT,
        )

        await add_agent_tools()

        instructions = utilities.load_instructions(INSTRUCTIONS_FILE)

        if not Config.API_DEPLOYMENT_NAME:
            raise ValueError("MODEL_DEPLOYMENT_NAME environment variable is required")

        print("Creating agent...")
        agent = await agents_client.create_agent(
            model=Config.API_DEPLOYMENT_NAME,
            name=Config.AGENT_NAME,
            instructions=instructions,
            toolset=toolset,
            temperature=Config.TEMPERATURE,
        )
        print(f"Created agent, ID: {agent.id}")

        agents_client.enable_auto_function_calls(tools=toolset)
        print("Enabled auto function calls.")

        print("Creating thread...")
        thread = await agents_client.threads.create()
        print(f"Created thread, ID: {thread.id}")

        return agent, thread

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        return None, None


async def cleanup(agent: Agent | None, thread: AgentThread | None, agents_client_instance: AgentsClient | None = None) -> None:
    """Cleanup the Azure AI resources."""
    await cleanup_global_mcp_client()
    if agent and thread and agents_client_instance:
        try:
            existing_files = await agents_client_instance.files.list()
            for f in existing_files.data:
                await agents_client_instance.files.delete(f.id)
            await agents_client_instance.threads.delete(thread.id)
            await agents_client_instance.delete_agent(agent.id)
        except Exception as e:
            print(f"⚠️  Warning: Error during Azure cleanup: {e}")


async def post_message(thread_id: str, content: str, agent: Agent, thread: AgentThread, agents_client_instance: AgentsClient) -> None:
    """Post a message to the Foundry Agent Service."""
    try:
        await agents_client_instance.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )

        async with await agents_client_instance.runs.stream(
            thread_id=thread.id,
            agent_id=agent.id,
            event_handler=StreamEventHandler(
                functions=mcp_tools if mcp_tools else AsyncFunctionTool(set()),
                project_client=(
                    project_client
                    if project_client is not None
                    else AIProjectClient(
                        credential=utilities.get_credential(),
                        endpoint=Config.PROJECT_ENDPOINT,
                    )
                ),
                agents_client=agents_client_instance,
                utilities=utilities,
            ),
            max_completion_tokens=Config.MAX_COMPLETION_TOKENS,
            max_prompt_tokens=Config.MAX_PROMPT_TOKENS,
            temperature=Config.TEMPERATURE,
            top_p=Config.TOP_P,
            instructions=agent.instructions,
        ) as stream:
            await stream.until_done()

    except Exception as e:
        utilities.log_msg_purple(f"An error occurred posting the message: {e!s}")


async def main() -> None:
    """
    Run the FastAPI web application.
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
    """
    print("Starting Azure AI Agent Web Chat...")
    print("The web interface will be available at http://127.0.0.1:8005")
    print("Access the chat interface in your browser after startup completes.")



@app.get("/", response_class=HTMLResponse)
async def get_chat_page() -> HTMLResponse:
    """Serve the chat HTML page"""
    html_file = Path(__file__).parent.parent.parent / "shared" / "static" / "index.html"
    with html_file.open("r") as f:
        return HTMLResponse(content=f.read())


@app.post("/upload")
async def upload_file(file: UploadFile, message: str = Form(None)) -> Dict:
    """Handle file upload and extract text content"""
    try:
        # Check file size (10MB limit)
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            return {"error": "File size too large (max 10MB)"}

        # Extract text based on file type
        file_text = ""
        file_extension = (
            file.filename.lower().split(".")[-1] if "." in file.filename else ""
        )

        if file_extension in ["txt", "md"]:
            file_text = content.decode("utf-8")
        elif file_extension in ["pdf"]:
            # For PDF files, you might want to add PyPDF2 or similar
            file_text = f"[PDF file content - filename: {file.filename}]\nNote: PDF parsing not implemented yet. Please describe what you'd like me to help you with regarding this PDF file."
        elif file_extension in ["doc", "docx"]:
            # For Word files, you might want to add python-docx
            file_text = f"[Word document content - filename: {file.filename}]\nNote: Word document parsing not implemented yet. Please describe what you'd like me to help you with regarding this document."
        else:
            # Try to read as text for other file types
            try:
                file_text = content.decode("utf-8")
            except UnicodeDecodeError:
                file_text = f"[Binary file - filename: {file.filename}]\nNote: Cannot read binary file content. Please describe what you'd like me to help you with regarding this file."

        # Prepare the message with file content
        if message:
            combined_message = (
                f"{message}\n\nFile content from '{file.filename}':\n\n{file_text}"
            )
        else:
            combined_message = f"Please analyze this file content from '{file.filename}':\n\n{file_text}"

        return {"content": combined_message, "filename": file.filename}

    except Exception as e:
        return {"error": f"Error processing file: {e!s}"}


@app.get("/chat/stream")
async def stream_chat(message: str = "") -> StreamingResponse:
    """Stream chat responses using Server-Sent Events"""
    global agent, thread, agents_client

    if not message.strip():
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'Empty message'})}\n\n"]),
            media_type="text/event-stream",
        )

    if not agent or not thread or not agents_client:
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'Agent not initialized'})}\n\n"]),
            media_type="text/event-stream",
        )

    # Get or create session (simplified - using a single session)
    session_id = "default"
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []

    # Add user message to session
    chat_sessions[session_id].append({"role": "user", "content": message})

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # Create a custom streaming event handler that captures tokens for web output
            class WebStreamEventHandler(StreamEventHandler):
                def __init__(self) -> None:
                    super().__init__(
                        functions=mcp_tools if mcp_tools else AsyncFunctionTool(set()),
                        project_client=project_client,
                        agents_client=agents_client,
                        utilities=utilities,
                    )
                    self.assistant_message = ""
                    self.token_queue: asyncio.Queue = asyncio.Queue()

                async def on_message_delta(self, delta: MessageDeltaChunk) -> None:
                    """Override to capture tokens for web streaming instead of terminal output"""
                    if delta.text:
                        self.assistant_message += delta.text
                        # Put token in queue for web streaming instead of printing to terminal
                        await self.token_queue.put(delta.text)
                    
                    # Don't call the parent method which would print to terminal
                    # super().on_message_delta(delta) - skip this to avoid terminal output

            # Create the event handler
            web_handler = WebStreamEventHandler()

            # Post message to the agent thread
            await agents_client.messages.create(
                thread_id=thread.id,
                role="user",
                content=message,
            )

            # Start the agent stream in a background task
            async def run_agent() -> None:
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
                finally:
                    # Signal end of stream
                    await web_handler.token_queue.put(None)

            # Start the agent processing
            agent_task = asyncio.create_task(run_agent())

            # Stream tokens as they arrive
            while True:
                try:
                    # Wait for next token with timeout
                    token = await asyncio.wait_for(web_handler.token_queue.get(), timeout=60.0)
                    if token is None:  # End of stream signal
                        break
                    
                    # Send token to web client
                    yield f"data: {json.dumps({'content': token})}\n\n"
                    
                    # Small delay to make streaming visible
                    # await asyncio.sleep(0.01)
                    
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'error': 'Response timeout after 60 seconds'})}\n\n"
                    break

            # Wait for agent task to complete
            try:
                await asyncio.wait_for(agent_task, timeout=5.0)
            except asyncio.TimeoutError:
                agent_task.cancel()

            # Add complete message to session
            if web_handler.assistant_message:
                chat_sessions[session_id].append({
                    "role": "assistant", 
                    "content": web_handler.assistant_message
                })

            # Send completion signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': 'Streaming error: ' + str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache", 
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        },
    )


if __name__ == "__main__":
    import uvicorn
    
    print("Starting web server...")
    uvicorn.run(app, host="127.0.0.1", port=8005)
