"""Storage helpers: folder layout per penugasan, hash, baca/tulis file."""
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import aiofiles

from app.config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)

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
    "_FEEDBACK-AGEN",
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
    """Generate kode penugasan unik: YYYY-MM-{skill-slug}-{seq}.

    Timestamp menyertakan mikrodetik (3 digit) supaya pembuatan beruntun dalam
    1 detik (mis. auto-promote banyak finding sekaligus) tidak bentrok pada
    constraint unik `kode`.
    """
    now = datetime.utcnow()
    slug = skill.replace("-", "")
    timestamp = now.strftime("%Y%m%d-%H%M%S") + f"{now.microsecond:06d}"
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
    # Skill criteria-driven (non RKA/PBJ): auditor unggah kriteria + dokumen objek.
    if "kriteria" in n or "juknis" in n or "juklak" in n:
        return "KRITERIA"
    if "objek" in n or "obyek" in n:
        return "OBJEK"
    # Survey pendahuluan (audit-*) — memo SP, hasil entry meeting, profil auditi awal.
    if "survey" in n or "survei" in n or n.startswith("sp") or "memo sp" in n:
        return "SURVEY"
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
        "KRITERIA": "01-peraturan-internal",  # regulasi/SOP/juknis acuan (criteria-driven)
        "OBJEK": "00-input",                   # dokumen objek pengawasan (criteria-driven)
        "SURVEY": "00-survey",                 # bahan survey pendahuluan audit-* (tahapan 0)
    }
    return mapping.get(jenis, "00-input")


async def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def read_json(path: Path) -> dict | list:
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return json.loads(await f.read())


def _count_temuan(folder: Path) -> int:
    path = folder / "_KKP" / "temuan.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data.get("temuan", [])) if isinstance(data, dict) else 0
    except (json.JSONDecodeError, OSError):
        return 0


def _all_sasaran_disetujui(folder: Path) -> bool:
    path = folder / "_PKP" / "sasaran-assignment.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    sasaran = data.get("sasaran", []) if isinstance(data, dict) else []
    return bool(sasaran) and all(s.get("status") == "DISETUJUI_KT" for s in sasaran)


def compute_penugasan_status(folder: Path, dokumen_statuses: list[str], stored_status=None):
    """Turunkan status penugasan dari artefak nyata di disk, bukan dari field DB
    yang tidak pernah dimajukan. Prioritas dari tahap terjauh.

    Catatan: field `Penugasan.status` di DB historically tidak ter-update di
    setiap stage; status display selalu dihitung ulang di sini. Pengecualian:
    `USULAN_CACM` (usulan dari EWS yang belum diterima PT) tidak punya artefak,
    jadi dipertahankan apa adanya.
    """
    from app.models import PenugasanStatus

    stored_val = stored_status.value if hasattr(stored_status, "value") else stored_status
    if stored_val == PenugasanStatus.USULAN_CACM.value:
        return PenugasanStatus.USULAN_CACM

    lhp_dir = folder / "_LHP"
    kkp_dir = folder / "_KKP"

    if lhp_dir.exists() and any(
        next(lhp_dir.glob(pat), None) is not None
        for pat in ("LHP-SUBSTANSI*.docx", "LHA-*.docx", "LHR-*.docx", "LHE-*.docx", "LP-*.docx")
    ):
        return PenugasanStatus.LHP_DONE
    if (lhp_dir / "rekomendasi.json").exists():
        return PenugasanStatus.LHP_IN_PROGRESS

    n_temuan = _count_temuan(folder)
    if n_temuan > 0:
        if _all_sasaran_disetujui(folder):
            return PenugasanStatus.KKP_DONE
        return PenugasanStatus.KKP_IN_PROGRESS

    if any(s == "INGESTING" for s in dokumen_statuses):
        return PenugasanStatus.INGESTING

    pkp_file = folder / "_PKP" / "sasaran-assignment.json"
    if pkp_file.exists():
        try:
            sa = json.loads(pkp_file.read_text(encoding="utf-8"))
            if isinstance(sa, dict) and sa.get("sasaran"):
                return PenugasanStatus.PKP_DONE
        except (json.JSONDecodeError, OSError):
            pass
    return PenugasanStatus.DRAFT


# Output turunan yang BOLEH dihapus saat re-ingest / re-analisis. Tidak pernah
# menyentuh dokumen sumber, context.md, atau _PKP/sasaran-assignment.json.
def reset_downstream(folder: Path, from_stage: str) -> list[str]:
    """Hapus output turunan supaya re-ingest/re-analisis MENGGANTIKAN (bukan
    menumpuk). `from_stage`:
      - 'ingest'   → _INGESTED + _KKP + _LHP + _QA-SAIPI turunan
      - 'analysis' → _KKP + _LHP + _QA-SAIPI turunan
      - 'lhp'      → _LHP + QC lhp turunan
    Return list path relatif yang dihapus (untuk log/response).
    """
    removed: list[str] = []

    def _rm(path: Path) -> None:
        try:
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(folder)))
        except OSError as e:
            log.warning("reset_downstream: gagal hapus %s: %s", path, e)

    def _glob_rm(subdir: str, patterns: list[str]) -> None:
        d = folder / subdir
        if not d.exists():
            return
        for pat in patterns:
            for p in d.glob(pat):
                _rm(p)

    def _reset_temuan_envelope() -> None:
        path = folder / "_KKP" / "temuan.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        envelope = {
            "penugasan": data.get("penugasan", {}),
            "schema_version": data.get("schema_version", "v4.0.0"),
            "temuan": [],
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        removed.append("_KKP/temuan.json (reset → envelope)")

    clear_lhp = from_stage in ("ingest", "analysis", "lhp")
    clear_kkp = from_stage in ("ingest", "analysis")
    clear_ingested = from_stage == "ingest"

    if clear_lhp:
        _glob_rm("_LHP", ["*.docx", "rekomendasi.json"])
        _glob_rm("_QA-SAIPI", ["checklist-lhp.json", "laporan-qa-lhp.md"])
    if clear_kkp:
        _glob_rm("_KKP", [
            "*.docx", "anomalies*.json", "tor-*.json", "rab-*.json", "_pipeline_meta.json",
        ])
        _glob_rm("_QA-SAIPI", ["checklist-kkp.json", "laporan-qa-kkp.md"])
        _reset_temuan_envelope()
    if clear_ingested:
        _glob_rm("_INGESTED", ["*.json"])

    return removed


