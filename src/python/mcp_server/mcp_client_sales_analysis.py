"""Provides tools to communicate with MCP servers."""

import asyncio
import logging
import sys
from pathlib import Path

# Add the mcp_server directory to the path
sys.path.append(str(Path(__file__).parent.parent / "shared"))

from typing import Any, Callable, Dict, List, Optional

from azure.ai.agents.models import AsyncFunctionTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from otlp import configure_oltp_grpc_tracing
from terminal_colors import TerminalColors as tc

tracer = configure_oltp_grpc_tracing()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(self, server_command: List[str]) -> None:
        """Initialize with the command to start the MCP server."""
        self.server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:] if len(server_command) > 1 else [],
        )
        self._session: Optional[ClientSession] = None
        self._client_context = None

    @classmethod
    def create_default(cls) -> "MCPClient":
        """Create an MCPClient with default server configuration."""
        script_dir = Path(__file__).resolve().parent
        server_script_path = script_dir / "mcp_server_sales_analysis.py"
        return cls([sys.executable, str(server_script_path), "--stdio"])

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_session()

    async def _ensure_session(self) -> None:
        """Ensure we have an active session, creating one if necessary."""
        if self._session is None:
            try:
                self._client_context = stdio_client(self.server_params)
                read, write = await self._client_context.__aenter__()
                self._session = ClientSession(read, write)
                await self._session.__aenter__()
                await self._session.initialize()
            except Exception as e:
                logging.error(f"Failed to establish MCP session: {e}")
                await self.close_session()
                raise

    async def close_session(self) -> None:
        """Close the current session and cleanup resources."""
        for context, name in [(self._session, "session"), (self._client_context, "client_context")]:
            if context is not None:
                try:
                    await context.__aexit__(None, None, None)
                except Exception as e:
                    logging.warning(f"Error closing MCP {name}: {e}")

        self._session = None
        self._client_context = None

    def _extract_content(self, result) -> str:
        """Extract text content from MCP result."""
        if not result.content:
            return "No result returned from tool"

        content_item = result.content[0]
        return content_item.text if hasattr(content_item, "text") else str(content_item)

    def _build_enhanced_docstring(self, tool_description: str, tool_parameters: Dict[str, Any]) -> str:
        """Build enhanced docstring with parameter info from MCP schema."""
        enhanced_doc = tool_description
        if tool_parameters and "properties" in tool_parameters:
            enhanced_doc += "\n\nParameters:"
            for param_name, param_info in tool_parameters["properties"].items():
                param_desc = param_info.get("description", "No description")
                enhanced_doc += f"\n:param {param_name}: {param_desc}"
        return enhanced_doc

    async def call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server using the persistent session."""
        try:
            await self._ensure_session()
            assert self._session is not None
            logger.info("Calling tool: %s with arguments: %s", tool_name, arguments)
            result = await self._session.call_tool(tool_name, arguments)
            return self._extract_content(result)
        except Exception as e:
            await self.close_session()
            logger.error("Error calling tool %s: %s", tool_name, e)
            error_msg = f"Error calling tool {tool_name}: {e}"
            logging.error(error_msg)
            return error_msg

    async def fetch_tools_async(self) -> List[Dict[str, Any]]:
        """Fetch tool schemas from MCP server using the persistent session."""
        try:
            await self._ensure_session()
            assert self._session is not None
            tools_result = await self._session.list_tools()
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in tools_result.tools
            ]
        except Exception as e:
            logger.error("Error fetching tools from MCP server: %s", e)
            await self.close_session()
            return []

    async def build_function_tools(self) -> AsyncFunctionTool:
        """Fetch tool schemas from MCP Server and build function tools."""
        logger.info("🔧 Fetching tools from MCP server...")

        tools = await self.fetch_tools_async()
        if not tools:
            logger.warning("⚠️  No tools found from MCP server")
            return AsyncFunctionTool(set())

        logger.info("✅ Found %d tools from MCP server", len(tools))

        # Create specific tool functions with proper parameter signatures
        functions_set = set()
        for tool in tools:
            function_info = tool["function"]
            tool_name = function_info["name"]
            tool_description = function_info["description"]
            tool_parameters = function_info.get("parameters", {})

            # Create specific functions based on tool name to maintain correct signatures
            if tool_name == "execute_sales_query":

                async def execute_sales_query(postgresql_query: str) -> str:
                    return await self.call_tool_async("execute_sales_query", {"postgresql_query": postgresql_query})

                execute_sales_query.__name__ = tool_name
                execute_sales_query.__doc__ = self._build_enhanced_docstring(tool_description, tool_parameters)
                functions_set.add(execute_sales_query)

            elif tool_name == "get_multiple_table_schemas":

                async def get_multiple_table_schemas(table_names: List[str]) -> str:
                    return await self.call_tool_async("get_multiple_table_schemas", {"table_names": table_names})

                get_multiple_table_schemas.__name__ = tool_name
                get_multiple_table_schemas.__doc__ = self._build_enhanced_docstring(tool_description, tool_parameters)
                functions_set.add(get_multiple_table_schemas)

            elif tool_name == "get_current_utc_date":

                async def get_current_utc_date() -> str:
                    return await self.call_tool_async("get_current_utc_date", {})

                get_current_utc_date.__name__ = tool_name
                get_current_utc_date.__doc__ = self._build_enhanced_docstring(tool_description, tool_parameters)
                functions_set.add(get_current_utc_date)

            else:
                # Fallback for any other tools - use closure to capture tool_name
                def make_generic_tool(captured_tool_name: str) -> Callable:
                    async def generic_tool(**kwargs: dict) -> str:  # type: ignore
                        return await self.call_tool_async(captured_tool_name, kwargs)

                    return generic_tool

                generic_func = make_generic_tool(tool_name)
                generic_func.__name__ = tool_name
                generic_func.__doc__ = self._build_enhanced_docstring(tool_description, tool_parameters)
                functions_set.add(generic_func)

        tool_names = [tool["function"]["name"] for tool in tools]
        logger.info("📋 Available MCP tools: %s", ', '.join(tool_names))

        return AsyncFunctionTool(functions_set)


if __name__ == "__main__":

    async def test() -> None:
        client = MCPClient.create_default()
        async with client:
            tools = await client.fetch_tools_async()
            logger.info("Available tools: %s", [tool['function']['name'] for tool in tools])

            if tools:
                tool_name = tools[0]["function"]["name"]
                result = await client.call_tool_async(tool_name, {})
                logger.info("Test result: %s", result)

    asyncio.run(test())
