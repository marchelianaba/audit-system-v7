"""Agen QC SAIPI — gate kepatuhan SAIPI."""
from claude_agent_sdk import ClaudeAgentOptions

from app.agents.base import build_agent_options
from app.tools.qc_tools import QC_TOOLS


def build_qc_saipi_agent() -> ClaudeAgentOptions:
    return build_agent_options(
        prompt_name="qc_saipi",
        tools=QC_TOOLS,
        server_name="qc",
        model="claude-haiku-4-5-20251001",
    )
