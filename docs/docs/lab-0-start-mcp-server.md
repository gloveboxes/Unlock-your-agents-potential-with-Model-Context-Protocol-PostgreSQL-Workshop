# Lab 0: Start MCP Server

## What You'll Learn

In this lab, you will:

- Understand how to start and configure the MCP server
- Learn about the MCP server's role in handling communication between LLMs and external tools
- Set up the foundation for the Model Context Protocol implementation

## Introduction

The Model Context Protocol (MCP) server is a crucial component that handles the communication between Large Language Models (LLMs) and external tools and data sources. Before you can interact with the agent and use MCP tools, you need to start this server.

## Interface options for MCP

MCP supports two main interfaces for connecting LLMs with tools:

- **HTTP API**: For web-based APIs and services.
- **Stdio**: For local scripts and command-line tools.

This lab uses the HTTP API interface to integrate with the Azure AI Foundry Agent Service.

### Starting the MCP Server

Normally, you'd deploy the MCP server in a production environment, but for this workshop, you'll run it locally in your development environment. This allows you to test and interact with the MCP tools without needing a full deployment.

=== "Python"

    #### Start the MCP Server

      To begin, you need to start the MCP server, which will handle the communication between the LLM and the external tools. 
      
      1. Open a terminal in VS Code
      2. From the terminal run the following commands to start the MCP server:

         ```bash
         cd /workspace/src/python/mcp
         python mcp_server.py
         ```

         This command starts the MCP server, which listens for incoming requests from the LLM and routes them to the appropriate tools.

        !!! tip "Keep the server running"
            Keep this terminal window open and the server running throughout the workshop. The server needs to be active for the agent to access external tools and data sources.


    ### Start up a DevTunnel for the MCP Server

    The MCP Server runs on localhost port 8010, but the Agent Service needs internet access to it. We'll use a DevTunnel to expose the MCP Server that is running locally to the internet.

    1. In a new terminal, authenticate DevTunnel if you haven't already:

        ```bash
        devtunnel login
        ```
     
    1. Next, in the terminal where the MCP server is running, start a DevTunnel by running:

        ```bash
        devtunnel create --port 8010 --allow-anonymous
        ```

        This will output a URL that you'll need for the agent to connect to the MCP server. The output will be similar to:

        ```text
        Hosting port: 8010
        Connect via browser: https://<tunnel-id>-8010.aue.devtunnels.ms
        Inspect network activity: https://<tunnel-id>-8010-inspect.aue.devtunnels.ms
        ```

    2. Copy the **Connect via browser** URL to the clipboard - you'll need it in the next lab to configure the agent.

=== "C#"

      TBD

## Next Steps

Once the MCP server is running, you can proceed to Lab 1 where you'll configure the agent to use MCP tools and start interacting with the system.
