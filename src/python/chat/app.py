"""
Simple Azure OpenAI Chat Server
FastAPI backend with Server-Sent Events for streaming
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List

import openai
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Load environment variables
load_dotenv()

app = FastAPI(title="Azure OpenAI Chat")

# Mount static files
static_dir = Path(__file__).parent.parent.parent / "shared" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Configure Azure OpenAI client
def get_azure_openai_client():
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    credential = DefaultAzureCredential()

    return openai.AzureOpenAI(
        azure_ad_token_provider=lambda: credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token,
        azure_endpoint=endpoint,
        api_version="2024-12-01-preview",
    )


client = get_azure_openai_client()
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# Store chat sessions (in production, use a database)
chat_sessions: Dict[str, List[Dict]] = {}


@app.get("/", response_class=HTMLResponse)
async def get_chat_page():
    """Serve the chat HTML page"""
    html_file = Path(__file__).parent.parent.parent / "shared" / "static" / "index.html"
    with html_file.open("r") as f:
        return HTMLResponse(content=f.read())


@app.post("/upload")
async def upload_file(file: UploadFile, message: str = Form(None)):
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
async def stream_chat(message: str = ""):
    """Stream chat responses using Server-Sent Events"""
    if not message.strip():
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'Empty message'})}\n\n"]),
            media_type="text/event-stream",
        )

    # Get or create session (simplified - using a single session)
    session_id = "default"
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []

    # Add user message to session
    chat_sessions[session_id].append({"role": "user", "content": message})

    async def generate():
        try:
            # Create streaming response
            stream = client.chat.completions.create(
                model=deployment,
                messages=chat_sessions[session_id],
                stream=True,
                temperature=0.7,
                max_tokens=1000,
            )

            assistant_message = ""

            # Process stream
            for chunk in stream:
                if (
                    chunk.choices
                    and len(chunk.choices) > 0
                    and chunk.choices[0].delta.content
                ):
                    delta = chunk.choices[0].delta.content
                    assistant_message += delta

                    # Send chunk as Server-Sent Event
                    yield f"data: {json.dumps({'content': delta})}\n\n"

                    # Small delay to make streaming visible
                    await asyncio.sleep(0.01)

            # Add assistant message to session
            chat_sessions[session_id].append(
                {"role": "assistant", "content": assistant_message}
            )

            # Send completion signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8003)
