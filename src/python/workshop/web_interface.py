import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, List

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    Agent,
    AgentThread,
    AsyncFunctionTool,
)
from azure.ai.projects.aio import AIProjectClient
from config import Config
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from stream_event_handler import WebStreamEventHandler
from utilities import Utilities


class WebInterface:
    """Handles all web interface functionality for the AI Agent Chat application."""
    
    def __init__(self, app: FastAPI, utilities: Utilities, tracer: trace) -> None:
        """Initialize the web interface with FastAPI app and utilities."""
        self.app = app
        self.utilities = utilities
        self.chat_sessions: Dict[str, List[Dict]] = {}
        self.tracer = tracer
        
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
        self.app.get("/files/{filename}")(self.serve_file)
    
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
            # Create the web streaming event handler
            web_handler = WebStreamEventHandler(
                self.utilities, self.agents_client
            )

            # Create a span for this chat request with more descriptive naming
            # Truncate message for span name to keep it readable
            message_preview = message[:50] + "..." if len(message) > 50 else message
            span_name = f"Zava Agent Chat Request: {message_preview}"
            
            with self.tracer.start_as_current_span(span_name) as span:
                # Add some attributes to the span for better observability
                span.set_attribute("user_message_length", len(message))
                span.set_attribute("session_id", session_id)
                span.set_attribute("user_message", message)  # Full message in attributes
                span.set_attribute("operation_type", "chat_request")
                span.set_attribute("agent_id", self.agent.id)
                span.set_attribute("thread_id", self.thread.id)
                
                # Create message in thread
                with self.tracer.start_as_current_span("create_user_message") as message_span:
                    await self.agents_client.messages.create(
                        thread_id=self.thread.id,
                        role="user",
                        content=message,
                    )
                    message_span.set_attribute("thread_id", self.thread.id)

                # Start the agent stream
                with self.tracer.start_as_current_span("agent_stream_processing") as stream_span:
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
                        stream_span.set_attribute("agent_id", self.agent.id)
                        stream_span.set_attribute("max_completion_tokens", Config.MAX_COMPLETION_TOKENS)
                    except Exception as e:
                        print(f"❌ Error in agent stream: {e}")
                        import traceback
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

            # Stream tokens as they arrive
            while True:
                try:
                    # Wait for next token with timeout
                    item = await asyncio.wait_for(web_handler.token_queue.get(), timeout=10.0)
                    print(f"🔍 DEBUG: Received item from queue: {item}")  # Debug
                    if item is None:  # End of stream signal
                        break
                    
                    # Send item to web client based on type
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            yield f"data: {json.dumps({'content': item['content']})}\n\n"
                        elif item.get("type") == "file":
                            print(f"🔍 DEBUG: Sending file to client: {item['file_info']}")  # Debug
                            yield f"data: {json.dumps({'file': item['file_info']})}\n\n"
                        elif item.get("type") == "error":
                            print(f"❌ Sending error to client: {item['error']}")  # Debug
                            yield f"data: {json.dumps({'error': item['error']})}\n\n"
                    else:
                        # Backwards compatibility for plain text
                        yield f"data: {json.dumps({'content': item})}\n\n"
                    
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'error': 'Response timeout after 60 seconds'})}\n\n"
                    break

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
    
    async def serve_file(self, filename: str) -> FileResponse:
        """Serve files from the shared files directory."""
        files_dir = Path(self.utilities.shared_files_path) / "files"
        file_path = files_dir / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Security check: ensure the file is within the files directory
        try:
            file_path.resolve().relative_to(files_dir.resolve())
        except ValueError as e:
            raise HTTPException(status_code=403, detail="Access denied") from e
        
        return FileResponse(path=str(file_path))
