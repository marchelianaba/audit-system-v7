"""Helper untuk membangun agen Claude.

Pakai pola create_sdk_mcp_server + ClaudeAgentOptions dari claude-agent-sdk.
Setiap agen punya:
- system prompt yang di-load dari prompts/*.md
- daftar tools (in-process MCP server)
- allowlist tool yang sesuai peran
- model (haiku / sonnet)

DESIGN INVARIANT — agen TIDAK BOLEH memakai built-in tools (Bash/Edit/Write/
TodoWrite/Agent/Glob/Read). Hanya MCP tools yang kita ekspos lewat bridge.
Alasan: agen dalam konteks audit harus bekerja melalui pipeline V6 deterministic
dan bridge yang kita kontrol — bukan improvisasi shell/Edit ke file sistem.
"""
import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _find_claude_cli() -> str | None:
    """Cari claude CLI di instalasi resmi Windows (AppData/Roaming/Claude/claude-code/).

    SDK menyertakan bundled claude.exe tapi sering gagal dieksekusi di Windows
    (FileNotFoundError saat spawn). Prioritaskan instalasi resmi dari Claude Code
    desktop app yang sudah terbukti berjalan di mesin ini.
    """
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    claude_code_dir = Path(appdata) / "Claude" / "claude-code"
    if not claude_code_dir.exists():
        return None
    # Pilih versi terbaru yang punya claude.exe
    versions = sorted(
        [d for d in claude_code_dir.iterdir()
         if d.is_dir() and (d / "claude.exe").exists()],
        reverse=True,
    )
    return str(versions[0] / "claude.exe") if versions else None


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
        else [f"mcp__{server_name}__{t.name}" for t in tools]
    )

    # Pakai --system-prompt-file (path pendek) bukan --system-prompt (isi inline).
    # Windows membatasi command line CreateProcess di 32767 chars; prompt 34KB+
    # melampaui batas → WinError 206. SDK mendukung {"type": "file", "path": ...}
    # yang ditranslasi ke flag --system-prompt-file <path>.
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt tidak ditemukan: {prompt_path}")
    system_prompt: str | dict = {"type": "file", "path": str(prompt_path)}

    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        # tools=[] mematikan SEMUA built-in (Bash, Edit, Write, Read, Glob,
        # TodoWrite, Agent, Skill, dll). Agen hanya bisa pakai MCP tools di
        # bawah supaya tidak menyentuh V6 atau filesystem lain di luar bridge.
        tools=[],
        mcp_servers={server_name: server},
        allowed_tools=allowed,
        # Defensive: walaupun tools=[] sudah mati, kita explicit-deny
        # tool-tool yang biasa dipakai agen untuk improvisasi.
        disallowed_tools=["Bash", "Edit", "Write", "Read", "TodoWrite", "Glob", "Grep", "Agent", "Skill"],
        model=model,
        # acceptEdits hanya berlaku untuk MCP tools sekarang (built-in mati).
        permission_mode="acceptEdits",
        # Batas atas turn — agen berhenti alami saat selesai, bukan di sini.
        # Tanpa ini SDK memakai default rendah (~10) → tugas audit kompleks
        # terpotong di tengah sebelum KKP/temuan selesai.
        max_turns=200,
        # Pakai claude.exe dari instalasi resmi (bukan bundled SDK yang gagal di Windows).
        cli_path=_find_claude_cli(),
    )
