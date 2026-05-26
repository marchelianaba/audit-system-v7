"""Tools BUKTI DUKUNG — retrieval cuplikan bukti tanpa baca seluruh PDF.

Dipakai terutama untuk evaluasi ber-LKE (SAKIP/SPIP) yang punya banyak dokumen
bukti. Agen mencari cuplikan relevan per unsur/kriteria (deterministik, nol token)
alih-alih membaca seluruh PDF tiap kriteria.
"""
import json
from pathlib import Path

from claude_agent_sdk import tool

from app import bukti_index as bidx


@tool(
    "list_bukti",
    "Daftar dokumen bukti dukung yang diunggah ke penugasan (nama, path, jumlah "
    "halaman). Auto-index sekali (cache by sha256). Pakai untuk overview sebelum "
    "retrieval. Untuk skill ber-banyak-dokumen (evaluasi SAKIP/SPIP).",
    {"penugasan_folder": str},
)
async def list_bukti(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    summary = bidx.build_index(folder)  # idempotent (cache)
    docs = bidx.list_docs(folder)
    payload = {**summary, "dokumen": docs[:60]}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


@tool(
    "search_bukti",
    "Cari CUPLIKAN (snippet) paling relevan di seluruh dokumen bukti penugasan "
    "berdasarkan `query` (kata kunci unsur/kriteria). Return top-N {dokumen, halaman, "
    "snippet}. JAUH lebih hemat daripada read_pdf_page seluruh dokumen — pakai ini "
    "untuk menarik bukti per unsur LKE, lalu skor. Baca halaman penuh via read_pdf_page "
    "HANYA bila perlu verifikasi mendalam.",
    {"penugasan_folder": str, "query": str, "limit": int},
)
async def search_bukti(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    query = str(args.get("query", "")).strip()
    if not query:
        return {"content": [{"type": "text", "text": "FAILED|query kosong"}], "is_error": True}
    try:
        limit = int(args.get("limit", 6))
    except (TypeError, ValueError):
        limit = 6
    res = bidx.search(folder, query, limit=limit)
    return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]}


BUKTI_TOOLS = [list_bukti, search_bukti]
