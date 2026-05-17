"""Storage helpers: folder layout per penugasan, hash, baca/tulis file."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import aiofiles

from app.config import get_settings

settings = get_settings()

# Subfolder standar per penugasan (mengikuti V6)
PENUGASAN_SUBFOLDERS = [
    "00-input",
    "01-peraturan-internal",
    "02-kontrak",
    "03-perencanaan",
    "04-pelaksanaan",
    "05-keuangan",
    "_PKP",
    "_KKP",
    "_LHP",
    "_QA-SAIPI",
    "_INGESTED",
    "_AUDIT-TRAIL",
    "_BUKTI-AI",
    "_SUBMIT",
]


def penugasan_folder(kode: str) -> Path:
    """Path absolut folder penugasan, dibuat bila belum ada."""
    folder = settings.data_dir / "penugasan" / kode
    folder.mkdir(parents=True, exist_ok=True)
    for sub in PENUGASAN_SUBFOLDERS:
        (folder / sub).mkdir(exist_ok=True)
    return folder


def gen_kode_penugasan(skill: str) -> str:
    """Generate kode penugasan unik: YYYY-MM-{skill-slug}-{seq}."""
    now = datetime.utcnow()
    slug = skill.replace("-", "")
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    return f"{now.year}-{now.month:02d}-{slug}-{timestamp}"


async def save_upload(file_bytes: bytes, target_path: Path) -> None:
    """Tulis bytes ke file async."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target_path, "wb") as f:
        await f.write(file_bytes)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_doc_by_filename(name: str) -> str:
    """Klasifikasi sederhana jenis dokumen berdasarkan nama file.

    Bisa di-override hasil Ingestion bila konten ternyata beda.
    """
    n = name.lower()
    if "tor" in n or "kerangka acuan" in n:
        return "TOR"
    if "rab" in n or "rincian anggaran" in n:
        return "RAB"
    if "kak" in n:
        return "KAK"
    if "hps" in n or "harga perkiraan" in n:
        return "HPS"
    if "rfi" in n:
        return "RFI"
    if "kontrak" in n or "perjanjian" in n:
        return "KONTRAK"
    if n.startswith("st") or "surat tugas" in n:
        return "ST"
    if n.startswith("kp") or "kartu penugasan" in n:
        return "KP"
    if n.startswith("pkp") or "program kerja pengawasan" in n:
        return "PKP"
    return "OTHER"


def target_subfolder_for(jenis: str) -> str:
    """Sub-folder default untuk jenis dokumen tertentu."""
    mapping = {
        "ST": "00-input",
        "KP": "00-input",
        "PKP": "00-input",
        "TOR": "03-perencanaan",
        "RAB": "03-perencanaan",
        "KAK": "02-kontrak",
        "HPS": "02-kontrak",
        "RFI": "02-kontrak",
        "KONTRAK": "02-kontrak",
    }
    return mapping.get(jenis, "00-input")


async def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def read_json(path: Path) -> dict | list:
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return json.loads(await f.read())


def append_audit_trail(folder: Path, event: dict) -> None:
    """Append 1 baris JSON ke _AUDIT-TRAIL/events.jsonl (sync, dipanggil dari tool)."""
    trail_file = folder / "_AUDIT-TRAIL" / "events.jsonl"
    trail_file.parent.mkdir(parents=True, exist_ok=True)
    event["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with open(trail_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
