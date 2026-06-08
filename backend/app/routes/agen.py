"""Routes orkestrasi agen + ingestion worker."""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents import (
    build_anggota_tim_agent,
    build_ketua_tim_agent,
)
from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models import (
    AgentRun,
    DocumentCache,
    Dokumen,
    DokumenStatus,
    Penugasan,
    PenugasanStatus,
    Role,
    User,
)
from app.config import get_settings
from app.llm_extract import extract_pdf_pages, extract_fields_hybrid, llm_extract_fields  # noqa: F401
from app.storage import INPUT_JENIS, context_readiness, reset_downstream
from app.tools.kkp_tools import COVERAGE_KEYS, _summarize_digest
from app.tools.v6_bridge import run_v6_script, safe_read_json

settings = get_settings()

# Jenis dokumen yang punya V6 digest script (perlu di-ingest ulang saat re-ingest)
_DIGESTIBLE_JENIS = ("TOR", "RAB", "KAK", "HPS", "RFI", "KONTRAK")

# Batas subprocess digest yang jalan bersamaan. Tiap digest = 1 proses python3
# (CPU/mem). 4 cukup mempercepat penugasan multi-dokumen tanpa membanjiri host.
_INGEST_CONCURRENCY = 4

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agen", tags=["agen"])

AGENT_BUILDERS = {
    "anggota_tim": build_anggota_tim_agent,
    "ketua_tim": build_ketua_tim_agent,
}


# ============================================================
# INGESTION WORKER (synchronous, inline)
# ============================================================

async def _digest_subprocess(
    sem: asyncio.Semaphore, script: str, args: list[str], out: Path, timeout: int
) -> tuple[bool, str | None]:
    """Jalankan 1 digest subprocess (independen, tidak menyentuh DB).

    Dibatasi semaphore supaya banyak dokumen tidak membuka terlalu banyak proses
    sekaligus. Return (success, error_message_bila_gagal).
    """
    async with sem:
        code, _, err = await run_v6_script(script, args, timeout=timeout)
    ok = code == 0 and out.exists()
    return ok, (None if ok else (err or f"{script} returned non-zero"))


async def _cache_put(db: AsyncSession, sha256: str, jenis: str | None, path: str) -> None:
    """Upsert DocumentCache untuk digest per-file (TOR/RAB). Idempotent.

    Sekali sebuah PDF di-extract, file identik (sha256 sama) di penugasan lain
    bisa langsung pakai hasilnya tanpa subprocess ulang (lihat routes.dokumen).
    """
    existing = (
        await db.execute(select(DocumentCache).where(DocumentCache.sha256 == sha256))
    ).scalar_one_or_none()
    if existing:
        existing.ingested_json_path = path
        existing.jenis = jenis or existing.jenis
        existing.extracted_by = "deterministic"
        existing.extracted_at = datetime.utcnow()
    else:
        db.add(
            DocumentCache(
                sha256=sha256,
                jenis=jenis or "OTHER",
                ingested_json_path=path,
                extracted_by="deterministic",
                extracted_at=datetime.utcnow(),
            )
        )


