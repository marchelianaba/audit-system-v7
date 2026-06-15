"""Bridge utility untuk memanggil script V6.

V6 scripts ada di /v6/scripts/{skill}/ (di-mount atau di-bake ke Docker image).
Kita panggil sebagai subprocess Python supaya environment-nya bersih dan
script V6 tidak perlu diubah sama sekali.
"""
import asyncio
import json
import logging
import subprocess
import sys
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

    Memakai asyncio.to_thread + subprocess.run (bukan create_subprocess_exec)
    agar kompatibel dengan Windows di mana SelectorEventLoop tidak support
    create_subprocess_exec (terutama saat uvicorn --reload aktif).

    PENTING: pakai `sys.executable` (interpreter yang menjalankan uvicorn,
    biasanya `.venv/bin/python`) supaya subprocess MEWARISI semua package
    dari venv backend (pdfplumber, python-docx, openpyxl, dll). Pakai
    "python3" string literal akan resolve ke `/usr/bin/python3` (Python
    sistem) yang TIDAK punya paket-paket ini → V6 gagal dgn "pdfplumber
    tidak terinstall" meskipun venv sudah lengkap.

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

    cmd = [sys.executable, str(script_path), *args]
    log.info("Run V6: %s", " ".join(str(c) for c in cmd))

    def _run_sync() -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                cwd=str(settings.v6_path),
                timeout=timeout,
            )
            return (
                result.returncode,
                result.stdout.decode("utf-8", errors="replace"),
                result.stderr.decode("utf-8", errors="replace"),
            )
        except subprocess.TimeoutExpired:
            return (124, "", f"Timeout setelah {timeout} detik")
        except Exception as exc:
            return (1, "", str(exc))

    return await asyncio.to_thread(_run_sync)


def qc_summary_counts(checklist: dict | list) -> tuple[int, int, int, int]:
    """Ambil (kritis, peringatan, needs_review, ok) dari output qc_saipi.py.

    qc_saipi.py menulis envelope {stage, summary, checklist[...]}. Sumber
    kebenaran adalah `summary` (sudah dihitung script + cocok dengan laporan
    markdown). Bila `summary` tidak ada (file lama), hitung dari array
    `checklist`. CATATAN: array-nya berkunci `checklist`, BUKAN `items` —
    bug lama membaca `items` sehingga selalu 0 → status PASS palsu.
    """
    if not isinstance(checklist, dict):
        return (0, 0, 0, 0)
    summary = checklist.get("summary")
    if isinstance(summary, dict):
        return (
            int(summary.get("kritis", 0)),
            int(summary.get("peringatan", 0)),
            int(summary.get("needs_review", 0)),
            int(summary.get("ok", 0)),
        )
    items = checklist.get("checklist", []) or []
    kritis = sum(1 for i in items if i.get("severity") == "KRITIS" and i.get("status") == "GAP")
    peringatan = sum(1 for i in items if i.get("severity") == "PERINGATAN" and i.get("status") == "GAP")
    needs_review = sum(1 for i in items if i.get("severity") == "NEEDS_REVIEW")
    ok = sum(1 for i in items if i.get("status") == "OK")
    return (kritis, peringatan, needs_review, ok)


def safe_read_json(path: Path) -> dict | list:
    """Baca JSON; return {} bila tidak ada / error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("JSON decode error %s: %s", path, e)
        return {}
