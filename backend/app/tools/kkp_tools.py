"""Tools untuk Agen Anggota Tim: append temuan ke temuan.json, render KKP.docx.

Schema temuan.json yang dipakai mengikuti yang dibutuhkan V6 render_kkp.py:

    {
        "penugasan": {
            "kode": str,
            "obyek": str,
            "jenis_pengawasan": str,  # skill: reviu-pengadaan, reviu-rka-kl
            "nomor_st": str,
            "tanggal_st": str,
        },
        "schema_version": "v4.0.0",
        "temuan": [
            {
                "id_temuan": "T-001",
                "sasaran_id": "S-01",
                "anggota_tim": {"nama_lengkap": "Sarah Aulia"},
                "judul_temuan": "...",
                "kondisi": "...",
                "kriteria": "...",
                "sebab": "..." | null,        # null untuk reviu (bukan audit)
                "akibat": "...",
                "dokumen_sumber": [
                    {"file": "02-kontrak/KAK.pdf", "halaman": 3, "kutipan": "..."}
                ],
                "status": "DRAFT",
                "tanggal_input": "ISO datetime",
                "catatan_ketua_tim": null,
                "integral": null,
            },
            ...
        ]
    }

Bridge `append_temuan` menerima input yang lebih sederhana dari agen dan
me-transform ke schema di atas — supaya agen tidak perlu tahu skema render_kkp.
"""
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import tool
from sqlalchemy import select

from app.tools.v6_bridge import qc_summary_counts, run_v6_script, safe_read_json


@tool(
    "read_context",
    "Baca context.md + sasaran-assignment.json + daftar file di subfolder input penugasan. "
    "Pakai ini PERTAMA sebelum apapun untuk dapat konteks.",
    {"penugasan_folder": str},
)
async def read_context(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    context_md = (
        (folder / "context.md").read_text(encoding="utf-8")
        if (folder / "context.md").exists()
        else ""
    )
    assignment = safe_read_json(folder / "_PKP" / "sasaran-assignment.json")

    # Daftar file di subfolder input (00-input, 01-..., 02-..., dst)
    # supaya agen tahu file mana yang bisa direferensikan di dokumen_sumber.
    input_files: list[str] = []
    for p in folder.iterdir():
        if p.is_dir() and not p.name.startswith("_"):
            for f in p.rglob("*"):
                if f.is_file():
                    input_files.append(str(f.relative_to(folder)))

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "context_md": context_md,
                        "sasaran_assignment": assignment,
                        "input_files": sorted(input_files),
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    }


@tool(
    "list_ingested",
    "Daftar file JSON hasil ingestion di _INGESTED/.",
    {"penugasan_folder": str},
)
async def list_ingested(args: dict) -> dict:
    folder = Path(args["penugasan_folder"]) / "_INGESTED"
    files = [p.name for p in folder.glob("*.json")] if folder.exists() else []
    return {"content": [{"type": "text", "text": "\n".join(files) or "(kosong)"}]}


def _normalize_temuan_input(raw: dict) -> dict:
    """Map keys umum yang dipakai agen ke schema V6 render_kkp.

    Agen sering pakai `judul` / `assigned_to`; render_kkp expect
    `judul_temuan` / `anggota_tim.nama_lengkap`. Bridge translate di sini
    supaya agen tidak perlu hafal skema persis.
    """
    out = dict(raw)

    # judul → judul_temuan
    if "judul_temuan" not in out and "judul" in out:
        out["judul_temuan"] = out.pop("judul")

    # assigned_to (str atau list[str]) → anggota_tim: {"nama_lengkap": str}
    if "anggota_tim" not in out:
        assigned = out.pop("assigned_to", None) or out.pop("anggota", None)
        if isinstance(assigned, list) and assigned:
            assigned = assigned[0]
        if isinstance(assigned, dict):
            out["anggota_tim"] = assigned
        elif isinstance(assigned, str):
            out["anggota_tim"] = {"nama_lengkap": assigned}
        else:
            out["anggota_tim"] = {"nama_lengkap": ""}
    elif isinstance(out.get("anggota_tim"), str):
        out["anggota_tim"] = {"nama_lengkap": out["anggota_tim"]}

    # Default-fill field SAIPI yang wajib di render_kkp
    out.setdefault("sasaran_id", "")
    out.setdefault("kondisi", "")
    out.setdefault("kriteria", "")
    out.setdefault("akibat", "")
    out.setdefault("sebab", None)  # reviu tidak punya sebab; bisa null
    out.setdefault("dokumen_sumber", [])

    # Metadata
    out.setdefault("tanggal_input", datetime.utcnow().isoformat() + "Z")
    out.setdefault("status", "DRAFT")
    out.setdefault("catatan_ketua_tim", None)
    out.setdefault("integral", None)

    return out


