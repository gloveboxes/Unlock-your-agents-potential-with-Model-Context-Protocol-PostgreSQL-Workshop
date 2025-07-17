import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for managing application settings."""

    # Agent configuration
    AGENT_NAME = "Zava DIY Sales Analysis Agent"

    # Azure configuration - loaded from environment variables
    MODEL_DEPLOYMENT_NAME: Optional[str] = os.getenv("MODEL_DEPLOYMENT_NAME")
    PROJECT_ENDPOINT: str = os.environ["PROJECT_ENDPOINT"]
    DEV_TUNNEL_URL: str = url + "/mcp/" if (url := os.getenv("DEV_TUNNEL_URL")) else ""
    RLS_USER_ID: str = os.getenv("RLS_USER_ID", "00000000-0000-0000-0000-000000000000")  # Default to Group Access ID

    # Model parameters
    MAX_COMPLETION_TOKENS = 20480
    MAX_PROMPT_TOKENS = 20480

    # The LLM is used to generate the SQL queries.
    # Set the temperature and top_p low to get more deterministic results.
    TEMPERATURE = 0.1
    TOP_P = 0.1

    # MCP configuration
    MAP_MCP_FUNCTIONS: bool = os.getenv("MAP_MCP_FUNCTIONS", "true").lower() in ("true", "1", "yes")

    @classmethod
    def validate_required_env_vars(cls) -> None:
        """Validate that all required environment variables are set."""
        required_vars = {
            "PROJECT_ENDPOINT": cls.PROJECT_ENDPOINT,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

        if not cls.MODEL_DEPLOYMENT_NAME:
            raise ValueError("MODEL_DEPLOYMENT_NAME environment variable is required")

    @classmethod
    def get_config_summary(cls) -> str:
        """Get a summary of the current configuration."""
        return f"""
Configuration Summary:
- Agent Name: {cls.AGENT_NAME}
- Model Deployment: {cls.MODEL_DEPLOYMENT_NAME or 'Not Set'}
- Temperature: {cls.TEMPERATURE}
- Top P: {cls.TOP_P}
- Max Completion Tokens: {cls.MAX_COMPLETION_TOKENS}
- Max Prompt Tokens: {cls.MAX_PROMPT_TOKENS}
"""
