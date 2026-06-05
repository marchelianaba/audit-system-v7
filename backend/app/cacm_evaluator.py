"""Evaluator engine + YAML registry untuk Mesin Kriteria CACM (Fase 1).

Tugas:
- Load semua `knowledge/cacm/kriteria/<id>.yaml` ke registry singleton.
- Validasi schema YAML lewat `cacm_schema.KriteriaModel`.
- Evaluasi 1 kriteria atas list observasi → return `EvaluasiHasil` dgn
  `status` (MERAH/KUNING/HIJAU/INFO), `value`, `value_display`, `narasi`,
  dan `evidence`.

Tidak menyentuh DB. Caller (routes/cacm.py) yg menulis CacmObservasi /
CacmFinding berdasarkan hasil eval.

V6 read-only — modul ini hanya di v7.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.cacm_dsl import (
    DSLError,
    eval_metric,
    eval_threshold,
    parse_metric_expression,
    parse_threshold_expression,
)
from app.cacm_schema import KriteriaModel, validate_kriteria_yaml
from app.config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# Hasil evaluasi
# ---------------------------------------------------------------------------

@dataclass
class EvaluasiHasil:
    """Output dari evaluate() — siap di-save ke CacmFinding (caller mapper)."""

    kriteria_id: str
    kriteria_revisi: str
    status: str                  # MERAH | KUNING | HIJAU | INFO
    value: Any                   # hasil metric (float / str / None)
    value_display: str           # diformat sesuai metric.format_display
    satuan: str | None
    narasi: str                  # narasi auto: judul + nilai + threshold match
    evidence: dict = field(default_factory=dict)
    threshold_matched: dict | None = None  # status + condition + catatan yang match
    error: str | None = None     # bila evaluasi gagal


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

@dataclass
class _RegistryEntry:
    """1 entry registry — model + AST hasil parse (di-cache supaya tidak re-parse tiap eval)."""

    model: KriteriaModel
    metric_ast: Any
    threshold_asts: list[tuple[str, Any, str | None]]  # [(status, ast, catatan), ...]
    file_path: Path


_REGISTRY: dict[str, _RegistryEntry] = {}
_LOAD_ERRORS: list[dict] = []  # [{file, errors[]}]


def _kriteria_root() -> Path:
    """Resolusi path folder kriteria dari config / fallback."""
    # Pakai APP_DATA_DIR root + ../knowledge atau project root + knowledge
    # Simpel: project root = settings.data_dir.parent.parent (mis. backend/data → project root)
    candidates: list[Path] = []
    try:
        candidates.append((settings.data_dir.parent.parent / "knowledge" / "cacm" / "kriteria"))
    except Exception:
        pass
    # Fallback ke project root relatif modul
    here = Path(__file__).resolve()
    candidates.append((here.parent.parent.parent / "knowledge" / "cacm" / "kriteria"))
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # may not exist; load_registry will skip gracefully


def load_registry(force_reload: bool = False) -> dict[str, _RegistryEntry]:
    """Load semua YAML di `knowledge/cacm/kriteria/*.yaml` ke registry singleton.

    Skip file yg validasi gagal (catat di _LOAD_ERRORS). Idempoten.
    """
    global _REGISTRY, _LOAD_ERRORS
    if _REGISTRY and not force_reload:
        return _REGISTRY
    _REGISTRY = {}
    _LOAD_ERRORS = []

    root = _kriteria_root()
    if not root.exists():
        return _REGISTRY

    for f in sorted(root.glob("*.yaml")):
        if f.name.lower() == "readme.md":
            continue
        try:
            raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _LOAD_ERRORS.append({"file": f.name, "errors": [f"yaml parse: {exc}"]})
            continue
        if not isinstance(raw, dict):
            _LOAD_ERRORS.append({"file": f.name, "errors": ["root harus dict, dapat lain"]})
            continue
        # Skip kelas 2 (semantic_anomaly) & kelas 3 (benchmark_unitcost) — Fase 1 hanya
        # menangani numeric_threshold. File tetap valid utk kelas 2/3 (skema berbeda),
        # tidak dianggap error.
        tipe = raw.get("tipe", "numeric_threshold")
        if tipe != "numeric_threshold":
            continue
        model, errs = validate_kriteria_yaml(raw)
        if errs or model is None:
            _LOAD_ERRORS.append({"file": f.name, "errors": errs})
            continue

        # Parse metric expression dulu — kalau invalid, skip
        try:
            metric_ast = parse_metric_expression(model.metric.expression)
        except DSLError as exc:
            _LOAD_ERRORS.append({"file": f.name, "errors": [f"metric DSL: {exc}"]})
            continue

        # Parse semua threshold expression
        threshold_asts: list[tuple[str, Any, str | None]] = []
        threshold_ok = True
        for t in model.thresholds:
            try:
                ast = parse_threshold_expression(t.condition)
                threshold_asts.append((t.status, ast, t.catatan))
            except DSLError as exc:
                _LOAD_ERRORS.append({
                    "file": f.name,
                    "errors": [f"threshold DSL ({t.status}): {exc}"],
                })
                threshold_ok = False
                break
        if not threshold_ok:
            continue

        _REGISTRY[model.id] = _RegistryEntry(
            model=model,
            metric_ast=metric_ast,
            threshold_asts=threshold_asts,
            file_path=f,
        )

    return _REGISTRY


def get_load_errors() -> list[dict]:
    """Daftar error yang ditemukan saat load YAML (untuk UI debug & log)."""
    return list(_LOAD_ERRORS)


def list_kriteria(dimensi: str | None = None) -> list[KriteriaModel]:
    """List semua kriteria yg sukses di-load (filter opsional by dimensi)."""
    load_registry()
    items = [e.model for e in _REGISTRY.values()]
    if dimensi:
        items = [m for m in items if m.dimensi == dimensi]
    return sorted(items, key=lambda m: m.id)


def get_kriteria(kriteria_id: str) -> KriteriaModel | None:
    load_registry()
    entry = _REGISTRY.get(kriteria_id)
    return entry.model if entry else None


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _format_value(model: KriteriaModel, value: Any) -> str:
    if value is None:
        return "—"
    fmt = model.metric.format_display
    if fmt:
        try:
            return fmt.format(value)
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _build_narasi(model: KriteriaModel, status: str, value_disp: str, catatan: str | None) -> str:
    """Auto-generate narasi untuk finding (siap masuk CacmFinding.narasi)."""
    pieces = [f"{model.id}: {model.nama}"]
    pieces.append(f"Metrik = {value_disp}")
    pieces.append(f"Status: {status}")
    if catatan:
        pieces.append(f"({catatan})")
    return ". ".join(pieces) + "."


def _select_evidence(model: KriteriaModel, rows: list[dict]) -> dict:
    """Ambil snapshot evidence_fields dari subset rows (cap 10 baris)."""
    if not model.evidence_fields:
        return {"sample_rows": min(len(rows), 10)}
    out: dict[str, list] = {f: [] for f in model.evidence_fields}
    for r in rows[:50]:
        for f in model.evidence_fields:
            # field path mis. "data.satker"
            path = f.split(".")
            cur: Any = r
            for k in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(k)
            out[f].append(cur)
    # Cap list lengths
    return {k: v[:10] for k, v in out.items()}


def evaluate(kriteria_id: str, rows: list[dict]) -> EvaluasiHasil:
    """Eval 1 kriteria atas list of observation rows (dict dgn key 'data').

    Setiap row punya format {"data": {<raw fields>}, ...} mengikuti
    `CacmObservasi.data` JSONB. Caller meneruskan rows dari DB query atau
    langsung dari payload ingestion.
    """
    load_registry()
    entry = _REGISTRY.get(kriteria_id)
    if not entry:
        return EvaluasiHasil(
            kriteria_id=kriteria_id,
            kriteria_revisi="?",
            status="INFO",
            value=None,
            value_display="—",
            satuan=None,
            narasi=f"Kriteria '{kriteria_id}' tidak terdaftar.",
            error=f"kriteria '{kriteria_id}' tidak ada di registry",
        )

    model = entry.model

    # Eval metric
    try:
        value = eval_metric(entry.metric_ast, rows)
    except DSLError as exc:
        return EvaluasiHasil(
            kriteria_id=model.id,
            kriteria_revisi=model.revisi,
            status="INFO",
            value=None,
            value_display="—",
            satuan=model.metric.satuan,
            narasi=f"{model.id}: Gagal eval metric — {exc}",
            error=str(exc),
        )

    value_display = _format_value(model, value)
    evidence = _select_evidence(model, rows)
    evidence["total_rows"] = len(rows)

    # Match threshold (top-to-bottom; status pertama yg TRUE menang)
    matched_status = "INFO"
    matched_catatan: str | None = None
    matched_condition: str | None = None
    for status, ast, catatan in entry.threshold_asts:
        try:
            if eval_threshold(ast, value):
                matched_status = status
                matched_catatan = catatan
                # Cari condition string asli
                for t in model.thresholds:
                    if t.status == status:
                        matched_condition = t.condition
                        break
                break
        except DSLError:
            continue

    narasi = _build_narasi(model, matched_status, value_display, matched_catatan)

    return EvaluasiHasil(
        kriteria_id=model.id,
        kriteria_revisi=model.revisi,
        status=matched_status,
        value=value if not isinstance(value, float) or value == value else None,  # NaN guard
        value_display=value_display,
        satuan=model.metric.satuan,
        narasi=narasi,
        evidence=evidence,
        threshold_matched=(
            {
                "status": matched_status,
                "condition": matched_condition,
                "catatan": matched_catatan,
            }
            if matched_status != "INFO"
            else None
        ),
    )


def evaluate_all_for_dimensi(dimensi: str, rows: list[dict]) -> list[EvaluasiHasil]:
    """Eval semua kriteria di dimensi tertentu atas 1 set observasi."""
    load_registry()
    results: list[EvaluasiHasil] = []
    for entry in _REGISTRY.values():
        if entry.model.dimensi == dimensi and entry.model.tipe == "numeric_threshold":
            results.append(evaluate(entry.model.id, rows))
    return results
