"""
Provides tools to communicate with MCP servers.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from azure.ai.agents.models import AsyncFunctionTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from terminal_colors import TerminalColors as tc


class MCPClient:
    """Client for communicating with MCP servers with optimized connection handling.

    Note: This class is not thread-safe. Use one instance per event loop or protect with locks if needed.
    """

    __slots__ = ("_client_context", "_read", "_session", "_write", "server_command", "server_params")

    def __init__(self, server_command: List[str]) -> None:
        """Initialize with the command to start the MCP server."""
        self.server_command = server_command
        self.server_params = StdioServerParameters(
            command=self.server_command[0],
            args=self.server_command[1:] if len(self.server_command) > 1 else [],
        )
        self._session: Optional[ClientSession] = None
        self._read: Any = None
        self._write: Any = None
        self._client_context: Any = None

    @classmethod
    def create_default(cls) -> "MCPClient":
        """Create an MCPClient with default server configuration.
        
        This creates a client that connects to the mcp_server.py script
        in the same directory as the mcp_client.py file.
        """
        script_dir = Path(__file__).resolve().parent
        server_script_path = script_dir / "mcp_server.py"
        server_command = [sys.executable, str(server_script_path), "--stdio"]
        return cls(server_command)

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Async context manager exit."""
        await self.close_session()

    async def _ensure_session(self) -> None:
        """Ensure we have an active session, creating one if necessary."""
        if self._session is None:
            try:
                self._client_context = stdio_client(self.server_params)
                self._read, self._write = await self._client_context.__aenter__()
                self._session = ClientSession(self._read, self._write)
                await self._session.__aenter__()
                await self._session.initialize()
            except Exception as e:
                logging.error(f"Failed to establish MCP session: {e}")
                await self.close_session()
                raise

    async def close_session(self) -> None:
        """Close the current session and cleanup resources."""
        exceptions = []

        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                exceptions.append(e)
                logging.warning(f"Error closing MCP session: {e}")
            finally:
                self._session = None

        if self._client_context is not None:
            try:
                await self._client_context.__aexit__(None, None, None)
            except Exception as e:
                exceptions.append(e)
                logging.warning(f"Error closing MCP client context: {e}")
            finally:
                self._client_context = None
                self._read = None
                self._write = None

        # If there were multiple exceptions, log them all
        if len(exceptions) > 1:
            logging.warning(f"Multiple cleanup errors occurred: {exceptions}")

    def _extract_content(self, result: Any) -> str:  # type: ignore[misc]
        """Extract text content from MCP result."""
        if not result.content or len(result.content) == 0:
            return "No result returned from tool"

        content_item = result.content[0]
        if hasattr(content_item, "text"):
            return content_item.text
        return str(content_item)

    async def call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server using the persistent session."""
        try:
            await self._ensure_session()
            assert self._session is not None, "Session should be established after _ensure_session"
            print(f"{tc.BRIGHT_BLUE}Calling tool: {tool_name} with arguments: {arguments}{tc.RESET}")
            result = await self._session.call_tool(tool_name, arguments)
            return self._extract_content(result)

        except Exception as e:
            await self.close_session()
            error_msg = f"Error calling tool {tool_name}: {e}"
            logging.error(error_msg)
            return error_msg

    async def fetch_tools_async(self) -> List[Dict[str, Any]]:
        """Fetch tool schemas from MCP server using the persistent session."""
        try:
            await self._ensure_session()
            assert self._session is not None, "Session should be established after _ensure_session"

            tools_result = await self._session.list_tools()

            # Use list comprehension for better performance
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
            logging.error(f"Error fetching tools from MCP server: {e}")
            await self.close_session()
            return []

    # Tool function factories for creating MCP tool wrappers
    def make_execute_sales_query(self, tool_name: str) -> Callable:
        """Factory for execute_sales_query tool function."""
        async def execute_sales_query_func(postgresql_query: str) -> str:
            try:
                return await self.call_tool_async(tool_name, {"postgresql_query": postgresql_query})
            except Exception as e:
                return f"Error executing {tool_name}: {e}"
        return execute_sales_query_func

    def make_get_multiple_table_schemas(self, tool_name: str) -> Callable:
        """Factory for get_multiple_table_schemas tool function."""
        async def get_multiple_table_schemas_func(table_names: List[str]) -> str:
            try:
                return await self.call_tool_async(tool_name, {"table_names": table_names})
            except Exception as e:
                return f"Error executing {tool_name}: {e}"
        return get_multiple_table_schemas_func

    def make_get_current_utc_date(self, tool_name: str) -> Callable:
        """Factory for get_current_utc_date tool function."""
        async def get_current_utc_date_func() -> str:
            try:
                return await self.call_tool_async(tool_name, {})
            except Exception as e:
                return f"Error executing {tool_name}: {e}"
        return get_current_utc_date_func

    def make_fallback(self, tool_name: str) -> Callable:
        """Factory for fallback tool function."""
        async def fallback_func() -> str:
            try:
                return await self.call_tool_async(tool_name, {})
            except Exception as e:
                return f"Error executing {tool_name}: {e}"
        return fallback_func

    def get_tool_factories(self) -> Dict[str, Callable]:
        """Get the tool factory mapping."""
        return {
            "execute_sales_query": self.make_execute_sales_query,
            "get_multiple_table_schemas": self.make_get_multiple_table_schemas,
            "get_current_utc_date": self.make_get_current_utc_date,
        }

    async def build_function_tools(self) -> AsyncFunctionTool:
        """Fetch tool schemas from MCP Server and build function tools."""
        print("🔧 Fetching tools from MCP server...")

        try:
            # Fetch tool schemas from MCP Server
            tools = await self.fetch_tools_async()

            if not tools:
                print("⚠️  No tools found from MCP server")
                return AsyncFunctionTool(set())

            print(f"✅ Found {len(tools)} tools from MCP server")

            # Build a function for each tool with proper metadata
            # Note: Azure AI Agent Service requires explicit parameter signatures, 
            # not **kwargs, so we need specific implementations for each tool
            def make_tool_func(tool_schema: dict) -> Callable:
                tool_name = tool_schema["function"]["name"]
                tool_description = tool_schema["function"]["description"]
                tool_params = tool_schema["function"]["parameters"]
                # print(tool_schema)
                
                # Create function with explicit parameters based on the tool schema
                tool_factories = self.get_tool_factories()
                factory = tool_factories.get(tool_name, self.make_fallback)
                tool_func = factory(tool_name)

                # Set function metadata for Azure AI Agent Service
                tool_func.__name__ = tool_name
                tool_func.__doc__ = tool_description

                # Note: Azure AI Agent Service will use __name__ and __doc__ for function discovery

                return tool_func

            # Create function set with proper schemas
            functions_set = {make_tool_func(tool) for tool in tools}

            tool_names = [tool["function"]["name"] for tool in tools]
            print(f"📋 Available MCP tools: {', '.join(tool_names)}")

            # Create a function tool from the functions set
            return AsyncFunctionTool(functions_set)

        except Exception as e:
            print(f"❌ Error fetching MCP tools: {e}")
            return AsyncFunctionTool(set())

    @classmethod
    def initialize_sync(cls) -> bool:
        """Synchronous wrapper for MCP initialization."""
        try:
            # Just test if we can create a simple client
            return True  # Simplified for now
        except Exception as e:
            logging.error(f"Error initializing MCP client: {e}")
            return False


if __name__ == "__main__":
    # Simple test using the class methods directly
    async def test() -> None:
        client = MCPClient.create_default()
        async with client:
            tools = await client.fetch_tools_async()
            print(f"Available tools: {[tool['function']['name'] for tool in tools]}")

            if tools:
                tool_name = tools[0]["function"]["name"]
                result = await client.call_tool_async(tool_name, {})
                print(f"Test result: {result}")

    asyncio.run(test())