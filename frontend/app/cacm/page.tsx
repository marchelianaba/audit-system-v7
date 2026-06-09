'use client';

// Halaman CACM — C1a: ingest hasil EWS SIRUP (dari agent tim) + usulan penugasan.
// Webhook/pull live (C1b) menyusul. Sumber data = sample fixture untuk demo.

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, clearToken, getSession, Session } from '@/lib/api';
import { AppShell } from '@/components/AppShell';

type Run = Awaited<ReturnType<typeof api.getCacmRun>>;
type Finding = Run['findings'][number];

const STATUS_CLS: Record<string, string> = {
  MERAH: 'bg-red-100 text-red-800 border-red-300',
  KUNING: 'bg-amber-100 text-amber-800 border-amber-300',
  HIJAU: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  INFO: 'bg-blue-100 text-blue-800 border-blue-300',
};

function rupiah(n: number): string {
  return 'Rp ' + (n || 0).toLocaleString('id-ID');
}

export default function CacmPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [session, setSession] = useState<Session | null>(null);

  const [runsMeta, setRunsMeta] = useState<Awaited<ReturnType<typeof api.getCacmRuns>>['runs']>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const isPT = session?.role_aktif === 'PT';

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getCacmRuns();
      setRunsMeta(res.runs);
      if (res.runs.length > 0) {
        const detail = await api.getCacmRun(res.runs[0].id);
        setRun(detail);
      } else {
        setRun(null);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSession(s);
    if (!s) {
      router.push('/login');
      return;
    }
    loadRuns();
  }, [router, loadRuns]);

  const handleLogout = () => {
    clearToken();
    router.push('/login');
  };

  const selectRun = async (id: number) => {
    setBusy('run');
    try {
      setRun(await api.getCacmRun(id));
      setExpanded(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const ingestSample = async () => {
    setBusy('ingest');
    try {
      await api.ingestCacmSample();
      await loadRuns();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const syncAgent = async () => {
    setBusy('sync');
    setError(null);
    try {
      await api.syncCacm();
      await loadRuns();
    } catch (e: any) {
      // 503 = agent belum dikonfigurasi (pesan jelas dari backend)
      setError(e.message?.includes('503') ? 'Agent EWS belum dikonfigurasi (set CACM_AGENT_BASE_URL + CACM_AGENT_API_KEY di .env backend).' : e.message);
    } finally {
      setBusy(null);
    }
  };

  const promote = async (f: Finding) => {
    if (!confirm(`Jadikan finding ${f.kode} (${f.satker}) sebagai usulan penugasan?`)) return;
    setBusy(`promote-${f.id}`);
    try {
      await api.promoteFinding(f.id);
      if (run) setRun(await api.getCacmRun(run.id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async (f: Finding) => {
    setBusy(`dismiss-${f.id}`);
    try {
      await api.dismissFinding(f.id);
      if (run) setRun(await api.getCacmRun(run.id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  if (!mounted) return <main className="min-h-screen" />;
  if (!session) return null;

  const s = run?.summary || {};

  return (
    <AppShell>

      <div className="max-w-6xl mx-auto p-6">
        <div className="flex justify-between items-start mb-1">
          <h1 className="text-2xl font-bold text-primary-dark">CACM — Early Warning System SIRUP</h1>
          {isPT && (
            <div className="flex gap-2">
              <button
                onClick={syncAgent}
                disabled={busy === 'sync'}
                className="px-3 py-2 text-sm rounded border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 disabled:opacity-50"
                title="Pull run terbaru dari agent EWS tim (butuh agent ter-deploy + CACM_AGENT_* di .env)"
              >
                {busy === 'sync' ? 'Sinkron…' : '⟳ Sync dari agent'}
              </button>
              <button
                onClick={ingestSample}
                disabled={busy === 'ingest'}
                className="px-3 py-2 text-sm rounded bg-primary text-white font-semibold hover:bg-primary-dark disabled:opacity-50"
              >
                {busy === 'ingest' ? 'Memuat…' : '＋ Muat contoh EWS'}
              </button>
            </div>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Hasil evaluasi 9 skenario EWS atas data SIRUP (RUP/perencanaan). Finding MERAH/KUNING dapat
          dijadikan usulan penugasan reviu pengadaan. <span className="text-gray-400">C1a: ingest dari
          file/sample; webhook &amp; pull otomatis (C1b) menyusul.</span>
        </p>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
        )}

        {loading ? (
          <div className="text-gray-500 text-sm">Memuat…</div>
        ) : !run ? (
          <div className="bg-white border border-dashed border-gray-300 rounded-lg p-10 text-center text-gray-500">
            Belum ada data EWS.{' '}
            {isPT ? 'Klik "Muat contoh EWS" untuk mengisi dengan data sample.' : 'Tunggu PT mengisi data EWS.'}
          </div>
        ) : (
          <>
            {/* Run selector + summary */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
              {runsMeta.length > 1 && (
                <select
                  value={run.id}
                  onChange={(e) => selectRun(Number(e.target.value))}
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm"
                >
                  {runsMeta.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.run_id} ({r.tanggal_evaluasi || r.received_at?.slice(0, 10)})
                    </option>
                  ))}
                </select>
              )}
              <span className="text-xs px-2 py-1 rounded bg-gray-100">Total {s.total ?? 0}</span>
              <span className="text-xs px-2 py-1 rounded bg-red-100 text-red-800">🔴 {s.merah ?? 0} Merah</span>
              <span className="text-xs px-2 py-1 rounded bg-amber-100 text-amber-800">🟡 {s.kuning ?? 0} Kuning</span>
              <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-800">ℹ️ {s.info ?? 0} Info</span>
              <span className="text-[11px] px-2 py-1 rounded bg-slate-100 text-slate-600" title="Sumber data run">
                {run.source === 'webhook' ? '📡 webhook' : run.source === 'pull' ? '⟳ pull agent' : '📄 offline'}
              </span>
              <span className="text-[11px] text-gray-400">run: {run.run_id}</span>
            </div>

            {/* Rekap per satker */}
            {run.rekap.length > 0 && (
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden mb-5">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left p-2.5 text-xs uppercase text-gray-600">Satker</th>
                      <th className="text-right p-2.5 text-xs uppercase text-gray-600">Paket Penyedia</th>
                      <th className="text-right p-2.5 text-xs uppercase text-gray-600">Pagu Penyedia (juta)</th>
                      <th className="text-right p-2.5 text-xs uppercase text-gray-600">Total Pagu (juta)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.rekap.map((rk, i) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="p-2.5">{rk.satker}</td>
                        <td className="p-2.5 text-right">{rk.penyedia_paket}</td>
                        <td className="p-2.5 text-right">{(rk.penyedia_pagu_juta || 0).toLocaleString('id-ID')}</td>
                        <td className="p-2.5 text-right font-medium">{(rk.total_pagu_juta || 0).toLocaleString('id-ID')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Diff EWS legacy vs v7-native — validasi cut-over */}
            <DiffSection runId={run.id} />

            {/* V7-native findings (paralel CACM Fase 1 evaluator) */}
            <V7NativeFindingsSection runId={run.id} />

            {/* Findings */}
            <h2 className="text-lg font-bold text-primary-dark mb-2">Temuan EWS legacy ({run.findings.length})</h2>
            <div className="space-y-2">
              {run.findings.map((f) => (
                <div key={f.id} className="bg-white border border-gray-200 rounded-lg">
                  <div className="flex items-start gap-3 p-3">
                    <span className={`shrink-0 px-2 py-0.5 text-xs rounded border ${STATUS_CLS[f.status] || 'bg-gray-100'}`}>
                      {f.status}
                    </span>
                    <span className="shrink-0 text-xs font-mono text-gray-500 mt-0.5">{f.kode}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-800">
                        {f.judul || f.ringkasan || f.kode}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {f.satker}
                        {f.nilai_aktual ? ` · ${f.nilai_aktual}` : ''}
                      </div>
                      {f.tindak_lanjut === 'DIPROMOSIKAN' && f.penugasan_id && (
                        <Link href={`/penugasan/${f.penugasan_id}`} className="text-xs text-emerald-700 hover:underline">
                          ✓ Jadi penugasan #{f.penugasan_id} →
                        </Link>
                      )}
                      {f.tindak_lanjut === 'DIABAIKAN' && (
                        <span className="text-xs text-gray-400">✕ Diabaikan</span>
                      )}
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      <button
                        onClick={() => setExpanded(expanded === f.id ? null : f.id)}
                        className="text-xs text-gray-500 hover:text-gray-700"
                      >
                        {expanded === f.id ? 'Tutup' : 'Detail'}
                      </button>
                      {isPT && f.promotable && f.tindak_lanjut === 'BARU' && (
                        <>
                          <button
                            onClick={() => promote(f)}
                            disabled={busy === `promote-${f.id}`}
                            className="text-xs px-2 py-1 rounded bg-primary text-white hover:bg-primary-dark disabled:opacity-50"
                          >
                            {busy === `promote-${f.id}` ? '…' : 'Jadikan usulan'}
                          </button>
                          <button
                            onClick={() => dismiss(f)}
                            disabled={busy === `dismiss-${f.id}`}
                            className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                          >
                            Abaikan
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {expanded === f.id && (
                    <div className="border-t border-gray-100 p-3 text-sm text-gray-700 space-y-2 bg-gray-50">
                      {/* Narasi: MERAH punya `penjelasan`; KUNING/INFO pakai `ringkasan`. */}
                      {(f.penjelasan || f.ringkasan) && (
                        <p className="whitespace-pre-wrap">{f.penjelasan || f.ringkasan}</p>
                      )}
                      <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-xs">
                        {f.nilai_aktual && <div className="sm:col-span-2"><span className="text-gray-400">Nilai aktual:</span> {f.nilai_aktual}</div>}
                        {f.threshold && <div><span className="text-gray-400">Threshold:</span> {f.threshold}</div>}
                        {(f.jumlah_paket_terdampak > 0 || f.total_nilai_terdampak > 0) && (
                          <div>
                            <span className="text-gray-400">Paket terdampak:</span> {f.jumlah_paket_terdampak}
                            {f.total_nilai_terdampak > 0 ? ` · ${rupiah(f.total_nilai_terdampak)}` : ''}
                          </div>
                        )}
                        {f.regulasi && <div className="sm:col-span-2"><span className="text-gray-400">Regulasi:</span> {f.regulasi}</div>}
                        {f.rekomendasi && <div className="sm:col-span-2"><span className="text-gray-400">Rekomendasi EWS:</span> {f.rekomendasi}</div>}
                      </div>
                      {f.paket_detail.length > 0 && (
                        <div className="mt-1">
                          <div className="text-xs text-gray-400 mb-1">Paket terdampak ({f.paket_detail.length}):</div>
                          <div className="space-y-0.5">
                            {f.paket_detail.slice(0, 15).map((p, i) => (
                              <div key={i} className="text-xs font-mono bg-white border border-gray-200 rounded px-2 py-1">
                                {p.nama || p.nama_paket} — {rupiah(p.pagu)} ({p.metode}, {p.jenis})
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

// =============================================================================
// V7NativeFindingsSection — finding hasil evaluator v7-native paralel dgn
// EwsFinding legacy. Tombol "Re-evaluate" (PT/PM) ulang run dgn YAML terbaru.
// =============================================================================

type V7Finding = Awaited<ReturnType<typeof api.getCacmV7Findings>>['findings'][number];

const CACM_STATUS_CLS_V7: Record<string, string> = {
  MERAH: 'bg-red-100 text-red-800 border-red-300',
  KUNING: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  HIJAU: 'bg-green-100 text-green-800 border-green-300',
  INFO: 'bg-gray-100 text-gray-600 border-gray-300',
};

function V7NativeFindingsSection({ runId }: { runId: number }) {
  const session = getSession();
  const canReEval = session?.role_aktif === 'PT' || session?.role_aktif === 'PM';
  const canPromote = session?.role_aktif === 'PT';
  const [findings, setFindings] = useState<V7Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [promotingId, setPromotingId] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.getCacmV7Findings(runId);
      setFindings(r.findings);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [runId]);

  const doPromote = async (f: V7Finding) => {
    if (!canPromote) return;
    if (f.tindak_lanjut === 'DIPROMOSIKAN') {
      setMsg(`Finding ${f.kriteria_id} sudah dipromosikan jadi penugasan #${f.penugasan_id}.`);
      return;
    }
    if (!['MERAH', 'KUNING'].includes(f.status.toUpperCase())) {
      setMsg(`Status ${f.status} tidak bisa dipromosikan (hanya MERAH/KUNING).`);
      return;
    }
    if (!confirm(`Promosikan finding ${f.kriteria_id} (${f.satker_nama}) jadi penugasan USULAN_CACM?`)) return;
    setPromotingId(f.id); setMsg(null);
    try {
      const r = await api.promoteCacmFinding(f.id);
      setMsg(`✓ Dipromosikan ke penugasan ${r.penugasan_kode} (#${r.penugasan_id}).`);
      refresh();
    } catch (e: any) {
      setMsg(`Gagal promote: ${e.message}`);
    } finally {
      setPromotingId(null);
    }
  };

  const doReEval = async () => {
    if (!canReEval) return;
    if (!confirm(`Re-evaluate run #${runId} dgn kriteria YAML terbaru? CacmFinding & CacmObservasi run ini akan dihapus & dibangun ulang. EwsFinding legacy tidak terpengaruh.`)) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.reEvaluateCacmRun(runId);
      setMsg(`Re-evaluate: ${r.removed_findings_old} finding lama dihapus, ${r.new_findings} finding baru dibuat.`);
      refresh();
    } catch (e: any) { setMsg(`Gagal: ${e.message}`); }
    finally { setBusy(false); }
  };

  if (loading) return (
    <div className="mb-4 p-3 text-xs text-gray-400 italic border border-amber-100 rounded">Memuat v7-native findings…</div>
  );
  if (findings.length === 0) return (
    <div className="mb-4 p-3 text-xs text-gray-500 border border-amber-200 bg-amber-50/30 rounded">
      Belum ada finding v7-native untuk run ini. Bisa terjadi bila ingest sebelum Fase 1 commit-2 rilis, atau evaluator gagal (cek log backend).
      {canReEval && (
        <button onClick={doReEval} disabled={busy} className="ml-3 text-xs px-2 py-0.5 rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50">
          {busy ? 'Re-evaluate…' : 'Re-evaluate sekarang'}
        </button>
      )}
    </div>
  );

  // Group by satker_nama
  const bySatker: Record<string, V7Finding[]> = {};
  for (const f of findings) {
    bySatker[f.satker_nama] = bySatker[f.satker_nama] || [];
    bySatker[f.satker_nama].push(f);
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold text-primary-dark">
          Finding CACM v7-native ({findings.length})
          <span className="text-[11px] font-normal text-gray-500 ml-2">
            evaluator atas kriteria YAML — paralel dgn EWS legacy
          </span>
        </h2>
        {canReEval && (
          <button onClick={doReEval} disabled={busy} className="text-xs px-3 py-1 rounded border border-amber-500 text-amber-700 hover:bg-amber-600 hover:text-white disabled:opacity-50">
            {busy ? 'Re-evaluate…' : '↻ Re-evaluate run'}
          </button>
        )}
      </div>
      {msg && <div className="mb-2 p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-xs">{msg}</div>}

      <div className="space-y-3">
        {Object.entries(bySatker).map(([satker, items]) => (
          <div key={satker} className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="text-sm font-semibold text-gray-800 mb-2">{satker}</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="py-1.5 pr-2">Kriteria</th>
                  <th className="py-1.5 px-2">Status</th>
                  <th className="py-1.5 px-2">Metric</th>
                  <th className="py-1.5 px-2">Narasi</th>
                  <th className="py-1.5 pl-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {items.map((f) => {
                  const promotable = ['MERAH', 'KUNING'].includes(f.status.toUpperCase());
                  const alreadyPromoted = f.tindak_lanjut === 'DIPROMOSIKAN';
                  return (
                    <tr key={f.id} className="border-b border-gray-100 last:border-0">
                      <td className="py-1.5 pr-2 font-mono text-gray-500">{f.kriteria_id}</td>
                      <td className="py-1.5 px-2">
                        <span className={`px-1.5 py-0.5 rounded border text-[10px] ${CACM_STATUS_CLS_V7[f.status] || 'bg-gray-100'}`}>
                          {f.status}
                        </span>
                      </td>
                      <td className="py-1.5 px-2 text-gray-700">{f.metric_display || '—'}</td>
                      <td className="py-1.5 px-2 text-gray-500 text-[11px]">{f.narasi}</td>
                      <td className="py-1.5 pl-2 text-right">
                        {alreadyPromoted ? (
                          <span className="text-[10px] text-gray-400 italic">→ #{f.penugasan_id}</span>
                        ) : canPromote && promotable ? (
                          <button
                            onClick={() => doPromote(f)}
                            disabled={promotingId !== null}
                            className="text-[10px] px-2 py-0.5 rounded border border-amber-400 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                            title="Promosikan jadi penugasan USULAN_CACM"
                          >
                            {promotingId === f.id ? '…' : '↗ Promote'}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// DiffSection — bandingkan EWS legacy vs v7-native per (satker, kriteria).
// Tujuan: validasi cut-over sebelum auto-promote v7-native dinyalakan.
// =============================================================================

type DiffData = Awaited<ReturnType<typeof api.getCacmDiff>>;

const STATUS_BADGE: Record<string, string> = {
  MERAH: 'bg-red-100 text-red-800 border-red-300',
  KUNING: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  HIJAU: 'bg-green-100 text-green-800 border-green-300',
  INFO: 'bg-gray-100 text-gray-600 border-gray-300',
};

function DiffSection({ runId }: { runId: number }) {
  const [data, setData] = useState<DiffData | null>(null);
  const [loading, setLoading] = useState(true);
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getCacmDiff(runId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return <div className="mb-4 p-3 text-xs text-gray-400 italic border border-purple-100 rounded">Memuat diff EWS vs v7-native…</div>;
  }
  if (!data || (data.summary.n_ews_total === 0 && data.summary.n_v7_total === 0)) {
    return null; // hide bila tidak ada data
  }

  const s = data.summary;
  const matchPct = s.n_matched_pairs > 0 ? Math.round((s.n_match_status / s.n_matched_pairs) * 100) : 0;
  const matchedShow = mismatchOnly
    ? data.matched.filter((m) => !m.is_match)
    : data.matched;

  // Health badge: hijau ≥90% match, kuning 60-89%, merah <60%.
  const healthColor =
    matchPct >= 90 ? 'bg-green-100 text-green-800 border-green-300' :
    matchPct >= 60 ? 'bg-yellow-100 text-yellow-800 border-yellow-300' :
    'bg-red-100 text-red-800 border-red-300';

  return (
    <div className="mb-4 bg-white border border-purple-200 rounded-lg p-4">
      <div className="flex justify-between items-start gap-2 flex-wrap mb-2">
        <div>
          <h3 className="font-semibold text-primary-dark">
            ⚖ Diff EWS legacy vs v7-native
            <span className={`ml-2 text-[11px] font-normal px-1.5 py-0.5 rounded border ${healthColor}`}>
              {matchPct}% match
            </span>
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Validasi sebelum cut-over. Pair (satker, kriteria) dibandingkan via mapping <code>EWS_TO_V7</code>.
          </p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
        >
          {expanded ? 'Ringkas' : 'Detail'}
        </button>
      </div>

      {/* Summary counter */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
        <div className="border rounded p-2 bg-gray-50">
          <div className="text-gray-500">Pair total</div>
          <div className="text-base font-semibold">{s.n_matched_pairs}</div>
          <div className="text-[10px] text-gray-400">EWS:{s.n_ews_total} · v7:{s.n_v7_total}</div>
        </div>
        <div className="border rounded p-2 bg-green-50">
          <div className="text-gray-500">Status match</div>
          <div className="text-base font-semibold text-green-700">{s.n_match_status}</div>
        </div>
        <div className="border rounded p-2 bg-red-50">
          <div className="text-gray-500">Mismatch</div>
          <div className="text-base font-semibold text-red-700">{s.n_mismatch}</div>
        </div>
        <div className="border rounded p-2 bg-amber-50">
          <div className="text-gray-500">v7-only / ews-only</div>
          <div className="text-base font-semibold text-amber-700">{s.n_v7_only} / {s.n_ews_only}</div>
        </div>
      </div>

      {expanded && (
        <>
          {/* Filter toggle */}
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={mismatchOnly}
                onChange={(e) => setMismatchOnly(e.target.checked)}
                className="cursor-pointer"
              />
              <span className="text-gray-700">Tampilkan hanya MISMATCH</span>
            </label>
            <span className="text-[10px] text-gray-400">
              ({matchedShow.length} dari {data.matched.length} pair)
            </span>
          </div>

          {/* Matched table */}
          {matchedShow.length > 0 && (
            <div className="overflow-x-auto mb-3">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-200">
                    <th className="py-1.5 pr-2">Satker</th>
                    <th className="py-1.5 pr-2 font-mono text-[10px]">EWS / v7</th>
                    <th className="py-1.5 px-2">EWS status</th>
                    <th className="py-1.5 px-2">v7 status</th>
                    <th className="py-1.5 pl-2">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {matchedShow.map((m, i) => (
                    <tr key={i} className={`border-b border-gray-100 last:border-0 ${!m.is_match ? 'bg-red-50/40' : ''}`}>
                      <td className="py-1.5 pr-2 text-gray-600">{m.satker_nama}</td>
                      <td className="py-1.5 pr-2 font-mono text-[10px] text-gray-500">
                        {m.ews_kode}<br/>{m.v7_kriteria_id}
                      </td>
                      <td className="py-1.5 px-2">
                        <span className={`px-1.5 py-0.5 rounded border text-[10px] ${STATUS_BADGE[m.ews_status] || 'bg-gray-100'}`}>
                          {m.ews_status}
                        </span>
                        <div className="text-[10px] text-gray-400 mt-0.5">{m.ews_nilai || '—'}</div>
                      </td>
                      <td className="py-1.5 px-2">
                        <span className={`px-1.5 py-0.5 rounded border text-[10px] ${STATUS_BADGE[m.v7_status] || 'bg-gray-100'}`}>
                          {m.v7_status}
                        </span>
                        <div className="text-[10px] text-gray-400 mt-0.5">{m.v7_metric_display || '—'}</div>
                      </td>
                      <td className="py-1.5 pl-2">
                        {m.is_match ? (
                          <span className="text-green-600 text-[11px]">✓ match</span>
                        ) : (
                          <span className="text-red-600 text-[11px]">✗ beda</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* v7-only */}
          {data.v7_only.length > 0 && (
            <div className="mb-3 p-2 border border-amber-200 rounded bg-amber-50/30">
              <div className="text-xs font-semibold text-amber-800 mb-1">
                v7-only ({data.v7_only.length}) — kriteria v7 tanpa pasangan EWS
              </div>
              <ul className="text-[11px] text-gray-600 space-y-0.5">
                {data.v7_only.map((v, i) => (
                  <li key={i}>
                    <span className="font-mono text-gray-500">{v.v7_kriteria_id}</span> · {v.satker_nama} ·{' '}
                    <span className={`px-1 py-0.5 rounded border text-[10px] ${STATUS_BADGE[v.v7_status] || 'bg-gray-100'}`}>{v.v7_status}</span>{' '}
                    <span className="text-gray-400">— {v.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ews-only */}
          {data.ews_only.length > 0 && (
            <div className="mb-3 p-2 border border-orange-200 rounded bg-orange-50/30">
              <div className="text-xs font-semibold text-orange-800 mb-1">
                ews-only ({data.ews_only.length}) — EWS legacy tanpa pasangan v7
              </div>
              <ul className="text-[11px] text-gray-600 space-y-0.5">
                {data.ews_only.map((v, i) => (
                  <li key={i}>
                    <span className="font-mono text-gray-500">{v.ews_kode}</span> · {v.satker_nama} ·{' '}
                    <span className={`px-1 py-0.5 rounded border text-[10px] ${STATUS_BADGE[v.ews_status] || 'bg-gray-100'}`}>{v.ews_status}</span>{' '}
                    <span className="text-gray-400">— {v.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
