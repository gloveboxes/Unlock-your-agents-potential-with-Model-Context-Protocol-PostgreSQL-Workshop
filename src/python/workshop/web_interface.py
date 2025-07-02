import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, List

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, MessageDeltaChunk
from azure.ai.projects.aio import AIProjectClient
from config import Config
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from stream_event_handler import StreamEventHandler
from utilities import Utilities


class WebInterface:
    """Handles all web interface functionality for the AI Agent Chat application."""
    
    def __init__(self, app: FastAPI, utilities: Utilities) -> None:
        """Initialize the web interface with FastAPI app and utilities."""
        self.app = app
        self.utilities = utilities
        self.chat_sessions: Dict[str, List[Dict]] = {}
        
        # These will be injected by the main app
        self.agents_client: AgentsClient | None = None
        self.project_client: AIProjectClient | None = None
        self.agent: Agent | None = None
        self.thread: AgentThread | None = None
        self.mcp_tools: AsyncFunctionTool | None = None
        
        self._setup_routes()
        self._setup_static_files()
    
    def inject_dependencies(self, agents_client: AgentsClient, project_client: AIProjectClient, 
                          agent: Agent, thread: AgentThread, mcp_tools: AsyncFunctionTool) -> None:
        """Inject the agent-related dependencies after initialization."""
        self.agents_client = agents_client
        self.project_client = project_client
        self.agent = agent
        self.thread = thread
        self.mcp_tools = mcp_tools
    
    def _setup_static_files(self) -> None:
        """Setup static file serving."""
        static_dir = Path(__file__).parent.parent.parent / "shared" / "static"
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    def _setup_routes(self) -> None:
        """Setup all web routes."""
        self.app.get("/", response_class=HTMLResponse)(self.get_chat_page)
        self.app.post("/upload")(self.upload_file)
        self.app.get("/chat/stream")(self.stream_chat)
    
    async def get_chat_page(self) -> HTMLResponse:
        """Serve the chat HTML page."""
        html_file = Path(__file__).parent.parent.parent / "shared" / "static" / "index.html"
        with html_file.open("r") as f:
            return HTMLResponse(content=f.read())
    
    async def upload_file(self, file: UploadFile, message: str = Form(None)) -> Dict:
        """Handle file upload and extract text content."""
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
    
    async def stream_chat(self, message: str = "") -> StreamingResponse:
        """Stream chat responses using Server-Sent Events."""
        if not message.strip():
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': 'Empty message'})}\n\n"]),
                media_type="text/event-stream",
            )

        if not self.agent or not self.thread or not self.agents_client:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': 'Agent not initialized'})}\n\n"]),
                media_type="text/event-stream",
            )

        # Get or create session (simplified - using a single session)
        session_id = "default"
        if session_id not in self.chat_sessions:
            self.chat_sessions[session_id] = []

        # Add user message to session
        self.chat_sessions[session_id].append({"role": "user", "content": message})

        return StreamingResponse(
            self._generate_stream(message, session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache", 
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            },
        )
    
    async def _generate_stream(self, message: str, session_id: str) -> AsyncGenerator[str, None]:
        """Generate streaming response for chat."""
        try:
            # Create a custom streaming event handler that captures tokens for web output
            class WebStreamEventHandler(StreamEventHandler):
                def __init__(self, utilities: Utilities, mcp_tools: AsyncFunctionTool, 
                           project_client: AIProjectClient, agents_client: AgentsClient) -> None:
                    super().__init__(
                        functions=mcp_tools if mcp_tools else AsyncFunctionTool(set()),
                        project_client=project_client,
                        agents_client=agents_client,
                        utilities=utilities,
                    )
                    self.assistant_message = ""
                    self.token_queue: asyncio.Queue = asyncio.Queue()

                async def on_message_delta(self, delta: MessageDeltaChunk) -> None:
                    """Override to capture tokens for web streaming instead of terminal output."""
                    if delta.text:
                        self.assistant_message += delta.text
                        # Put token in queue for web streaming instead of printing to terminal
                        await self.token_queue.put(delta.text)
                    
                    # Don't call the parent method which would print to terminal
                    # super().on_message_delta(delta) - skip this to avoid terminal output

            # Create the event handler
            web_handler = WebStreamEventHandler(
                self.utilities, self.mcp_tools, self.project_client, self.agents_client
            )

            # Post message to the agent thread
            await self.agents_client.messages.create(
                thread_id=self.thread.id,
                role="user",
                content=message,
            )

            # Start the agent stream in a background task
            async def run_agent() -> None:
                try:
                    async with await self.agents_client.runs.stream(
                        thread_id=self.thread.id,
                        agent_id=self.agent.id,
                        event_handler=web_handler,
                        max_completion_tokens=Config.MAX_COMPLETION_TOKENS,
                        max_prompt_tokens=Config.MAX_PROMPT_TOKENS,
                        temperature=Config.TEMPERATURE,
                        top_p=Config.TOP_P,
                        instructions=self.agent.instructions,
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
                self.chat_sessions[session_id].append({
                    "role": "assistant", 
                    "content": web_handler.assistant_message
                })

            # Send completion signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': 'Streaming error: ' + str(e)})}\n\n"
