"""Mapping bidireksional kode EWS legacy ↔ kriteria_id v7-native.

Dipakai untuk:
- Diff UI: pair EwsFinding vs CacmFinding agar bisa bandingkan status.
- Anti-duplikat promote: deteksi usulan terbuka dari satker yang sama
  baik via kode EWS atau kriteria_id v7.

Sumber kebenaran mapping ini = baris pertama description di YAML kriteria
yang menyebut "EWS-XX" eksplisit. Bila YAML baru tanpa pasangan EWS legacy
(mis. PBJ-TUPOKSI-MATCH / PBJ-UNITCOST-WAJAR — kelas baru di luar 9 EWS
asal), entri ada di V7_ONLY.

Pelihara mapping ini bila ada YAML baru yang merupakan port dari EWS lain.
"""
from __future__ import annotations

# 9 EWS legacy → kriteria_id v7-native (1:1, port di Fase 1 commit-1).
EWS_TO_V7: dict[str, str] = {
    "EWS-01": "PBJ-PL-BATAS-NILAI",
    "EWS-02": "PBJ-PJL-INDIKASI",
    "EWS-03": "PBJ-PDN-RASIO",
    "EWS-04": "PBJ-PEMILIHAN-Q4",
    "EWS-05": "PBJ-UKM-RASIO",
    "EWS-06": "PBJ-PAKET-BARU",
    "EWS-07": "PBJ-NON-KOMPETITIF",
    "EWS-08": "PBJ-PAGU-TREN",
    "EWS-09": "PBJ-SPLIT-INDIKASI",
}

# Reverse mapping — dibangun otomatis dari EWS_TO_V7.
V7_TO_EWS: dict[str, str] = {v: k for k, v in EWS_TO_V7.items()}

# Kriteria v7-native yang TIDAK punya pasangan EWS legacy.
# Catat di sini untuk transparansi (UI bisa tampilkan badge "v7-only" untuk
# kriteria ini, BUKAN tag "mismatch" yang menyesatkan).
V7_ONLY: set[str] = {
    "PBJ-TUPOKSI-MATCH",       # semantic_anomaly — kelas baru di luar EWS
    "PBJ-UNITCOST-WAJAR",      # benchmark_unitcost — kelas baru di luar EWS
}


def ews_kode_for_v7(kriteria_id: str) -> str | None:
    """v7 kriteria_id → kode EWS legacy. None bila v7-only."""
    return V7_TO_EWS.get(kriteria_id)


def v7_kriteria_for_ews(kode: str) -> str | None:
    """EWS kode → v7 kriteria_id. None bila EWS lawas tanpa port."""
    return EWS_TO_V7.get(kode)


def is_v7_only(kriteria_id: str) -> bool:
    """True bila kriteria_id ini tidak punya pasangan EWS legacy."""
    return kriteria_id in V7_ONLY or kriteria_id not in V7_TO_EWS
