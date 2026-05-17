"""Bridge utility untuk memanggil script V6.

V6 scripts ada di /v6/scripts/{skill}/ (di-mount atau di-bake ke Docker image).
Kita panggil sebagai subprocess Python supaya environment-nya bersih dan
script V6 tidak perlu diubah sama sekali.
"""
import asyncio
import json
import logging
from pathlib import Path

from app.config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


async def run_v6_script(
    script_relative_path: str,
    args: list[str],
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Jalankan script V6 sebagai subprocess Python async.

    Args:
        script_relative_path: relatif terhadap `/v6`, mis. "scripts/reviu-rka-kl/run_batch.py"
        args: argumen tambahan ke script
        timeout: detik

    Returns:
        (exit_code, stdout, stderr)
    """
    script_path = settings.v6_path / script_relative_path
    if not script_path.exists():
        return (127, "", f"Script V6 tidak ditemukan: {script_path}")

    cmd = ["python3", str(script_path), *args]
    log.info("Run V6: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(settings.v6_path),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return (124, "", f"Timeout setelah {timeout} detik")

    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def safe_read_json(path: Path) -> dict | list:
    """Baca JSON; return {} bila tidak ada / error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("JSON decode error %s: %s", path, e)
        return {}
