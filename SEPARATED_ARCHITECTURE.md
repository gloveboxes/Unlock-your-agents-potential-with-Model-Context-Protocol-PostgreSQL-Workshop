# Separated Services Architecture

This project has been refactored to separate the web interface from the agent service, providing better modularity and scalability.

## Architecture Overview

```
┌─────────────────┐    HTTP/REST API    ┌─────────────────┐    HTTP/Dev Tunnel    ┌─────────────────┐
│   Web App       │ ──────────────────► │  Agent Service  │ ────────────────────► │   MCP Server    │
│ src/python/     │                     │ src/python/     │                       │  src/python/    │
│ web_app/        │                     │ workshop/       │                       │  mcp_server/    │
│ (port 8005)     │                     │ (port 8006)     │                       │  (port 8010)    │
│                 │                     │                 │                       │                 │
│ - User Interface│                     │ - Azure AI      │                       │ - PostgreSQL    │
│ - File Upload   │                     │   Agent         │                       │   Integration   │
│ - Static Assets │                     │ - Chat Logic    │                       │ - Database      │
│ - Proxy to      │                     │ - Streaming     │                       │   Queries       │
│   Agent Service │                     │ - Telemetry     │                       │ - Tools         │
└─────────────────┘                     └─────────────────┘                       └─────────────────┘
```

## Components

### 1. Web App (`src/python/web_app/web_app.py`)

- **Port**: 8005
- **Purpose**: User interface and file handling
- **Features**:
  - Serves HTML, CSS, JS static files
  - Handles file uploads
  - Proxies chat requests to Agent Service
  - Converts agent service responses to web-compatible format
  - **Imports shared modules from workshop folder** (config, utilities)

### 2. Agent Service (`src/python/workshop/agent_service.py`)

- **Port**: 8006
- **Purpose**: AI agent logic and Azure integration
- **Features**:
  - Azure AI Agents client
  - MCP server integration via dev tunnel
  - Streaming chat responses
  - Telemetry and monitoring
  - File serving from agent-generated content
  - **Shared modules** (config, utilities, stream_event_handler)

### 3. MCP Server (`src/python/mcp/mcp_server.py`)

- **Port**: 8010
- **Purpose**: PostgreSQL database integration
- **Features**:
  - Database query tools
  - Schema information
  - Data visualization helpers

## Running the Services

### Option 1: Using VS Code Debug (Recommended)
1. Press `F5` in VS Code
2. Select "Debug: MCP Server + Agent Service + Web App"
3. All three services will start automatically

### Option 2: Manual Start
Start each service in separate terminals:

```bash
# Terminal 1 - MCP Server
cd src/python/mcp
python mcp_server.py

# Terminal 2 - Agent Service  
cd src/python/workshop
python agent_service.py

# Terminal 3 - Web App
cd src/python/web_app
python web_app.py
```

### Option 3: VS Code Tasks
Use the VS Code task runner:
1. `Ctrl+Shift+P` → "Tasks: Run Task"
2. Select the desired task:
   - "Run MCP Server"
   - "Run Agent Service" 
   - "Run Web App"

## Testing the Setup

Run the test script to verify all services are running:

```bash
./test_services.sh
```

## URLs

- **Web Interface**: http://127.0.0.1:8005
- **Agent Service Health**: http://127.0.0.1:8006/health
- **Web App Health**: http://127.0.0.1:8005/health

## Benefits of This Architecture

1. **Separation of Concerns**: Web UI and agent logic are decoupled
2. **Scalability**: Can scale web and agent services independently
3. **Development**: Easier to work on frontend and backend separately
4. **Deployment**: Can deploy services to different containers/servers
5. **Testing**: Can test agent service independently via REST API
6. **Monitoring**: Separate health checks and metrics for each service
7. **Code Reuse**: Web app imports shared modules from workshop (no duplication)
8. **Maintainability**: Single source of truth for configuration and utilities

## Legacy Support

The original monolithic `app.py` is still available for backward compatibility. Use the "Debug: MCP Server + Workshop App (Legacy)" configuration to run it.

## API Documentation

### Agent Service Endpoints

- `GET /health` - Health check
- `POST /chat/stream` - Stream chat responses
- `GET /files/{filename}` - Serve generated files

### Web App Endpoints

- `GET /` - Main chat interface
- `POST /upload` - File upload
- `GET /chat/stream` - Proxied chat streaming
- `GET /files/{filename}` - Proxied file serving
- `GET /health` - Health check including agent service status