# Jenis dokumen yang dihitung sebagai "bahan analisis" untuk gate Generate Context
# (criteria-driven). ST/KP/PKP = administratif, bukan bahan analisis.
INPUT_JENIS = {"TOR", "RAB", "KAK", "HPS", "RFI", "KONTRAK", "KRITERIA", "OBJEK", "SURVEY", "OTHER"}


def context_readiness(
    folder: Path, skill: str | None = None, has_input_docs: bool = False
) -> dict:
    """Prasyarat Generate Context: KT sudah mengisi sasaran + AT sudah unggah
    bahan analisis. "Bahan" tergantung jenis skill:

    - Skill pipeline (reviu-rka-kl/reviu-pengadaan): butuh dokumen ter-digest
      (_INGESTED/*.json) karena context.md disusun dari hasil digest.
    - Skill criteria-driven (audit-kinerja, evaluasi-*, dll): tidak ada digest;
      cukup ada dokumen kriteria/objek yang diunggah (`has_input_docs`, dihitung
      caller dari DB) — agen membaca langsung via read_pdf_page.

    `skill=None` diperlakukan sebagai pipeline (kompatibilitas pemanggil lama).
    """
    from app.skills_registry import LEGACY_SKILLS

    has_sasaran = False
    sa = folder / "_PKP" / "sasaran-assignment.json"
    if sa.exists():
        try:
            d = json.loads(sa.read_text(encoding="utf-8"))
            has_sasaran = bool(isinstance(d, dict) and d.get("sasaran"))
        except (json.JSONDecodeError, OSError):
            pass
    ingested_dir = folder / "_INGESTED"
    has_ingested = ingested_dir.exists() and any(ingested_dir.glob("*.json"))

    skill_norm = str(skill).strip().lower() if skill else None
    is_pipeline = skill_norm is None or skill_norm in LEGACY_SKILLS
    # Pipeline → wajib digest. Criteria-driven → cukup dokumen input (atau digest bila ada).
    has_material = has_ingested if is_pipeline else (has_input_docs or has_ingested)

    reasons: list[str] = []
    if not has_sasaran:
        reasons.append("Ketua Tim belum mengisi sasaran")
    if not has_material:
        if is_pipeline:
            reasons.append("belum ada dokumen ter-digest (AT upload TOR/RAB atau KAK/HPS dulu)")
        else:
            reasons.append("belum ada dokumen kriteria/objek yang diunggah AT")
    return {
        "ready": has_sasaran and has_material,
        "has_sasaran": has_sasaran,
        "has_ingested": has_ingested,
        "has_input_docs": has_input_docs,
        "reason": "; ".join(reasons) if reasons else "Siap generate context",
    }


def delete_penugasan_folder(folder: Path) -> None:
    """Hapus seluruh folder penugasan dari disk (hard delete)."""
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def delete_file_quiet(path: str | None) -> None:
    """Hapus satu file bila ada; abaikan error."""
    if not path:
        return
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
    except OSError as e:
        log.warning("delete_file_quiet: gagal hapus %s: %s", path, e)


_INGESTED_PREFIX = {"TOR": "tor", "RAB": "rab"}


def stage_cached_digest(folder: Path, jenis: str, source_json: str | None) -> str | None:
    """Salin hasil digest dari cache ke _INGESTED/ penugasan ini.

    Cache HIT (sha256 sama) cukup men-skip subprocess digest yang mahal, tapi
    file hasilnya tetap harus ada di _INGESTED LOKAL karena tool agen
    (list_ingested / read_ingested_digest) hanya glob folder penugasan ini.
    Penamaan mengikuti konvensi tor-NN.json / rab-NN.json. Return path lokal,
    atau None bila source tidak ada (caller perlakukan sebagai cache miss).
    """
    if not source_json:
        return None
    src = Path(source_json)
    if not src.is_file():
        return None
    ingested_dir = folder / "_INGESTED"
    ingested_dir.mkdir(parents=True, exist_ok=True)
    prefix = _INGESTED_PREFIX.get(jenis, jenis.lower())
    n = len(list(ingested_dir.glob(f"{prefix}-*.json"))) + 1
    dest = ingested_dir / f"{prefix}-{n:02d}.json"
    try:
        shutil.copy2(src, dest)
    except OSError as e:
        log.warning("stage_cached_digest: gagal salin %s → %s: %s", src, dest, e)
        return None
    return str(dest)


def append_audit_trail(folder: Path, event: dict) -> None:
    """Append 1 baris JSON ke _AUDIT-TRAIL/events.jsonl (sync, dipanggil dari tool)."""
    trail_file = folder / "_AUDIT-TRAIL" / "events.jsonl"
    trail_file.parent.mkdir(parents=True, exist_ok=True)
    event["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with open(trail_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
