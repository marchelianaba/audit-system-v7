"""Pydantic schema untuk file YAML kriteria CACM.

Validasi at-load-time: tiap YAML di `knowledge/cacm/kriteria/<id>.yaml` di-parse
ke `KriteriaModel`; bila skema invalid, evaluator menolak load (fail-fast, lebih
baik dari runtime error saat eval).

Skema mengikuti dokumen rencana di `docs/rencana-cacm-kriteria.html` §3.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CacmStatus = Literal["MERAH", "KUNING", "HIJAU", "INFO"]
KriteriaTipe = Literal["numeric_threshold", "semantic_anomaly", "benchmark_unitcost"]
DimensiCacm = Literal[
    "PENGADAAN_RENCANA",   # SIRUP
    "PENGADAAN_REALISASI", # SPSE
    "ANGGARAN",            # DIPA / RKA
    "KINERJA",             # e-Performance / IKU / dst (TBD)
]
SumberData = Literal["sirup", "spse", "dipa", "kinerja_eperformance", "kinerja_integral", "kinerja_other"]


class PeriodeRelevansi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mulai_bulan: int = Field(default=1, ge=1, le=12)
    selesai_bulan: int = Field(default=12, ge=1, le=12)


class Threshold(BaseModel):
    """Satu baris di list thresholds."""

    model_config = ConfigDict(extra="forbid")

    status: CacmStatus
    condition: str = Field(
        ...,
        min_length=1,
        description="Expression numeric comparison string (mis. '>=60', '<40 AND >=20').",
    )
    catatan: str | None = None


class Metric(BaseModel):
    """Definisi metric DSL — di-eval atas list observasi."""

    model_config = ConfigDict(extra="forbid")

    expression: str = Field(
        ...,
        min_length=1,
        description="DSL expression: sum/avg/count/ratio/max/min/delta atas field data.*",
    )
    satuan: str | None = None
    format_display: str | None = Field(
        default=None,
        description="Python format string utk display, mis. '{:.1f}%' atau 'Rp {:,.0f}'.",
    )
    catatan_evaluator: str | None = None


class Promote(BaseModel):
    """Konfigurasi promote finding ke Penugasan (USULAN_CACM)."""

    model_config = ConfigDict(extra="forbid")

    skill: str = "reviu-pengadaan"
    pattern_ids_hint: list[str] = Field(default_factory=list)
    prefilled_obyek_tpl: str | None = None
    prefilled_dasar_permintaan: str | None = None


class KriteriaModel(BaseModel):
    """Skema utama 1 file YAML kriteria CACM."""

    model_config = ConfigDict(extra="allow")  # allow extra utk mode_* (semantic_anomaly)

    id: str = Field(..., min_length=1, pattern=r"^[A-Z]+(-[A-Z0-9]+)+$")
    revisi: str = Field(..., min_length=1)
    nama: str = Field(..., min_length=1)
    catatan_revisi: str | None = None

    tipe: KriteriaTipe = "numeric_threshold"
    dimensi: DimensiCacm
    sumber_data: SumberData

    satker_terapkan: list[str] = Field(default_factory=lambda: ["ALL"])
    periode_relevansi: PeriodeRelevansi | None = None

    regulasi: list[str] = Field(default_factory=list)

    metric: Metric
    thresholds: list[Threshold] = Field(..., min_length=2)

    evidence_fields: list[str] = Field(default_factory=list)
    promote: Promote | None = None

    catatan_implementasi: str | None = None

    def has_status(self, status: CacmStatus) -> bool:
        return any(t.status == status for t in self.thresholds)


def validate_kriteria_yaml(raw: dict) -> tuple[KriteriaModel | None, list[str]]:
    """Validate dict yang sudah di-parse dari YAML.

    Return (model, errors). `model is None` bila ada error.
    """
    errors: list[str] = []
    try:
        m = KriteriaModel.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        return None, [str(exc)[:500]]

    # Aturan tambahan: minimal punya 1 status MERAH ATAU 1 HIJAU
    if not (m.has_status("MERAH") or m.has_status("HIJAU")):
        errors.append(
            "thresholds harus punya minimal 1 entry MERAH atau HIJAU agar bisa membedakan."
        )

    # Cek duplikat status
    seen: set[str] = set()
    for t in m.thresholds:
        if t.status in seen:
            errors.append(f"status '{t.status}' duplikat di thresholds — tiap status maksimal 1x.")
        seen.add(t.status)

    return (None if errors else m, errors)
