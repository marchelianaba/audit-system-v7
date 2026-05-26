"""Agen Anggota Tim — analisis + susun KKP."""
from claude_agent_sdk import ClaudeAgentOptions

from app.agents.base import build_agent_options
from app.tools.bukti_tools import BUKTI_TOOLS
from app.tools.feedback_tools import FEEDBACK_TOOLS
from app.tools.gate_tools import GATE_TOOLS
from app.tools.kkp_tools import KKP_TOOLS
from app.tools.lke_tools import LKE_TOOLS
from app.tools.pipeline_tools import PIPELINE_TOOLS
from app.tools.skill_tools import SKILL_TOOLS
from app.tools.wiki_tools import WIKI_TOOLS


def build_anggota_tim_agent() -> ClaudeAgentOptions:
    return build_agent_options(
        prompt_name="anggota_tim",
        tools=(PIPELINE_TOOLS + KKP_TOOLS + WIKI_TOOLS + SKILL_TOOLS + GATE_TOOLS
               + LKE_TOOLS + BUKTI_TOOLS + FEEDBACK_TOOLS),
        server_name="at",
        model="claude-sonnet-4-6",
    )