@tool(
    "append_temuan",
    "Append 1 temuan ke _KKP/temuan.json. Bridge otomatis transform key sederhana "
    "(judul, assigned_to) ke schema V6 (judul_temuan, anggota_tim.nama_lengkap). "
    "Field wajib di input: sasaran_id, anggota_tim/assigned_to, judul, kondisi, kriteria, "
    "akibat, dokumen_sumber[{file, halaman, kutipan}].",
    {
        "penugasan_folder": str,
        "temuan": dict,
    },
)
async def append_temuan(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    path = folder / "_KKP" / "temuan.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Init kalau belum ada (umumnya sudah ada karena scaffolding di POST /penugasan,
    # tapi defensive).
    if path.exists():
        data = safe_read_json(path) or {}
    else:
        data = {}
    if not data or "penugasan" not in data:
        data = {
            "penugasan": {
                "kode": folder.name,
                "obyek": "",
                "jenis_pengawasan": "",
                "nomor_st": "",
                "tanggal_st": None,
            },
            "schema_version": "v4.0.0",
            "temuan": [],
        }
    data.setdefault("temuan", [])

    new_temuan = _normalize_temuan_input(args["temuan"])
    if not new_temuan.get("id_temuan"):
        seq = len(data["temuan"]) + 1
        new_temuan["id_temuan"] = f"T-{seq:03d}"

    data["temuan"].append(new_temuan)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "content": [
            {
                "type": "text",
                "text": f"OK|id={new_temuan['id_temuan']}|total_now={len(data['temuan'])}",
            }
        ]
    }


@tool(
    "render_kkp_docx",
    "Render KKP-{nama-anggota}.docx menggunakan scripts/render_kkp.py V6.",
    {"penugasan_folder": str, "nama_anggota": str},
)
async def render_kkp_docx(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/render_kkp.py",
        [
            "--penugasan",
            args["penugasan_folder"],
            "--anggota",
            args["nama_anggota"],
        ],
        timeout=120,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:400]}"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"OK|stdout={out[:200]}"}]}


@tool(
    "run_qc_kkp",
    "Jalankan QC SAIPI stage KKP secara SYNCHRONOUS. Memanggil scripts/qc_saipi.py "
    "V6 dengan --stage kkp lalu return status + breakdown severity + excerpt laporan. "
    "Pakai SETELAH semua temuan + KKP.docx selesai untuk gate kepatuhan SAIPI.",
    {"penugasan_folder": str},
)
async def run_qc_kkp(args: dict) -> dict:
    """Sync version dari QC KKP — ganti pola async marker-flag yang lama.

    Pola lama (`request_qc_kkp` writer flag) bermasalah: agen yang memanggilnya
    tidak dapat hasil → improvisasi sendiri. Sync version langsung jalankan
    qc_saipi.py V6 dan return ringkasan untuk dipakai agen langsung.
    """
    folder = Path(args["penugasan_folder"])
    if not folder.exists():
        return {
            "content": [{
                "type": "text",
                "text": f"FAILED|folder penugasan tidak ada: {folder} — cek path (typo?), jangan anggap PASS",
            }],
            "is_error": True,
        }
    code, out, err = await run_v6_script(
        "scripts/qc_saipi.py",
        ["--penugasan", str(folder), "--stage", "kkp"],
        timeout=120,
    )

    checklist = safe_read_json(folder / "_QA-SAIPI" / "checklist-kkp.json")
    total_kritis, total_peringatan, total_needs_review, total_ok = qc_summary_counts(checklist)

    if total_kritis > 0:
        status_label = "BLOCKED_KRITIS"
    elif total_peringatan > 0 or total_needs_review > 0:
        status_label = "PASS_WITH_WARNINGS"
    else:
        status_label = "PASS"

    laporan_path = folder / "_QA-SAIPI" / "laporan-qa-kkp.md"
    laporan_excerpt = ""
    if laporan_path.exists():
        laporan_excerpt = laporan_path.read_text(encoding="utf-8")[:4000]

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"stage=kkp|status={status_label}|exit_code={code}|"
                    f"kritis={total_kritis}|peringatan={total_peringatan}|"
                    f"needs_review={total_needs_review}|ok={total_ok}|"
                    f"laporan_path={laporan_path}\n\n"
                    f"=== LAPORAN QA (excerpt) ===\n{laporan_excerpt}"
                ),
            }
        ]
    }


