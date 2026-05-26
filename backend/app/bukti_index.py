"""Indeks & retrieval BUKTI DUKUNG (deterministik, tanpa token LLM).

Untuk evaluasi ber-LKE (SAKIP/SPIP) auditee mengunggah BANYAK dokumen bukti.
Membaca semua PDF × halaman ke konteks LLM untuk tiap kriteria = boros & lambat.
Modul ini:
  1. Ekstrak teks tiap PDF SEKALI (pdfplumber), cache per-penugasan di
     `_BUKTI/index.json`, di-key sha256 → file sama tak di-extract ulang.
  2. Retrieval LEKSIKAL (keyword overlap) → kembalikan CUPLIKAN (snippet) paling
     relevan per query, bukan seluruh dokumen. Nol panggilan API.

Agen memakai ini (lewat bukti_tools.search_bukti) untuk menarik bukti relevan per
unsur LKE, lalu skor satu unsur sekaligus.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.storage import sha256_bytes

INDEX_DIR = "_BUKTI"
INDEX_FILE = "index.json"
_PAGE_TEXT_CAP = 6000      # batasi teks/halaman tersimpan di index
_SNIPPET_WIN = 320         # lebar snippet di sekitar hit

# Folder output/sistem yang BUKAN bukti dukung.
_SKIP_PARTS = {"_KKP", "_LHP", "_QA-SAIPI", "_INGESTED", "_BUKTI", "_PKP"}

_STOPWORD = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "atau", "adalah", "pada",
    "oleh", "dalam", "sebagai", "tidak", "ini", "itu", "juga", "dapat", "telah",
    "akan", "sudah", "ada", "atas", "agar", "para", "the", "of", "and",
}


def _index_path(folder: Path) -> Path:
    return folder / INDEX_DIR / INDEX_FILE


def _iter_bukti_pdfs(folder: Path):
    for p in sorted(folder.rglob("*.pdf")):
        rel = p.relative_to(folder)
        if any(part in _SKIP_PARTS for part in rel.parts):
            continue
        yield p


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", str(text).lower()) if t not in _STOPWORD]


def _extract_pages(pdf_path: Path) -> list[dict]:
    from pdfplumber import open as open_pdf
    pages: list[dict] = []
    try:
        with open_pdf(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                txt = (page.extract_text() or "").strip()
                if txt:
                    pages.append({"page": i, "text": txt[:_PAGE_TEXT_CAP]})
    except Exception:  # noqa: BLE001 — PDF rusak/terenkripsi: lewati, jangan crash
        return []
    return pages


def build_index(folder: Path, force: bool = False) -> dict:
    """Bangun/refresh index bukti. Cache per-file by sha256 (skip extract bila sama).

    Return ringkasan {total_dokumen, total_halaman, diekstrak, dari_cache}.
    """
    folder = Path(folder)
    prev = load_index(folder) or {}
    cache: dict[str, dict] = {d.get("sha256", ""): d for d in prev.get("docs", [])}

    docs: list[dict] = []
    extracted = cached = 0
    for pdf in _iter_bukti_pdfs(folder):
        try:
            sha = sha256_bytes(pdf.read_bytes())
        except OSError:
            continue
        if not force and sha in cache and cache[sha].get("pages") is not None:
            d = dict(cache[sha])
            d["name"] = pdf.name
            d["path"] = str(pdf.relative_to(folder))
            cached += 1
        else:
            pages = _extract_pages(pdf)
            d = {"name": pdf.name, "path": str(pdf.relative_to(folder)),
                 "sha256": sha, "n_pages": len(pages), "pages": pages}
            extracted += 1
        docs.append(d)

    index = {"docs": docs, "total_dokumen": len(docs),
             "total_halaman": sum(d.get("n_pages", 0) for d in docs)}
    path = _index_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return {"total_dokumen": index["total_dokumen"], "total_halaman": index["total_halaman"],
            "diekstrak": extracted, "dari_cache": cached}


def load_index(folder: Path) -> dict | None:
    p = _index_path(Path(folder))
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_docs(folder: Path) -> list[dict]:
    idx = load_index(folder) or build_index(folder) and load_index(folder)
    idx = idx or {}
    return [{"name": d["name"], "path": d["path"], "n_pages": d.get("n_pages", 0)}
            for d in idx.get("docs", [])]


def _snippet(text: str, terms: list[str]) -> str:
    low = text.lower()
    pos = -1
    for t in terms:
        i = low.find(t)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    if pos == -1:
        return text[:_SNIPPET_WIN].strip()
    start = max(0, pos - _SNIPPET_WIN // 3)
    return text[start:start + _SNIPPET_WIN].strip()


def search(folder: Path, query: str, limit: int = 6) -> dict:
    """Retrieval leksikal: kembalikan top-N snippet halaman paling relevan dgn query."""
    folder = Path(folder)
    idx = load_index(folder)
    if idx is None:
        build_index(folder)
        idx = load_index(folder) or {"docs": []}
    terms = _tokenize(query)
    if not terms:
        return {"query": query, "total": 0, "hasil": [], "pesan": "query terlalu pendek"}

    scored: list[dict] = []
    for d in idx.get("docs", []):
        name_lc = d.get("name", "").lower()
        for pg in d.get("pages", []):
            text = pg.get("text", "")
            low = text.lower()
            score = sum(low.count(t) for t in terms) + sum(2 for t in terms if t in name_lc)
            if score <= 0:
                continue
            scored.append({"dokumen": d["name"], "path": d["path"], "halaman": pg["page"],
                           "score": score, "snippet": _snippet(text, terms)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"query": query, "total": len(scored), "hasil": scored[: max(1, min(limit, 20))]}
