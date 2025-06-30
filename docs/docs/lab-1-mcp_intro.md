## Introduction

The Model Context Protocol (MCP) is an emerging standard designed to connect Large Language Models (LLMs) with external tools and data sources in a consistent, scalable way. MCP acts as a universal interface, allowing LLMs to interact seamlessly with resources like databases, APIs, and time/date services—enabling smarter, more extensible AI applications.

In this lab, you’ll use MCP to bridge an LLM with both a PostgreSQL database and a date/time source. MCP is rapidly becoming the standard for tool integration across platforms like Agents Service, Copilot, and many other AI ecosystems. By adopting MCP, you gain a future-proof, plug-and-play architecture for building powerful, interoperable AI solutions.

### Interface options for MCP
MCP provides a flexible interface for connecting LLMs with external tools and data sources. Here are the key options:

- **HTTP API**: The most common interface, allowing LLMs to make HTTP requests to external services. This is ideal for web-based APIs and services and allows for streaming and batch processing responses from tools.
- **Stdio**: A simple interface that allows LLMs to communicate with external tools via standard input/output streams. This is useful for local scripts and command-line tools.

In this lab, you will use the HTTP API interface to connect the LLM with a PostgreSQL database and a date/time service. We'll be running the MCP server locally, which will handle the communication between the LLM and the external tools. But in production, you would deploy the MCP Server to Azure using Azure Container Apps or Azure Functions, allowing you to secure, scale and manage the service effectively.

## Lab Exercise

=== "Python"

    ### Start the MCP Server

      To begin, you need to start the MCP server, which will handle the communication between the LLM and the external tools. 
      
      1. Open a terminal in VS Code
      2. From the terminal run the following commands to start the MCP server:

         ```bash
         cd /workspace/src/python/mcp
         python mcp_server.py
         ```

         This command starts the MCP server, which listens for incoming requests from the LLM and routes them to the appropriate tools.

    ### Start the Agent

      1. Open the `main.py` and enable the agent tools by uncommenting the following lines:

         Uncomment the following lines by removing the "# " characters

         ```python
         # INSTRUCTIONS_FILE = "instructions/enable_mcp_server_calling.txt"

         # toolset.add(functions)
         ```

        !!! warning "Ensure you remove the space after the `#` character"
            The lines to be uncommented are not adjacent. When removing the `#` character, ensure you also delete the space that follows it.

      1. Review the code in the `main.py` file.

         After uncommenting, your code should look like this:

         ```python
         INSTRUCTIONS_FILE = "instructions/code_interpreter.txt"

         async def add_agent_tools() -> None:
               """Add tools for the agent."""
               global functions

               # Fetch and build MCP tools dynamically
               functions = await fetch_and_build_mcp_tools()

               # Add the functions tool
               toolset.add(functions)
         ```

=== "C#"

      TBD

1. **Start the Agent**:

   Press `F5` to run the agent in your development environment. This will initialize the agent and connect it to the MCP server.

2. **Interact with the Agent**:
   The agent supports rich streaming conversations with real-time responses:

   ```
   🤖 Zava Sales Analysis Agent Ready!
   Connected to Azure AI Foundry
   Available tools: PostgreSQL schema tools + sales query execution
   =========================================================================

   You: What were our top-selling product categories last quarter?

   Agent: Let me analyze your sales data...
   [Real-time streaming response with formatted tables and insights]
   ```

3. **Example Queries to Try**:
   - **Sales Performance**: "Show me revenue by product category for 2024 as a bar chart"
   - **Regional Analysis**: "Which stores performed best last quarter?"
   - **Customer Insights**: "Who are our top 10 customers by order value?"
   - **Product Search**: "Find products similar to camping equipment"
   - **Trend Analysis**: "Show me seasonal sales patterns"
   - **Inventory Reports**: "What's our current stock level by store?"

4. **Advanced Features**:
   - **Multi-language**: Ask questions in different languages for localized responses
   - **Data Export**: Request data in CSV format (presented as markdown tables)
   - **Complex Queries**: The agent can join multiple tables and perform sophisticated analysis