# =============================================================================
# CONTEXT GENERATION — AI susun context.md dari digest + sasaran (Step 0 AT)
# =============================================================================


# Field kunci yang DIHARAPKAN ada per jenis digest. Sumber tunggal — dipakai
# _run_ingestion (deteksi field hilang → fallback LLM) dan digestion_harness
# (metrik cakupan). Cocokkan dengan key yang diisi _summarize_digest_raw.
COVERAGE_KEYS = {
    "TOR": ["kementerian", "program_nama", "kegiatan_nama", "ro", "total_biaya", "dasar_hukum"],
    "RAB": ["kementerian", "ro", "jumlah_komponen", "total_pagu"],
    "PENGADAAN": ["obyek", "nilai_hps", "jangka_waktu"],
}


def _overlay_fallback(data: dict, out: dict) -> dict:
    """Tumpangkan nilai dari blok `_llm_fallback` (hasil fallback LLM saat ingestion)
    untuk key ringkasan yang KOSONG dari parse deterministik.

    Digest deterministik dibiarkan apa adanya (jujur); nilai pulihan disimpan
    terpisah di `data["_llm_fallback"]` saat ingestion. Di sini kita isikan ke
    ringkasan agar konsumen (read_ingested_digest, harness) melihatnya. Provenans
    dicatat di `out["_llm_recovered"]`.
    """
    if not isinstance(data, dict):
        return out
    fb = data.get("_llm_fallback")
    if not isinstance(fb, dict):
        return out
    recovered = []
    for k, v in fb.items():
        if k == "_meta":
            continue
        if out.get(k) in (None, "", [], 0) and v not in (None, "", [], 0):
            out[k] = v
            recovered.append(k)
    if recovered:
        out["_llm_recovered"] = recovered
    return out


def _summarize_digest(name: str, data: dict) -> dict:
    """Ringkasan field kunci satu file digest (untuk context.md / metrik / agen).

    Membungkus parse deterministik (`_summarize_digest_raw`) lalu menumpangkan
    field hasil fallback LLM bila ada (`_overlay_fallback`).
    """
    out = _summarize_digest_raw(name, data)
    return _overlay_fallback(data, out)


def _summarize_digest_raw(name: str, data: dict) -> dict:
    """Ambil field kunci dari satu file digest untuk bahan context.md.

    Catatan: digest RAB JUGA punya `identitas_ro` (seperti TOR), jadi RAB harus
    dideteksi LEBIH DULU (lewat `komponen`/`total_pagu`) — kalau tidak, RAB salah
    ter-label TOR & data komponen/pagu hilang. Pengadaan menyimpan hasil per-dokumen
    di bawah `dokumen`, bukan top-level.
    """
    out: dict = {"file": name}
    if not isinstance(data, dict):
        return out

    # RAB (digest_rab): punya komponen / total_pagu (cek SEBELUM TOR).
    komp = data.get("komponen")
    if komp is not None or data.get("total_pagu") is not None:
        out["jenis"] = "RAB"
        ident = data.get("identitas_ro") or data.get("identitas") or {}
        if isinstance(ident, dict):
            for k in ("kementerian", "unit_eselon_i", "program_nama", "program",
                      "kegiatan_nama", "kegiatan", "ro", "alokasi_dana"):
                if ident.get(k):
                    out[k] = ident[k]
        if isinstance(komp, list):
            out["jumlah_komponen"] = len(komp)
        if data.get("total_pagu") is not None:
            out["total_pagu"] = data["total_pagu"]
        return out

    # TOR (digest_tor): identitas_ro + biaya + dasar_hukum (tanpa komponen).
    idr = data.get("identitas_ro")
    if isinstance(idr, dict):
        out["jenis"] = "TOR"
        for k in ("kementerian", "unit_eselon_i", "program_nama", "kegiatan_nama",
                  "ro", "volume", "satuan"):
            if idr.get(k):
                out[k] = idr[k]
        biaya = data.get("biaya")
        if isinstance(biaya, dict) and biaya.get("total"):
            out["total_biaya"] = biaya["total"]
            if biaya.get("sumber_dana"):
                out["sumber_dana"] = biaya["sumber_dana"]
        dh = data.get("dasar_hukum")
        if isinstance(dh, list):
            out["dasar_hukum"] = [
                f"{d.get('jenis_regulasi') or ''} {d.get('nomor') or ''}/{d.get('tahun') or ''}".strip()
                for d in dh[:8]
            ]
        return out

    # Pengadaan (digest_pengadaan): hasil per-dokumen di `dokumen.{kak,hps,rfi,kontrak}`.
    dok = data.get("dokumen")
    if isinstance(dok, dict):
        out["jenis"] = "PENGADAAN"
        out["dokumen_per_jenis"] = {k: len(v) for k, v in dok.items() if isinstance(v, list)}

        def _first_parsed(key: str) -> dict:
            lst = dok.get(key) or []
            p = lst[0].get("parsed") if lst and isinstance(lst[0], dict) else None
            return p if isinstance(p, dict) else {}

        kak, hps = _first_parsed("kak"), _first_parsed("hps")
        nama = kak.get("nama_pekerjaan") or hps.get("nama_pekerjaan")
        if nama:
            out["obyek"] = nama
        nilai = hps.get("nilai_hps") or kak.get("nilai_hps")
        if nilai:
            out["nilai_hps"] = nilai
        per = kak.get("periode") or hps.get("periode")
        if per:
            out["jangka_waktu"] = per
        if kak.get("sla_value"):
            out["sla"] = kak["sla_value"]
        return out

    # Fallback: pengadaan top-level (struktur lama).
    out["jenis"] = "PENGADAAN"
    for k in ("obyek", "nilai_hps", "metode_pemilihan", "jangka_waktu", "sla"):
        if data.get(k):
            out[k] = data[k]
    return out


