"""Helper untuk membangun agen Claude.

Pakai pola create_sdk_mcp_server + ClaudeAgentOptions dari claude-agent-sdk.
Setiap agen punya:
- system prompt yang di-load dari prompts/*.md
- daftar tools (in-process MCP server)
- allowlist tool yang sesuai peran
- model (haiku / sonnet)
"""
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Baca system prompt dari file markdown."""
    p = PROMPTS_DIR / f"{name}.md"
    if not p.exists():
        raise FileNotFoundError(f"Prompt tidak ditemukan: {p}")
    return p.read_text(encoding="utf-8")


def build_agent_options(
    *,
    prompt_name: str,
    tools: list,
    server_name: str = "audit-v7",
    model: str = "claude-sonnet-4-6",
    allowed_tool_names: list[str] | None = None,
) -> ClaudeAgentOptions:
    """Konstruksi ClaudeAgentOptions yang konsisten untuk semua agen.

    Returns:
        ClaudeAgentOptions siap dipakai ClaudeSDKClient.
    """
    server = create_sdk_mcp_server(name=server_name, version="0.1.0", tools=tools)

    # allowed_tool_names: format claude-agent-sdk = "mcp__{server_name}__{tool_name}"
    allowed = (
        [f"mcp__{server_name}__{n}" for n in allowed_tool_names]
        if allowed_tool_names
        else [f"mcp__{server_name}__{t.__name__}" for t in tools]
    )

    return ClaudeAgentOptions(
        system_prompt=load_prompt(prompt_name),
        mcp_servers={server_name: server},
        allowed_tools=allowed,
        model=model,
        permission_mode="acceptEdits",
    )