def _llm_fallback_sync(out_path: Path, jenis_summary: str, pdf_paths: list[str], model: str) -> int:
    """BLOCKING: pulihkan field kunci yang hilang dari digest deterministik via LLM murah.

    Hanya dipanggil bila digest sukses tapi ada field kunci kosong (parser tak
    menangani layout). Membaca TEKS dokumen (pdfplumber) lalu meminta model murah
    mengekstrak field yang hilang, dan menyimpannya TERPISAH di blok `_llm_fallback`
    pada file digest (parse deterministik dibiarkan apa adanya). `_summarize_digest`
    yang menumpangkannya ke ringkasan. Return jumlah field yang berhasil dipulihkan.

    Dipanggil lewat asyncio.to_thread (klien anthropic + pdfplumber blocking).
    """
    data = safe_read_json(out_path)
    if not isinstance(data, dict) or not data:
        return 0
    summ = _summarize_digest(out_path.name, data)
    keys = COVERAGE_KEYS.get(jenis_summary, [])
    missing = [k for k in keys if summ.get(k) in (None, "", [], 0)]
    if not missing:
        return 0

    pages: list[str] = []
    for p in pdf_paths:
        pages += extract_pdf_pages(p)
    # Hybrid: regex deterministik (LiteParse) dulu, Haiku hanya untuk residual.
    # Bila semua field hilang ternyata bisa diambil regex → LLM TIDAK dipanggil.
    res = extract_fields_hybrid(pages, jenis_summary, missing, model=model)
    if res.get("_error"):
        log.warning("LLM fallback %s: %s", out_path.name, res["_error"])
        # Tetap simpan apa-apa yang sempat di-ekstrak regex sebelum error LLM
    recovered = {k: res[k] for k in missing if res.get(k) not in (None, "", [], 0)}
    if not recovered:
        return 0

    # Trace: tag sumber tiap field (deterministic vs llm) berdasarkan apa yang
    # liteparse_extract mampu kasih. Simpel: kalau regex deterministic punya field
    # itu, tag 'deterministic'; sisanya 'llm'.
    try:
        from app.liteparse_extract import extract_fields_deterministic
        det = extract_fields_deterministic(pages, jenis_summary)
    except Exception:  # noqa: BLE001
        det = {}
    sources = {k: ("deterministic" if k in det else "llm") for k in recovered.keys()}

    fb = data.get("_llm_fallback") if isinstance(data.get("_llm_fallback"), dict) else {}
    fb.update(recovered)
    fb["_meta"] = {
        "model": model,
        "at": datetime.utcnow().isoformat() + "Z",
        "fields": sorted(recovered.keys()),
        "sources": sources,
    }
    data["_llm_fallback"] = fb
    try:
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("Gagal tulis _llm_fallback ke %s: %s", out_path, e)
        return 0
    log.info("LLM fallback %s: pulih %s", out_path.name, sorted(recovered.keys()))
    return len(recovered)


async def _run_llm_fallback(jobs: list, results: list) -> None:
    """Jalankan fallback LLM untuk semua digest sukses yang field kuncinya hilang.

    Paralel & dibatasi semaphore; tiap pekerjaan di thread (blocking IO+LLM).
    Hanya menyentuh file digest JSON (bukan DB). No-op bila fitur OFF.
    """
    if not settings.digest_llm_fallback:
        return
    fb_jobs: list[tuple[Path, str, list[str]]] = []
    for (kind, payload, out, _), (ok, _err) in zip(jobs, results):
        if not ok:
            continue
        if kind == "file":
            d = payload
            js = "TOR" if d.jenis == "TOR" else ("RAB" if d.jenis == "RAB" else None)
            if js:
                fb_jobs.append((out, js, [d.file_path]))
        else:  # pbj folder-level
            fb_jobs.append((out, "PENGADAAN", [d.file_path for d in payload]))
    if not fb_jobs:
        return

    model = settings.digest_llm_model
    sem = asyncio.Semaphore(_INGEST_CONCURRENCY)

    async def _one(out: Path, js: str, pdfs: list[str]) -> int:
        async with sem:
            return await asyncio.to_thread(_llm_fallback_sync, out, js, pdfs, model)

    counts = await asyncio.gather(*(_one(*fj) for fj in fb_jobs), return_exceptions=True)
    total = sum(c for c in counts if isinstance(c, int))
    if total:
        log.info("LLM fallback ingestion: pulih %d field di %d dokumen", total, len(fb_jobs))


