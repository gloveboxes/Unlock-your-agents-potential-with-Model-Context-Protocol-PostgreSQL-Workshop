"""
Provides tools to communicate with MCP servers.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from azure.ai.agents.models import AsyncFunctionTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    """Client for communicating with MCP servers with optimized connection handling.

    Note: This class is not thread-safe. Use one instance per event loop or protect with locks if needed.
    """

    __slots__ = ("_client_context", "_read", "_session", "_write", "server_command", "server_params")

    def __init__(self, server_command: List[str]):
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

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_session()

    async def _ensure_session(self):
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

    async def close_session(self):
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

    def _extract_content(self, result) -> str:
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


# Global MCP client instance for reuse
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        server_script_path = os.path.join(script_dir, "mcp_server.py")
        server_command = [sys.executable, server_script_path]
        _mcp_client = MCPClient(server_command)
    return _mcp_client


async def cleanup_global_mcp_client():
    """Cleanup the global MCP client instance."""
    global _mcp_client
    if _mcp_client is not None:
        try:
            await _mcp_client.close_session()
        except Exception as e:
            logging.warning(f"Error during MCP client cleanup: {e}")
        finally:
            _mcp_client = None


# Utility functions for integration
async def call_mcp_tool_async(tool_name: str, **kwargs) -> str:
    """Call an MCP tool with the given arguments."""
    client = get_mcp_client()
    return await client.call_tool_async(tool_name, kwargs)


async def fetch_mcp_tools_async() -> List[Dict[str, Any]]:
    """Fetch tool schemas from MCP server in OpenAI function format."""
    client = get_mcp_client()
    return await client.fetch_tools_async()


async def fetch_and_build_mcp_tools() -> AsyncFunctionTool:
    """Fetch tool schemas from MCP Server and build function tools."""
    print("🔧 Fetching tools from MCP server...")

    try:
        # Fetch tool schemas from MCP Server
        tools = await fetch_mcp_tools_async()

        if not tools:
            print("⚠️  No tools found from MCP server")
            return AsyncFunctionTool(set())

        print(f"✅ Found {len(tools)} tools from MCP server")

        # Build a function for each tool with proper metadata
        def make_tool_func(tool_schema: dict):
            tool_name = tool_schema["function"]["name"]
            tool_description = tool_schema["function"]["description"]

            # Create function with explicit parameter signature for tools that need it
            if tool_name == "execute_sales_query":

                async def execute_sales_query_func(postgresql_query: str):
                    try:
                        result = await call_mcp_tool_async(tool_name, postgresql_query=postgresql_query)
                        return result
                    except Exception as e:
                        return f"Error executing {tool_name}: {e}"

                tool_func = execute_sales_query_func
            else:
                # For tools without parameters, use **kwargs
                async def generic_tool_func(**kwargs):
                    try:
                        result = await call_mcp_tool_async(tool_name, **kwargs)
                        return result
                    except Exception as e:
                        return f"Error executing {tool_name}: {e}"

                tool_func = generic_tool_func

            # Set function metadata for Azure AI Agent Service
            tool_func.__name__ = tool_name
            tool_func.__doc__ = tool_description

            # Note: Azure AI Agent Service will use __name__ and __doc__ for function discovery

            return tool_func

        # Create function set with proper schemas
        functions_set = {make_tool_func(tool) for tool in tools}

        tool_names = [tool["function"]["name"] for tool in tools]
        print(f"📋 Available MCP tools: {', '.join(tool_names)}")

        return AsyncFunctionTool(functions_set)

    except Exception as e:
        print(f"❌ Error fetching MCP tools: {e}")
        return AsyncFunctionTool(set())


# Synchronous wrapper functions for use in the main app
def initialize_mcp_sync() -> bool:
    """Synchronous wrapper for MCP initialization."""
    try:
        # Just test if we can create a simple client
        return True  # Simplified for now
    except Exception as e:
        logging.error(f"Error initializing MCP client: {e}")
        return False


if __name__ == "__main__":
    # Simple test
    async def test():
        tools = await fetch_mcp_tools_async()
        print(f"Available tools: {[tool['function']['name'] for tool in tools]}")

        if tools:
            tool_name = tools[0]["function"]["name"]
            result = await call_mcp_tool_async(tool_name)
            print(f"Test result: {result}")

    asyncio.run(test())
