"""Agen Anggota Tim — analisis + susun KKP."""
from claude_agent_sdk import ClaudeAgentOptions

from app.agents.base import build_agent_options
from app.tools.kkp_tools import KKP_TOOLS
from app.tools.pipeline_tools import PIPELINE_TOOLS


def build_anggota_tim_agent() -> ClaudeAgentOptions:
    return build_agent_options(
        prompt_name="anggota_tim",
        tools=PIPELINE_TOOLS + KKP_TOOLS,
        server_name="at",
        model="claude-sonnet-4-6",
    )