async def _run_ingestion(penugasan_id: int) -> None:
    """Jalankan digest deterministic V6 untuk semua dokumen di penugasan.

    Digest TOR/RAB/PBJ dijalankan PARALEL (asyncio.gather, dibatasi semaphore)
    karena tiap subprocess independen — mempercepat penugasan multi-dokumen.
    Mutasi DB + tulis cache dilakukan SEKUENSIAL setelah gather (AsyncSession
    tidak aman dipakai banyak coroutine bersamaan). Hasil digest per-file
    (TOR/RAB) di-cache by sha256; PBJ folder-level tidak di-cache.
    """
    async with SessionLocal() as db:
        p = (
            await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
        ).scalar_one_or_none()
        if not p:
            return
        docs = (
            await db.execute(
                select(Dokumen).where(
                    Dokumen.penugasan_id == penugasan_id,
                    Dokumen.status == DokumenStatus.INGESTING,
                )
            )
        ).scalars().all()

        folder = Path(p.folder_path)
        ingested_dir = folder / "_INGESTED"
        ingested_dir.mkdir(parents=True, exist_ok=True)

        tor_docs = [d for d in docs if d.jenis == "TOR"]
        rab_docs = [d for d in docs if d.jenis == "RAB"]
        pbj_docs = [d for d in docs if d.jenis in ("KAK", "HPS", "RFI", "KONTRAK")]
        other_docs = [d for d in docs if d.jenis in (None, "ST", "KP", "PKP", "OTHER")]

        sem = asyncio.Semaphore(_INGEST_CONCURRENCY)
        # Daftar job: (kind, payload, out_path, coro). kind="file" → cache-able;
        # kind="pbj" → folder-level, satu output dipakai banyak dokumen.
        jobs: list[tuple[str, object, Path, object]] = []

        for i, d in enumerate(tor_docs, start=1):
            out = ingested_dir / f"tor-{i:02d}.json"
            jobs.append((
                "file", d, out,
                _digest_subprocess(
                    sem, "scripts/reviu-rka-kl/digest_tor.py",
                    [d.file_path, "--no-raw", "-o", str(out)], out, 120,
                ),
            ))
        for i, d in enumerate(rab_docs, start=1):
            out = ingested_dir / f"rab-{i:02d}.json"
            jobs.append((
                "file", d, out,
                _digest_subprocess(
                    sem, "scripts/reviu-rka-kl/digest_rab.py",
                    [d.file_path, "-o", str(out)], out, 120,
                ),
            ))
        if pbj_docs:
            out = ingested_dir / "pengadaan-digest.json"
            jobs.append((
                "pbj", pbj_docs, out,
                _digest_subprocess(
                    sem, "scripts/audit-pengadaan/digest_pengadaan.py",
                    [str(folder), "-o", str(out)], out, 180,
                ),
            ))

        # Jalankan SEMUA subprocess paralel
        results = await asyncio.gather(*(coro for _, _, _, coro in jobs))

        # Terapkan hasil + cache (sekuensial — aman untuk satu AsyncSession)
        for (kind, payload, out, _), (ok, err) in zip(jobs, results):
            if kind == "file":
                d = payload  # type: ignore[assignment]
                if ok:
                    d.status = DokumenStatus.READY
                    d.ingested_json_path = str(out)
                    d.ingested_at = datetime.utcnow()
                    await _cache_put(db, d.sha256, d.jenis, str(out))
                else:
                    d.status = DokumenStatus.FAILED
                    d.error_message = (err or "digest returned non-zero")[:500]
            else:  # pbj
                for d in payload:  # type: ignore[assignment]
                    if ok:
                        d.status = DokumenStatus.READY
                        d.ingested_json_path = str(out)
                        d.ingested_at = datetime.utcnow()
                    else:
                        d.status = DokumenStatus.FAILED
                        d.error_message = (err or "digest_pengadaan returned non-zero")[:500]

        for d in other_docs:
            d.status = DokumenStatus.READY
            d.ingested_at = datetime.utcnow()

        # Tier-2 (opsional, OFF default): untuk digest yang field kuncinya hilang,
        # pulihkan via LLM murah dari TEKS dokumen. File-only (tidak menyentuh DB).
        await _run_llm_fallback(jobs, results)

        # Post-process digest pengadaan: rescue file yg masuk `unclassified_files`
        # karena pattern V6 terlalu ketat (mis. prefix `Signed_` dari Privy/eMaterai
        # membuat `\bKAK\b` gagal). Robust classifier + re-parse via V6 module.
        # File-only, V6 read-only. Lihat app.digest_postprocess.
        for (kind, payload, out, _) in jobs:
            if kind == "pbj" and out.exists():
                try:
                    from app.digest_postprocess import repair_pengadaan_digest

                    repair_pengadaan_digest(out, folder=folder)
                except Exception as exc:
                    # Repair best-effort; jangan gagalkan ingestion bila gagal.
                    print(f"[digest_postprocess] warning: {exc}")

        await db.commit()