@tool(
    "read_ingested_digest",
    "Baca RINGKASAN isi hasil ingestion (_INGESTED/*.json) — field kunci seperti "
    "kementerian, program, kegiatan, RO, volume, total biaya, dasar hukum, jumlah "
    "komponen RAB. Dipakai untuk menyusun context.md. Return JSON ringkas (di-cap).",
    {"penugasan_folder": str},
)
async def read_ingested_digest(args: dict) -> dict:
    folder = Path(args["penugasan_folder"]) / "_INGESTED"
    items: list[dict] = []
    if folder.exists():
        for p in sorted(folder.glob("*.json")):
            data = safe_read_json(p)
            items.append(_summarize_digest(p.name, data))
    text = json.dumps({"total": len(items), "digest": items}, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text[:8000]}]}


@tool(
    "get_team_members",
    "Daftar anggota tim penugasan (nama + NIP) berdasarkan assigned_to di "
    "sasaran-assignment.json, di-lookup ke data user. Dipakai untuk mengisi tabel "
    "Tim di context.md. Jabfung tidak tersimpan di sistem — gunakan default wajar.",
    {"penugasan_folder": str},
)
async def get_team_members(args: dict) -> dict:
    from app.database import SessionLocal
    from app.models import User

    folder = Path(args["penugasan_folder"])
    assignment = safe_read_json(folder / "_PKP" / "sasaran-assignment.json")
    names: list[str] = []
    if isinstance(assignment, dict):
        for s in assignment.get("sasaran", []) or []:
            for nm in (s.get("assigned_to") or []):
                if nm and nm not in names:
                    names.append(nm)

    members: list[dict] = []
    if names:
        async with SessionLocal() as db:
            rows = (
                await db.execute(select(User).where(User.nama_lengkap.in_(names)))
            ).scalars().all()
            found = {u.nama_lengkap: u.nip for u in rows}
        for nm in names:
            members.append({"nama": nm, "nip": found.get(nm, "[DIISI AUDITOR]")})

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({"anggota": members}, ensure_ascii=False),
        }]
    }


@tool(
    "write_context_md",
    "Tulis/timpa context.md penugasan dengan konten lengkap (markdown). Pakai untuk "
    "menyimpan context.md hasil generate AI. WAJIB format lolos QC: ada baris "
    "`Tujuan: ...` dan `Ruang Lingkup: ...` (inline, bukan heading), tabel Tim dengan "
    "jabfung (mis. Auditor Madya/Muda/Pertama), tanpa placeholder selain [DIISI AUDITOR].",
    {"penugasan_folder": str, "content": str},
)
async def write_context_md(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    content = args.get("content", "")
    if not content.strip():
        return {
            "content": [{"type": "text", "text": "FAILED|content kosong"}],
            "is_error": True,
        }
    path = folder / "context.md"
    path.write_text(content, encoding="utf-8")
    return {
        "content": [{
            "type": "text",
            "text": f"OK|context.md ditulis ({len(content)} char)",
        }]
    }


KKP_TOOLS = [
    read_context, list_ingested, read_ingested_digest, get_team_members,
    write_context_md, append_temuan, render_kkp_docx, run_qc_kkp,
]
