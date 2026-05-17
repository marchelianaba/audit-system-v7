"""Routes orkestrasi agen + ingestion worker."""
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
    build_ingestion_agent,
    build_ketua_tim_agent,
    build_qc_saipi_agent,
)
from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models import AgentRun, Dokumen, DokumenStatus, Penugasan, PenugasanStatus, Role, User
from app.tools.v6_bridge import run_v6_script

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agen", tags=["agen"])

AGENT_BUILDERS = {
    "ingestion": build_ingestion_agent,
    "anggota_tim": build_anggota_tim_agent,
    "ketua_tim": build_ketua_tim_agent,
    "qc_saipi": build_qc_saipi_agent,
}


# ============================================================
# INGESTION WORKER (synchronous, inline)
# ============================================================

async def _run_ingestion(penugasan_id: int) -> None:
    """Jalankan digest deterministic V6 untuk semua dokumen di penugasan."""
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

        for i, d in enumerate(tor_docs, start=1):
            out = ingested_dir / f"tor-{i:02d}.json"
            code, _, err = await run_v6_script(
                "scripts/reviu-rka-kl/digest_tor.py",
                [d.file_path, "--no-raw", "-o", str(out)],
                timeout=120,
            )
            if code == 0 and out.exists():
                d.status = DokumenStatus.READY
                d.ingested_json_path = str(out)
                d.ingested_at = datetime.utcnow()
            else:
                d.status = DokumenStatus.FAILED
                d.error_message = (err or "digest_tor returned non-zero")[:500]

        for i, d in enumerate(rab_docs, start=1):
            out = ingested_dir / f"rab-{i:02d}.json"
            code, _, err = await run_v6_script(
                "scripts/reviu-rka-kl/digest_rab.py",
                [d.file_path, "-o", str(out)],
                timeout=120,
            )
            if code == 0 and out.exists():
                d.status = DokumenStatus.READY
                d.ingested_json_path = str(out)
                d.ingested_at = datetime.utcnow()
            else:
                d.status = DokumenStatus.FAILED
                d.error_message = (err or "digest_rab returned non-zero")[:500]

        if pbj_docs:
            out = ingested_dir / "pengadaan-digest.json"
            code, _, err = await run_v6_script(
                "scripts/audit-pengadaan/digest_pengadaan.py",
                [str(folder), "-o", str(out)],
                timeout=180,
            )
            success = code == 0 and out.exists()
            for d in pbj_docs:
                if success:
                    d.status = DokumenStatus.READY
                    d.ingested_json_path = str(out)
                    d.ingested_at = datetime.utcnow()
                else:
                    d.status = DokumenStatus.FAILED
                    d.error_message = (err or "digest_pengadaan returned non-zero")[:500]

        for d in other_docs:
            d.status = DokumenStatus.READY
            d.ingested_at = datetime.utcnow()

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

    docs = (
        await db.execute(
            select(Dokumen).where(
                Dokumen.penugasan_id == p.id,
                Dokumen.status != DokumenStatus.READY,
            )
        )
    ).scalars().all()
    for d in docs:
        d.status = DokumenStatus.INGESTING
    p.status = PenugasanStatus.INGESTING
    await db.commit()

    await _run_ingestion(p.id)

    updated = (
        await db.execute(select(Dokumen).where(Dokumen.penugasan_id == p.id))
    ).scalars().all()
    return {
        "penugasan_id": p.id,
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
# AGENT STREAM (SSE)
# ============================================================

async def _stream_agent(agent_name: str, user_prompt: str, penugasan_id: int, user_id: int):
    options = AGENT_BUILDERS[agent_name]()

    async with SessionLocal() as db:
        run = AgentRun(
            penugasan_id=penugasan_id,
            agent_name=agent_name,
            user_id=user_id,
            status="running",
            input_summary=user_prompt[:500],
            started_at=datetime.utcnow(),
            tool_calls=[],
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()

    yield {"event": "start", "data": json.dumps({"agent": agent_name, "run_id": run_id})}

    output_parts: list[str] = []
    tool_calls: list[dict] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_prompt)
            async for message in client.receive_response():
                content = getattr(message, "content", None) or []
                for block in content:
                    btype = type(block).__name__
                    if btype == "TextBlock":
                        text = getattr(block, "text", "")
                        output_parts.append(text)
                        yield {"event": "text", "data": json.dumps({"text": text})}
                    elif btype == "ToolUseBlock":
                        name = getattr(block, "name", "?")
                        inp = getattr(block, "input", {})
                        tool_calls.append({"tool": name, "input": inp})
                        yield {"event": "tool_use", "data": json.dumps({"tool": name, "input": inp})}
                    elif btype == "ToolResultBlock":
                        result = getattr(block, "content", "")
                        if isinstance(result, list) and result:
                            result_text = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
                        else:
                            result_text = str(result)[:500]
                        yield {"event": "tool_result", "data": json.dumps({"result": result_text[:500]})}
    except Exception as e:
        log.exception("Agent run failed: %s", e)
        async with SessionLocal() as db:
            row = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            row.status = "failed"
            row.error_message = str(e)[:1000]
            row.ended_at = datetime.utcnow()
            await db.commit()
        yield {"event": "error", "data": json.dumps({"message": str(e)[:500]})}
        return

    async with SessionLocal() as db:
        row = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        row.status = "completed"
        row.output_summary = "".join(output_parts)[:2000]
        row.tool_calls = tool_calls
        row.ended_at = datetime.utcnow()
        await db.commit()

    yield {"event": "done", "data": json.dumps({"run_id": run_id})}


@router.get("/{agent_name}/stream")
async def stream_agent(
    agent_name: str,
    penugasan_id: int,
    prompt: str,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user, role = current
    if agent_name not in AGENT_BUILDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agen tidak dikenal: {agent_name}")
    if agent_name == "anggota_tim" and role != Role.AT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Anggota Tim")
    if agent_name == "ketua_tim" and role not in (Role.KT, Role.PT, Role.PM):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Ketua Tim/PT/PM")

    p = (await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")

    skill_str = p.skill if isinstance(p.skill, str) else p.skill.value
    full_prompt = (
        f"Penugasan kode={p.kode}, skill={skill_str}, folder={p.folder_path}\n"
        f"Pengguna: {user.nama_lengkap} ({role.value})\n\n"
        f"Permintaan: {prompt}"
    )
    return EventSourceResponse(_stream_agent(agent_name, full_prompt, p.id, user.id))

@router.post("/{agent_name}/run")
async def run_agent(
    agent_name: str,
    payload: dict,  # body: {"penugasan_id": int, "prompt": str}
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Jalankan agen synchronous, return hasil lengkap sebagai JSON."""
    user, role = current

    if agent_name not in AGENT_BUILDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agen tidak dikenal: {agent_name}")
    if agent_name == "anggota_tim" and role != Role.AT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Anggota Tim")
    if agent_name == "ketua_tim" and role not in (Role.KT, Role.PT, Role.PM):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Ketua Tim/PT/PM")

    penugasan_id = int(payload.get("penugasan_id"))
    prompt = str(payload.get("prompt", ""))

    p = (await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")

    skill_str = p.skill if isinstance(p.skill, str) else p.skill.value
    full_prompt = (
        f"Penugasan kode={p.kode}, skill={skill_str}, folder={p.folder_path}\n"
        f"Pengguna: {user.nama_lengkap} ({role.value})\n\n"
        f"Permintaan: {prompt}"
    )

    options = AGENT_BUILDERS[agent_name]()
    output_parts: list[str] = []
    tool_calls: list[dict] = []
    error_msg: str | None = None

    run = AgentRun(
        penugasan_id=penugasan_id,
        agent_name=agent_name,
        user_id=user.id,
        status="running",
        input_summary=full_prompt[:500],
        started_at=datetime.utcnow(),
        tool_calls=[],
    )
    db.add(run)
    await db.commit()

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(full_prompt)
            async for message in client.receive_response():
                content = getattr(message, "content", None) or []
                for block in content:
                    btype = type(block).__name__
                    if btype == "TextBlock":
                        output_parts.append(getattr(block, "text", ""))
                    elif btype == "ToolUseBlock":
                        tool_calls.append({
                            "tool": getattr(block, "name", "?"),
                            "input": getattr(block, "input", {}),
                        })
    except Exception as e:
        log.exception("Agent run failed")
        error_msg = str(e)[:1000]

    run.status = "failed" if error_msg else "completed"
    run.output_summary = "".join(output_parts)[:2000]
    run.tool_calls = tool_calls
    run.error_message = error_msg
    run.ended_at = datetime.utcnow()
    await db.commit()

    return {
        "run_id": run.id,
        "status": run.status,
        "output": "".join(output_parts),
        "tool_calls": tool_calls,
        "error": error_msg,
    }