@router.post("/ingest/{penugasan_id}")
async def trigger_ingestion(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ingestion (synchronous inline, response 30-60 detik)."""
    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")

    # Re-ingest = REPLACE: bersihkan _INGESTED + output analisis turunan (KKP/LHP)
    # supaya hasil baru menggantikan yang lama, bukan menumpuk.
    removed = reset_downstream(Path(p.folder_path), from_stage="ingest")

    # Semua dokumen yang punya digest script di-set INGESTING agar di-digest ulang.
    docs = (
        await db.execute(
            select(Dokumen).where(
                Dokumen.penugasan_id == p.id,
                Dokumen.jenis.in_(_DIGESTIBLE_JENIS),
            )
        )
    ).scalars().all()
    for d in docs:
        d.status = DokumenStatus.INGESTING
        d.ingested_json_path = None
        d.ingested_at = None
        d.error_message = None
    p.status = PenugasanStatus.INGESTING
    await db.commit()

    await _run_ingestion(p.id)

    updated = (
        await db.execute(select(Dokumen).where(Dokumen.penugasan_id == p.id))
    ).scalars().all()
    return {
        "penugasan_id": p.id,
        "reset_downstream": removed,
        "dokumen_diproses": [
            {
                "id": d.id,
                "nama_file": d.nama_file,
                "jenis": d.jenis,
                "status": d.status if isinstance(d.status, str) else d.status.value,
            }
            for d in updated
        ],
    }


# ============================================================
# AGENT STREAM (SSE) — run DI-DECOUPLE dari koneksi klien
# ============================================================
#
# Masalah lama: generator SSE = tempat agen jalan. Saat klien disconnect
# (pindah tab / tutup browser), sse-starlette CANCEL generator → subprocess
# Claude mati di tengah jalan, dan AgentRun nyangkut status "running".
#
# Solusi: agen jalan di asyncio.Task TERPISAH (RunHandle) yang hidup
# independen dari koneksi. Event di-buffer; koneksi SSE hanya men-subscribe
# ke buffer. Disconnect → subscriber berhenti, TAPI task tetap jalan sampai
# selesai (DB selalu mencapai completed/failed). Re-mount tab → /attach
# me-replay buffer + lanjut tail.


class RunHandle:
    """Pegangan satu run agen yang hidup independen dari koneksi SSE."""

    def __init__(self, run_id: int, agent_name: str, penugasan_id: int):
        self.run_id = run_id
        self.agent_name = agent_name
        self.penugasan_id = penugasan_id
        self.events: list[dict] = []      # buffer event SSE (append-only)
        self.done = False
        self.cond = asyncio.Condition()
        self.task: asyncio.Task | None = None

    async def emit(self, event: str, data: dict) -> None:
        async with self.cond:
            self.events.append({"event": event, "data": json.dumps(data)})
            self.cond.notify_all()

    async def finish(self) -> None:
        async with self.cond:
            self.done = True
            self.cond.notify_all()

    async def subscribe(self):
        """Yield semua event dari awal lalu tail sampai run selesai.

        Aman untuk banyak subscriber sekaligus (mis. 2 tab). Saat klien
        disconnect, generator ini di-cancel — TANPA mempengaruhi task agen.
        """
        idx = 0
        while True:
            async with self.cond:
                while idx >= len(self.events) and not self.done:
                    await self.cond.wait()
                pending = self.events[idx:]
                idx = len(self.events)
                finished = self.done
            for ev in pending:
                yield ev
            if finished and idx >= len(self.events):
                return


# Registry in-process. Hilang saat backend restart (uvicorn --reload) — itu
# kompromi yang diterima untuk dev; run yang ke-interupsi restart akan tampak
# "running" basi di DB sampai run berikutnya.
_RUNS: dict[int, RunHandle] = {}
_ACTIVE_BY_KEY: dict[tuple[int, str], int] = {}


def _active_handle(penugasan_id: int, agent_name: str) -> RunHandle | None:
    rid = _ACTIVE_BY_KEY.get((penugasan_id, agent_name))
    if rid is None:
        return None
    return _RUNS.get(rid)


async def _execute_run(handle: RunHandle, user_prompt: str, user_id: int) -> None:
    """Loop agen sebenarnya — jalan sebagai task terpisah dari koneksi SSE.

    ISOLATION GUARANTEE (sama spt sebelumnya): AGENT_BUILDERS[name]() bikin
    ClaudeAgentOptions baru per invoke; ClaudeSDKClient spawn subprocess baru;
    di-terminate saat __aexit__. Zero state leak antar run.
    """
    run_id = handle.run_id
    await handle.emit("start", {"agent": handle.agent_name, "run_id": run_id})

    output_parts: list[str] = []
    tool_calls: list[dict] = []
    error_msg: str | None = None

    try:
        options = AGENT_BUILDERS[handle.agent_name]()
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_prompt)
            async for message in client.receive_response():
                content = getattr(message, "content", None) or []
                for block in content:
                    btype = type(block).__name__
                    if btype == "TextBlock":
                        text = getattr(block, "text", "")
                        output_parts.append(text)
                        await handle.emit("text", {"text": text})
                    elif btype == "ToolUseBlock":
                        name = getattr(block, "name", "?")
                        inp = getattr(block, "input", {})
                        tool_calls.append({"tool": name, "input": inp})
                        await handle.emit("tool_use", {"tool": name, "input": inp})
                    elif btype == "ToolResultBlock":
                        result = getattr(block, "content", "")
                        if isinstance(result, list) and result:
                            result_text = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
                        else:
                            result_text = str(result)[:500]
                        await handle.emit("tool_result", {"result": result_text[:500]})
    except Exception as e:  # noqa: BLE001
        log.exception("Agent run %s failed: %s", run_id, e)
        error_msg = str(e)[:1000]

    # Persist hasil akhir (SELALU tercapai — tidak bergantung koneksi klien).
    try:
        async with SessionLocal() as db:
            row = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            row.status = "failed" if error_msg else "completed"
            row.output_summary = "".join(output_parts)[:2000]
            row.tool_calls = tool_calls
            row.error_message = error_msg
            row.ended_at = datetime.utcnow()
            await db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Gagal persist hasil run %s", run_id)

    if error_msg:
        await handle.emit("error", {"message": error_msg[:500]})
    else:
        await handle.emit("done", {"run_id": run_id})
    await handle.finish()

    # Lepas dari index "active" supaya /attach berikutnya tahu run sudah kelar.
    _ACTIVE_BY_KEY.pop((handle.penugasan_id, handle.agent_name), None)


async def _start_run(agent_name: str, full_prompt: str, penugasan_id: int, user_id: int) -> RunHandle:
    """Buat AgentRun di DB + RunHandle + jadwalkan task agen di background."""
    async with SessionLocal() as db:
        run = AgentRun(
            penugasan_id=penugasan_id,
            agent_name=agent_name,
            user_id=user_id,
            status="running",
            input_summary=full_prompt[:500],
            started_at=datetime.utcnow(),
            tool_calls=[],
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()

    handle = RunHandle(run_id, agent_name, penugasan_id)
    _RUNS[run_id] = handle
    _ACTIVE_BY_KEY[(penugasan_id, agent_name)] = run_id
    handle.task = asyncio.create_task(_execute_run(handle, full_prompt, user_id))
    return handle


def _check_agent_role(agent_name: str, role: Role) -> None:
    if agent_name not in AGENT_BUILDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agen tidak dikenal: {agent_name}")
    if agent_name == "anggota_tim" and role != Role.AT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Anggota Tim")
    if agent_name == "ketua_tim" and role not in (Role.KT, Role.PT):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Ketua Tim atau Pengendali Teknis")


@router.get("/{agent_name}/stream")
async def stream_agent(
    agent_name: str,
    penugasan_id: int,
    prompt: str,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mulai run agen baru lalu stream eventnya. Run jalan di background task —
    bila klien disconnect, run TETAP berjalan (lihat /attach untuk reconnect)."""
    user, role = current
    _check_agent_role(agent_name, role)

    p = (await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")

    # Hard gate: Generate Context ([MODE:CONTEXT]) hanya boleh bila KT sudah isi
    # sasaran + AT sudah upload bahan (digest untuk RKA/PBJ, atau kriteria/objek
    # untuk skill criteria-driven).
    if "[MODE:CONTEXT]" in prompt:
        input_jenis = (
            await db.execute(
                select(Dokumen.jenis).where(
                    Dokumen.penugasan_id == p.id,
                    Dokumen.status == DokumenStatus.READY,
                )
            )
        ).scalars().all()
        has_input = any((j or "").upper() in INPUT_JENIS for j in input_jenis)
        rd = context_readiness(Path(p.folder_path), skill=p.skill, has_input_docs=has_input)
        if not rd["ready"]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Belum bisa generate context — {rd['reason']}.",
            )

    # Tolak start ganda bila masih ada run aktif untuk penugasan+agen ini.
    existing = _active_handle(p.id, agent_name)
    if existing is not None and not existing.done:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Masih ada analisis berjalan untuk agen ini. Tunggu selesai atau buka tab Chat untuk melihat progres.",
        )

    skill_str = p.skill if isinstance(p.skill, str) else p.skill.value
    full_prompt = (
        f"Penugasan kode={p.kode}, skill={skill_str}, folder={p.folder_path}\n"
        f"Pengguna: {user.nama_lengkap} ({role.value})\n\n"
        f"Permintaan: {prompt}"
    )
    handle = await _start_run(agent_name, full_prompt, p.id, user.id)
    return EventSourceResponse(handle.subscribe())


