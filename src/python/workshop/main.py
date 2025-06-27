import asyncio
import logging

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent, AgentThread, AsyncFunctionTool, AsyncToolSet, CodeInterpreterTool
from azure.ai.projects.aio import AIProjectClient
from azure.core.exceptions import ClientAuthenticationError
from config import Config
from mcp_client import (
    cleanup_global_mcp_client,
    fetch_and_build_mcp_tools,
)
from stream_event_handler import StreamEventHandler
from terminal_colors import TerminalColors as tc
from utilities import Utilities

# Configure logging to suppress verbose Azure SDK logs
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Specifically suppress Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.ai.agents").setLevel(logging.WARNING)
logging.getLogger("azure.ai.projects").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

INSTRUCTIONS_FILE = None

toolset = AsyncToolSet()
utilities = Utilities()

# Move client creation inside main function after authentication validation
agents_client = None
project_client = None

functions = None  # Will be populated dynamically with MCP tools


INSTRUCTIONS_FILE = "instructions/function_calling.txt"
INSTRUCTIONS_FILE = "instructions/code_interpreter.txt"


async def add_agent_tools() -> None:
    """Add tools for the agent."""
    global functions

    # Fetch and build MCP tools dynamically
    functions = await fetch_and_build_mcp_tools()

    # Add the functions tool
    toolset.add(functions)

    # Add the code interpreter tool
    code_interpreter = CodeInterpreterTool()
    toolset.add(code_interpreter)


async def initialize() -> tuple[Agent | None, AgentThread | None]:
    """Initialize the agent with the MCP tools and instructions."""

    if not INSTRUCTIONS_FILE:
        return None, None

    if not agents_client:
        raise RuntimeError("Agents client not initialized")

    await add_agent_tools()

    try:
        instructions = utilities.load_instructions(INSTRUCTIONS_FILE)

        if not Config.API_DEPLOYMENT_NAME:
            raise ValueError("MODEL_DEPLOYMENT_NAME environment variable is required")

        print("Creating agent...")
        agent = await agents_client.create_agent(
            model=Config.API_DEPLOYMENT_NAME,
            name=Config.AGENT_NAME,
            instructions=instructions,
            toolset=toolset,
            temperature=Config.TEMPERATURE,
        )
        print(f"Created agent, ID: {agent.id}")

        agents_client.enable_auto_function_calls(tools=toolset)
        print("Enabled auto function calls.")

        print("Creating thread...")
        thread = await agents_client.threads.create()
        print(f"Created thread, ID: {thread.id}")

        return agent, thread

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        return None, None


async def cleanup(agent: Agent | None, thread: AgentThread | None, agents_client_instance=None) -> None:
    """Cleanup the Azure AI resources."""
    await cleanup_global_mcp_client()
    if agent and thread and agents_client_instance:
        try:
            existing_files = await agents_client_instance.files.list()
            for f in existing_files.data:
                await agents_client_instance.files.delete(f.id)
            await agents_client_instance.threads.delete(thread.id)
            await agents_client_instance.delete_agent(agent.id)
        except Exception as e:
            print(f"⚠️  Warning: Error during Azure cleanup: {e}")


async def post_message(thread_id: str, content: str, agent: Agent, thread: AgentThread, agents_client_instance) -> None:
    """Post a message to the Foundry Agent Service."""
    try:
        await agents_client_instance.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )

        async with await agents_client_instance.runs.stream(
            thread_id=thread.id,
            agent_id=agent.id,
            event_handler=StreamEventHandler(
                functions=functions if functions else AsyncFunctionTool(set()),
                project_client=(
                    project_client
                    if project_client is not None
                    else AIProjectClient(
                        credential=utilities.get_credential(),
                        endpoint=Config.PROJECT_ENDPOINT,
                    )
                ),
                agents_client=agents_client_instance,
                utilities=utilities,
            ),
            max_completion_tokens=Config.MAX_COMPLETION_TOKENS,
            max_prompt_tokens=Config.MAX_PROMPT_TOKENS,
            temperature=Config.TEMPERATURE,
            top_p=Config.TOP_P,
            instructions=agent.instructions,
        ) as stream:
            await stream.until_done()

    except Exception as e:
        utilities.log_msg_purple(f"An error occurred posting the message: {e!s}")


async def main() -> None:
    """
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
    """
    global agents_client, project_client
    agent = None
    thread = None

    try:
        # Validate configuration first
        Config.validate_required_env_vars()

        # Validate Azure authentication
        print("🔐 Validating Azure authentication...")
        credential = await utilities.validate_azure_authentication()
        print("✅ Azure authentication successful!")

        # Create clients after authentication is validated
        agents_client = AgentsClient(
            credential=credential,
            endpoint=Config.PROJECT_ENDPOINT,
        )

        project_client = AIProjectClient(
            credential=credential,
            endpoint=Config.PROJECT_ENDPOINT,
        )

        async with agents_client, project_client:
            agent, thread = await initialize()
            if not agent or not thread:
                print(
                    f"{tc.BG_BRIGHT_RED}Initialization failed. Ensure you have uncommented the instructions file for the lab.{tc.RESET}"
                )
                print("Exiting...")
                return

            cmd = None

            while True:
                prompt = input(f"\n\n{tc.GREEN}Enter your query (type exit or save to finish): {tc.RESET}").strip()
                if not prompt:
                    continue

                cmd = prompt.lower()
                if cmd in {"exit", "save"}:
                    break

                await post_message(
                    agent=agent,
                    thread_id=thread.id,
                    content=prompt,
                    thread=thread,
                    agents_client_instance=agents_client,
                )

            if cmd == "save":
                print(
                    "The agent has not been deleted, so you can continue experimenting with it in the Azure AI Foundry."
                )
                print(
                    f"Navigate to https://ai.azure.com, select your project, then playgrounds, agents playgound, then select agent id: {agent.id}"
                )
            else:
                await cleanup(agent, thread, agents_client)
                print("The agent resources have been cleaned up.")

    except ClientAuthenticationError:
        # Authentication error already handled in utilities.validate_azure_authentication
        return
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        if agent and thread:
            await cleanup(agent, thread, agents_client)
    except Exception as e:
        print(f"❌ Error in main: {e}")
        if agent and thread:
            await cleanup(agent, thread)


if __name__ == "__main__":
    print("Starting async program...")
    asyncio.run(main())
    print("Program finished.")
