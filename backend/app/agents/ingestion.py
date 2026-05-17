"""Agen Ingestion — ekstrak PDF/Word ke JSON terstruktur."""
from claude_agent_sdk import ClaudeAgentOptions

from app.agents.base import build_agent_options
from app.tools.ingestion_tools import INGESTION_TOOLS


def build_ingestion_agent() -> ClaudeAgentOptions:
    return build_agent_options(
        prompt_name="ingestion",
        tools=INGESTION_TOOLS,
        server_name="ingestion",
        model="claude-haiku-4-5-20251001",
    )
