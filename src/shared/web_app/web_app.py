"""
Web Interface for Azure AI Agent Chat

This web application provides a user interface for interacting with the AI agent
through REST API calls to the agent service.

To run: python web_app.py
Web interface available at: http://127.0.0.1:8005
"""

import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, Dict, List

import httpx
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import inject
from otlp import configure_oltp_grpc_tracing
from utilities import Utilities

logging.basicConfig(level=logging.INFO)
tracer = configure_oltp_grpc_tracing()
logger = logging.getLogger(__name__)

# Agent service configuration
AGENT_SERVICE_URL = os.environ.get(
    "services__python-agent-app__http__0", "http://127.0.0.1:8006")

static_dir = Path(__file__).parent / "static"


class WebApp:
    """Handles all web interface functionality for the AI Agent Chat application."""

    def __init__(self, app: FastAPI) -> None:
        """Initialize the web interface with FastAPI app."""
        self.app = app
        self.utilities = Utilities()
        self.chat_sessions: Dict[str, List[Dict]] = {}

        self._setup_routes()
        self._setup_static_files()

    def _setup_static_files(self) -> None:
        """Setup static file serving."""
        self.app.mount(
            "/static", StaticFiles(directory=str(static_dir)), name="static")

    def _setup_routes(self) -> None:
        """Setup all web routes."""
        self.app.get("/", response_class=HTMLResponse)(self.get_chat_page)
        self.app.get("/favicon.ico",
                     response_class=FileResponse)(self.get_favicon)
        self.app.post("/upload")(self.upload_file)
        self.app.get("/chat/stream")(self.stream_chat)
        self.app.get("/files/{filename}")(self.serve_file)
        self.app.get("/health")(self.health_check)

    async def get_chat_page(self) -> HTMLResponse:
        """Serve the chat HTML page."""
        html_file = static_dir / "index.html"
        with html_file.open("r") as f:
            return HTMLResponse(content=f.read())

    async def get_favicon(self) -> FileResponse:
        """Serve the favicon.ico file."""
        favicon_path = static_dir / "favicon.ico"
        return FileResponse(favicon_path, media_type="image/x-icon")

    async def upload_file(self, file: UploadFile, message: str = Form(None)) -> Dict:
        """Handle file upload and extract text content."""
        try:
            # Check file size (10MB limit)
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(
                    status_code=413, detail="File too large (max 10MB)")

            # Extract text based on file type
            file_text = ""
            file_extension = (
                file.filename.lower().split(
                    ".")[-1] if file.filename and "." in file.filename else ""
            )

            if file_extension in ["txt", "md"]:
                file_text = content.decode("utf-8")
            elif file_extension in ["pdf"]:
                # Could integrate PDF parsing
                file_text = f"[PDF file: {file.filename}]"
            elif file_extension in ["doc", "docx"]:
                # Could integrate Word parsing
                file_text = f"[Word document: {file.filename}]"
            else:
                file_text = f"[Uploaded file: {file.filename}]"

            # Prepare the message with file content
            if message:
                combined_message = f"{message}\n\nAttached file content:\n{file_text}"
            else:
                combined_message = f"Please analyze this file:\n\n{file_text}"

            return {"content": combined_message, "filename": file.filename}

        except Exception as e:
            return {"error": f"Error processing file: {e!s}"}

    async def stream_chat(self, message: str = "") -> StreamingResponse:
        """Stream chat responses by proxying to the agent service."""

        with tracer.start_as_current_span("stream_chat") as span:
            if not message.strip():
                return StreamingResponse(
                    iter(
                        [f"data: {json.dumps({'error': 'Empty message'})}\n\n"]),
                    media_type="text/event-stream",
                )

            # Get or create session (simplified - using a single session)
            session_id = "default"
            if session_id not in self.chat_sessions:
                self.chat_sessions[session_id] = []

            # Add user message to session
            self.chat_sessions[session_id].append(
                {"role": "user", "content": message})

            return StreamingResponse(
                self._generate_stream(message, session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*",
                    "Content-Encoding": "identity"
                },
            )

    async def _generate_stream(self, message: str, session_id: str) -> AsyncGenerator[str, None]:
        """Generate streaming response by proxying to agent service."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Make request to agent service
                request_data = {
                    "message": message,
                    "session_id": session_id
                }

                logger.info(
                    "Forwarding message to agent service: %s", request_data)
                logger.info("Agent service URL: %s", AGENT_SERVICE_URL)

                # Create headers with trace context propagation
                headers = {"Accept": "text/event-stream"}
                # Inject the current trace context into the headers
                inject(headers)  # This propagates the current span context

                async with client.stream(
                    "POST",
                    f"{AGENT_SERVICE_URL}/chat/stream",
                    json=request_data,
                    headers=headers
                ) as response:
                    if response.status_code != 200:
                        logger.error(
                            "Agent service returned error: %s", response.status_code)
                        yield f"data: {json.dumps({'error': f'Agent service error: {response.status_code}'})}\n\n"
                        return

                    assistant_message = ""
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            # Parse and forward each chunk
                            lines = chunk.strip().split('\n')
                            for line in lines:
                                if line.startswith('data: '):
                                    # Remove 'data: ' prefix
                                    data_str = line[6:]
                                    try:
                                        data = json.loads(data_str)

                                        # Convert agent service response format to web format
                                        if data.get("content"):
                                            assistant_message += data["content"]
                                            yield f"data: {json.dumps({'content': data['content']})}\n\n"
                                        elif data.get("file_info"):
                                            yield f"data: {json.dumps({'file': data['file_info']})}\n\n"
                                        elif data.get("error"):
                                            yield f"data: {json.dumps({'error': data['error']})}\n\n"
                                        elif data.get("done"):
                                            # Agent service signals completion
                                            break
                                    except json.JSONDecodeError:
                                        # Skip malformed JSON
                                        continue

                    # Add complete message to session
                    if assistant_message:
                        self.chat_sessions[session_id].append({
                            "role": "assistant",
                            "content": assistant_message
                        })

            # Send completion signal
            yield "data: [DONE]\n\n"

        except httpx.RequestError as e:
            logger.error("Error connecting to agent service: %s", e)
            yield f"data: {json.dumps({'error': f'Connection error to agent service: {e!s}'})}\n\n"
        except Exception as e:
            logger.error("Error processing chat message: %s", e)
            yield f"data: {json.dumps({'error': f'Streaming error: {e!s}'})}\n\n"

    async def serve_file(self, filename: str) -> FileResponse:
        """Proxy file serving to agent service or serve locally."""
        try:
            # Try to proxy to agent service first
            async with httpx.AsyncClient() as client:
                # Create headers and inject trace context
                headers = {}
                inject(headers)  # Propagate the current span context
                response = await client.get(f"{AGENT_SERVICE_URL}/files/{filename}", headers=headers)
                if response.status_code == 200:
                    # Save file temporarily and serve it
                    temp_file = Path("/tmp") / filename
                    with temp_file.open("wb") as f:
                        f.write(response.content)
                    return FileResponse(path=str(temp_file))
        except Exception:
            pass

        # Fallback to local file serving
        files_dir = Path(self.utilities.shared_files_path) / "files"
        file_path = files_dir / filename

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        # Security check: ensure the file is within the files directory
        try:
            file_path.resolve().relative_to(files_dir.resolve())
        except ValueError as exc:
            raise HTTPException(
                status_code=403, detail="Access denied") from exc

        return FileResponse(path=str(file_path))

    async def health_check(self) -> Dict:
        """Check health of web app and agent service."""
        web_status = {"status": "healthy", "service": "web_interface"}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Create headers and inject trace context
                headers = {}
                inject(headers)  # Propagate the current span context
                response = await client.get(f"{AGENT_SERVICE_URL}/health", headers=headers)
                if response.status_code == 200:
                    agent_status = response.json()
                    return {
                        **web_status,
                        "agent_service": agent_status
                    }
                return {
                    **web_status,
                    "agent_service": {"status": "error", "code": response.status_code}
                }
        except Exception as e:
            return {
                **web_status,
                "agent_service": {"status": "error", "error": str(e)}
            }


# FastAPI app
app = FastAPI(title="Azure AI Agent Web Interface")
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()  # Instrument httpx client for tracing

# Initialize web app
web_app = WebApp(app)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8005))
    print(f"Starting web interface on port {port}...")
    print(f"Agent service URL: {AGENT_SERVICE_URL}")
    uvicorn.run(app, host="127.0.0.1", port=port)