@router.get("/{agent_name}/attach")
async def attach_agent(
    agent_name: str,
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
):
    """Reconnect ke run aktif (mis. setelah pindah tab / login ulang).

    Bila ada run aktif → stream (replay buffer + tail). Bila tidak → kirim
    event `idle` lalu tutup, sehingga frontend tahu tidak ada yang berjalan.
    """
    user, role = current
    _check_agent_role(agent_name, role)
    handle = _active_handle(penugasan_id, agent_name)

    if handle is None:
        async def _idle():
            yield {"event": "idle", "data": json.dumps({"active": False})}
        return EventSourceResponse(_idle())

    return EventSourceResponse(handle.subscribe())


@router.get("/{agent_name}/active")
async def active_agent_run(
    agent_name: str,
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
) -> dict:
    """Cek cepat (non-stream) apakah ada run aktif + teks terkumpul sejauh ini."""
    handle = _active_handle(penugasan_id, agent_name)
    if handle is None or handle.done:
        return {"active": False}
    text = "".join(
        json.loads(e["data"]).get("text", "")
        for e in handle.events
        if e["event"] == "text"
    )
    return {"active": True, "run_id": handle.run_id, "text_so_far": text}


# ============================================================
# CHAT HISTORY — semua run agen untuk penugasan tertentu
# ============================================================


@router.get("/{agent_name}/history")
async def get_agent_history(
    agent_name: str,
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return list semua AgentRun untuk penugasan + agent, urutan oldest → newest.

    Dipakai oleh frontend ChatTab untuk render percakapan lampau saat mount,
    supaya user yang login ulang tidak mulai dari kosong.
    """
    if agent_name not in AGENT_BUILDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agen tidak dikenal: {agent_name}")

    rows = (
        await db.execute(
            select(AgentRun)
            .where(
                AgentRun.penugasan_id == penugasan_id,
                AgentRun.agent_name == agent_name,
            )
            .order_by(AgentRun.started_at.asc())
        )
    ).scalars().all()

    return {
        "agent_name": agent_name,
        "penugasan_id": penugasan_id,
        "total": len(rows),
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "input_summary": r.input_summary or "",
                "output_summary": r.output_summary or "",
                "tool_calls": r.tool_calls or [],
                "tokens_in": r.tokens_in or 0,
                "tokens_out": r.tokens_out or 0,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }