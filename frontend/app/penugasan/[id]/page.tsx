'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, getSession, Dokumen, Penugasan, Role } from '@/lib/api';

type Tab = 'dokumen' | 'setup' | 'chat' | 'output';

export default function DetailPenugasanPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const session = getSession();

  const [penugasan, setPenugasan] = useState<Penugasan | null>(null);
  const [dokumen, setDokumen] = useState<Dokumen[]>([]);
  const [tab, setTab] = useState<Tab>('dokumen');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) {
      router.push('/login');
      return;
    }
    // Reset semua state lokal sebelum fetch — penting saat pindah ke penugasan lain,
    // supaya UI lama (dokumen list, error message) tidak ter-display sebentar selama fetch.
    setPenugasan(null);
    setDokumen([]);
    setError(null);
    setTab('dokumen');
    Promise.all([api.getPenugasan(id), api.listDokumen(id)])
      .then(([p, d]) => {
        setPenugasan(p);
        setDokumen(d);
      })
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const f of Array.from(files)) {
      try {
        const d = await api.uploadDokumen(id, f);
        setDokumen((prev) => [...prev, d]);
      } catch (err: any) {
        setError(err.message);
      }
    }
    e.target.value = '';
  };

  const triggerIngest = async () => {
    try {
      await api.triggerIngestion(id);
      // refresh list
      const d = await api.listDokumen(id);
      setDokumen(d);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (!session || !penugasan) return null;

  const allReady = dokumen.length > 0 && dokumen.every((d) => d.status === 'READY');

  return (
    <main className="min-h-screen">
      <header className="bg-primary text-white px-6 py-3 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Link href="/penugasan" className="text-white/80 hover:text-white text-sm">
            ← Penugasan
          </Link>
          <span className="text-white/40">|</span>
          <span className="font-semibold text-sm">{penugasan.obyek}</span>
        </div>
        <div className="text-xs">
          {session.user.nama_lengkap}{' '}
          <span className="px-2 py-0.5 rounded bg-white/15 ml-2">{session.role_aktif}</span>
        </div>
      </header>

      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 flex gap-1">
          {(['dokumen', 'setup', 'chat', 'output'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-3 text-sm border-b-2 transition ${
                  tab === t
                    ? 'border-primary text-primary-dark font-semibold'
                    : 'border-transparent text-gray-500 hover:text-primary-dark'
                }`}
              >
                {t === 'dokumen' && 'Dokumen'}
                {t === 'setup' && (session.role_aktif === 'AT' ? 'Konteks' : 'Setup Penugasan')}
                {t === 'chat' && (session.role_aktif === 'AT' ? 'Chat AT' : 'Chat KT')}
                {t === 'output' && 'Output & QC'}
              </button>
            ))}
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-6">
        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* key={id} memaksa React unmount + remount setiap kali penugasan ganti,
            mencegah state lokal (chat prompt, modal preview, dll) bocor antar penugasan. */}
        {tab === 'dokumen' && (
          <DokumenTab
            key={`dokumen-${id}`}
            dokumen={dokumen}
            onUpload={handleUpload}
            onIngest={triggerIngest}
            allReady={allReady}
            role={session.role_aktif}
          />
        )}

        {tab === 'setup' && (
          <SetupPenugasanTab key={`setup-${id}`} penugasanId={id} role={session.role_aktif} />
        )}

        {tab === 'chat' && (
          <ChatTab key={`chat-${id}`} penugasanId={id} role={session.role_aktif} skill={penugasan.skill} />
        )}

        {tab === 'output' && (
          <OutputTab key={`output-${id}`} penugasan={penugasan} />
        )}
      </div>
    </main>
  );
}

function DokumenTab({
  dokumen,
  onUpload,
  onIngest,
  allReady,
  role,
}: {
  dokumen: Dokumen[];
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onIngest: () => void;
  allReady: boolean;
  role: Role;
}) {
  const canUpload = role === 'AT';
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-primary-dark">Dokumen Penugasan</h2>
        <div className="flex gap-2">
          {canUpload ? (
            <label className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold cursor-pointer hover:bg-primary-dark">
              + Upload
              <input type="file" multiple onChange={onUpload} className="hidden" />
            </label>
          ) : (
            <span className="px-4 py-2 rounded bg-gray-100 text-gray-500 text-sm">
              🔒 Upload hanya oleh Anggota Tim (AT)
            </span>
          )}
          {canUpload && (
            <button
              onClick={onIngest}
              disabled={dokumen.length === 0}
              className="px-4 py-2 rounded bg-ing text-white text-sm font-semibold hover:opacity-90 disabled:opacity-40"
            >
              Mulai Ingestion
            </button>
          )}
        </div>
      </div>

      {dokumen.length === 0 ? (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-10 text-center text-gray-500">
          {canUpload
            ? 'Belum ada dokumen. Upload TOR/RAB (Reviu RKA-K/L) atau KAK/HPS/RFI/Kontrak (Reviu Pengadaan).'
            : 'Belum ada dokumen. AT yang akan upload bukti pendukung setelah KT setup sasaran selesai.'}
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-3 text-xs uppercase text-gray-600">Nama File</th>
                <th className="text-left p-3 text-xs uppercase text-gray-600">Jenis</th>
                <th className="text-left p-3 text-xs uppercase text-gray-600">Status</th>
                <th className="text-left p-3 text-xs uppercase text-gray-600">Output</th>
              </tr>
            </thead>
            <tbody>
              {dokumen.map((d) => (
                <tr key={d.id} className="border-t border-gray-100">
                  <td className="p-3">{d.nama_file}</td>
                  <td className="p-3">
                    <span className="px-2 py-0.5 text-xs rounded bg-gray-100">{d.jenis}</span>
                  </td>
                  <td className="p-3">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="p-3 text-xs text-gray-500">
                    {d.ingested_json_path ? d.ingested_json_path.split('/').pop() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {allReady && (
        <div className="mt-4 p-3 rounded bg-green-50 border border-green-200 text-green-700 text-sm">
          ✓ Semua dokumen siap dianalisis. Buka tab <strong>Chat AT</strong> untuk memulai analisis.
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: Dokumen['status'] }) {
  const map = {
    UPLOADED: 'bg-gray-100 text-gray-700',
    INGESTING: 'bg-yellow-50 text-yellow-700',
    READY: 'bg-green-50 text-green-700',
    FAILED: 'bg-red-50 text-red-700',
  } as const;
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${map[status]}`}>
      {status === 'UPLOADED' && 'Antri'}
      {status === 'INGESTING' && '⟳ Mengekstrak…'}
      {status === 'READY' && '✓ Siap'}
      {status === 'FAILED' && '✗ Gagal'}
    </span>
  );
}

type AgentRun = {
  id: number;
  status: string;
  input_summary: string;
  output_summary: string;
  tool_calls: Array<{ tool: string; input: any }>;
  started_at: string | null;
  ended_at: string | null;
  error_message: string | null;
};

function formatChatTime(iso: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function ChatTab({
  penugasanId,
  role,
  skill,
}: {
  penugasanId: number;
  role: string;
  skill: string;
}) {
  const [prompt, setPrompt] = useState(
    role === 'AT'
      ? `Mulai analisis ${skill} untuk penugasan ini. Jalankan pipeline V6 dan verifikasi anomali.`
      : 'Susun draft LHR dari temuan.json yang sudah disetujui anggota tim.'
  );
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [history, setHistory] = useState<AgentRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const agent = role === 'AT' ? 'anggota_tim' : 'ketua_tim';

  // Load history saat mount (atau saat penugasan/role change)
  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await api.getAgentHistory(agent as any, penugasanId);
      setHistory(res.runs);
      setHistoryError(null);
    } catch (e: any) {
      setHistoryError(e.message);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasanId, agent]);

  // Auto-scroll ke bawah setelah history loaded atau run selesai
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, running]);

  const start = async () => {
    setRunning(true);
    setElapsed(0);
    const startTime = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
    const currentPrompt = prompt;

    try {
      const res = await api.runAgent(agent as any, penugasanId, currentPrompt);
      // Tambah run baru ke history. Backend juga sudah persist ke DB.
      setHistory((prev) => [
        ...prev,
        {
          id: res.run_id,
          status: res.status,
          input_summary: currentPrompt.slice(0, 500),
          output_summary: res.output.slice(0, 2000),
          tool_calls: res.tool_calls,
          started_at: new Date(startTime).toISOString(),
          ended_at: new Date().toISOString(),
          error_message: res.error,
        },
      ]);
    } catch (e: any) {
      // Tambah error entry juga supaya jejak attempt tetap ada di UI sampai reload
      setHistory((prev) => [
        ...prev,
        {
          id: -Date.now(), // negatif = belum ada di DB
          status: 'failed',
          input_summary: currentPrompt.slice(0, 500),
          output_summary: '',
          tool_calls: [],
          started_at: new Date(startTime).toISOString(),
          ended_at: new Date().toISOString(),
          error_message: e.message,
        },
      ]);
    } finally {
      clearInterval(timer);
      setRunning(false);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-bold text-primary-dark">
          {role === 'AT' ? 'Chat dengan Agen Anggota Tim' : 'Chat dengan Agen Ketua Tim'}
        </h2>
        <button
          onClick={loadHistory}
          disabled={loadingHistory}
          className="text-xs px-2.5 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
        >
          {loadingHistory ? 'Memuat…' : '↻ Refresh history'}
        </button>
      </div>

      {historyError && (
        <div className="mb-3 p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">
          Gagal load history: {historyError}
        </div>
      )}

      <div
        ref={scrollRef}
        className="bg-white border border-gray-200 rounded-lg p-4 mb-3 min-h-[300px] max-h-[600px] overflow-y-auto space-y-4"
      >
        {loadingHistory && history.length === 0 ? (
          <p className="text-gray-400 text-sm italic">Memuat history percakapan…</p>
        ) : history.length === 0 && !running ? (
          <p className="text-gray-400 text-sm italic">
            Belum ada percakapan dengan agen. Tulis pertanyaan/perintah di bawah dan klik Jalankan.
          </p>
        ) : (
          history.map((run) => (
            <div key={run.id} className="border-b border-gray-100 pb-3 last:border-0">
              {/* Prompt user */}
              <div className="bg-blue-50 border-l-4 border-blue-500 rounded-r p-3 mb-2">
                <div className="flex justify-between items-baseline mb-1">
                  <span className="text-xs uppercase font-semibold text-blue-700">
                    {role === 'AT' ? 'Anggota Tim' : 'Ketua Tim'}
                  </span>
                  <span className="text-xs text-gray-500">{formatChatTime(run.started_at)}</span>
                </div>
                <div className="text-sm text-gray-800 whitespace-pre-wrap">{run.input_summary}</div>
              </div>

              {/* Response agen */}
              {run.error_message ? (
                <div className="bg-red-50 border-l-4 border-red-500 rounded-r p-3 text-sm text-red-700">
                  <div className="text-xs uppercase font-semibold mb-1">Error</div>
                  {run.error_message}
                </div>
              ) : (
                <div className="bg-gray-50 border-l-4 border-gray-300 rounded-r p-3">
                  <div className="flex justify-between items-baseline mb-1">
                    <span className="text-xs uppercase font-semibold text-gray-600">
                      Agen · {run.status}
                    </span>
                    {run.ended_at && (
                      <span className="text-xs text-gray-500">
                        selesai {formatChatTime(run.ended_at)}
                      </span>
                    )}
                  </div>
                  <div className="text-sm whitespace-pre-wrap text-gray-800">
                    {run.output_summary || '(tidak ada output)'}
                  </div>
                  {run.tool_calls && run.tool_calls.length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs uppercase text-gray-500 font-semibold cursor-pointer hover:text-gray-700 select-none">
                        Audit trail · {run.tool_calls.length} tool call{run.tool_calls.length === 1 ? '' : 's'}
                      </summary>
                      <div className="mt-2">
                        {run.tool_calls.map((tc, i) => (
                          <div
                            key={i}
                            className="bg-yellow-50 border-l-2 border-accent rounded-r p-2 text-xs font-mono mb-1"
                          >
                            → {tc.tool}({JSON.stringify(tc.input).slice(0, 120)}…)
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {running && (
          <div className="flex items-center gap-2 text-blue-600">
            <span className="inline-block w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></span>
            <span className="text-sm">Agen sedang bekerja… ({elapsed}s)</span>
          </div>
        )}
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        className="w-full border border-gray-300 rounded-lg p-3 text-sm h-24"
        placeholder="Tulis perintah ke agen…"
        disabled={running}
      />
      <div className="mt-2 flex gap-2">
        <button
          onClick={start}
          disabled={running}
          className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-dark disabled:opacity-40"
        >
          {running ? `⟳ Berjalan (${elapsed}s)…` : '▶ Jalankan'}
        </button>
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Catatan: agen butuh 30–90 detik untuk selesai. Tombol akan aktif kembali setelah respons masuk.
      </p>
    </div>
  );
}
type FileEntry = {
  name: string;
  path: string;
  size_bytes: number;
  mtime: string;
  ext: string;
};

type FileCategory = {
  key: string;
  label: string;
  files: FileEntry[];
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function iconForExt(ext: string): string {
  switch (ext) {
    case '.docx':
      return '📄';
    case '.pdf':
      return '📕';
    case '.json':
    case '.jsonl':
      return '🔧';
    case '.md':
      return '📝';
    case '.xlsx':
    case '.csv':
      return '📊';
    case '.txt':
    case '.log':
      return '📃';
    default:
      return '📎';
  }
}

const PREVIEWABLE = new Set(['.md', '.json', '.jsonl', '.txt', '.csv', '.log']);

// ============================================================
// SETUP PENUGASAN TAB — Ketua Tim mengisi sasaran-assignment + context.md
// ============================================================

type Sasaran = {
  sasaran_id: string;
  deskripsi: string;
  assigned_to: string[];
  langkah_kerja: string[];
  status: string;
};

function emptySasaran(idx: number): Sasaran {
  return {
    sasaran_id: `S-${String(idx).padStart(2, '0')}`,
    deskripsi: '',
    assigned_to: [],
    langkah_kerja: [],
    status: 'AKTIF',
  };
}

function SetupPenugasanTab({ penugasanId, role }: { penugasanId: number; role: Role }) {
  const canEditSasaran = role === 'KT' || role === 'PT';
  const canEditContext = role === 'KT' || role === 'PT' || role === 'AT';
  const [sasaran, setSasaran] = useState<Sasaran[] | null>(null);
  const [contextMd, setContextMd] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<'sasaran' | 'context' | null>(null);
  const [savedAt, setSavedAt] = useState<{ sasaran?: string; context?: string }>({});
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [sa, cm] = await Promise.all([
        api.getSasaranAssignment(penugasanId),
        api.getContextMd(penugasanId),
      ]);
      // Normalize: pastikan semua field array tidak undefined (data lama mungkin tidak punya langkah_kerja)
      const normalized: Sasaran[] = (sa.sasaran || []).map((s: any) => ({
        sasaran_id: String(s.sasaran_id ?? ''),
        deskripsi: String(s.deskripsi ?? ''),
        assigned_to: Array.isArray(s.assigned_to) ? s.assigned_to.map(String) : [],
        langkah_kerja: Array.isArray(s.langkah_kerja) ? s.langkah_kerja.map(String) : [],
        status: String(s.status ?? 'AKTIF'),
      }));
      setSasaran(normalized);
      setContextMd(cm.content || '');
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasanId]);

  const addSasaran = () => {
    const next = sasaran || [];
    setSasaran([...next, emptySasaran(next.length + 1)]);
  };

  const removeSasaran = (idx: number) => {
    if (!sasaran) return;
    setSasaran(sasaran.filter((_, i) => i !== idx));
  };

  const updateSasaran = (idx: number, patch: Partial<Sasaran>) => {
    if (!sasaran) return;
    const next = [...sasaran];
    next[idx] = { ...next[idx], ...patch };
    setSasaran(next);
  };

  const saveSasaran = async () => {
    if (!sasaran) return;
    setSaving('sasaran');
    setErr(null);
    try {
      // Validasi client-side
      const ids = sasaran.map((s) => s.sasaran_id.trim());
      const empty = ids.filter((id) => !id);
      if (empty.length > 0) {
        throw new Error('Ada sasaran tanpa ID — semua sasaran wajib punya ID');
      }
      if (new Set(ids).size !== ids.length) {
        throw new Error('Ada sasaran_id duplikat');
      }
      const cleaned = sasaran.map((s) => ({
        ...s,
        sasaran_id: s.sasaran_id.trim(),
        deskripsi: s.deskripsi.trim(),
        assigned_to: s.assigned_to.map((x) => x.trim()).filter(Boolean),
        langkah_kerja: s.langkah_kerja.map((x) => x.trim()).filter(Boolean),
      }));
      const res = await api.saveSasaranAssignment(penugasanId, cleaned);
      setSavedAt({ ...savedAt, sasaran: new Date().toLocaleTimeString('id-ID') });
      setSasaran(cleaned);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(null);
    }
  };

  const saveContextMd = async () => {
    setSaving('context');
    setErr(null);
    try {
      await api.saveContextMd(penugasanId, contextMd);
      setSavedAt({ ...savedAt, context: new Date().toLocaleTimeString('id-ID') });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return <div className="bg-white p-5 rounded-lg text-sm text-gray-500">Memuat setup penugasan…</div>;
  }

  return (
    <div className="space-y-6">
      {err && (
        <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
          {err}
        </div>
      )}

      {role === 'AT' ? (
        <div className="bg-blue-50 border-l-4 border-blue-400 p-4 rounded text-sm text-blue-900">
          <strong>Penyempurnaan Konteks (peran AT).</strong> Anda bisa edit{' '}
          <strong>context.md</strong> di bawah ini untuk melengkapi detail yang Anda
          temukan saat analisis (mis. periode, tujuan reviu yang lebih spesifik).
          Sasaran-assignment dikunci read-only — itu domain Ketua Tim.
        </div>
      ) : (
        <div className="bg-blue-50 border-l-4 border-blue-400 p-4 rounded text-sm text-blue-900">
          <strong>Setup Penugasan (peran KT/PT).</strong> Isi dua hal di bawah
          sebelum Anggota Tim bisa mulai analisis: (1) <strong>context.md</strong> — metadata
          penugasan termasuk tabel tim, dan (2) <strong>sasaran-assignment</strong> — daftar
          sasaran reviu yang di-assign ke anggota. Anda juga bisa bantu lewat
          tab <strong>Chat KT</strong> untuk drafting via percakapan.
        </div>
      )}

      {/* === CONTEXT.MD === */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">1. Konteks Penugasan (context.md)</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Isi Periode, Tahun Anggaran, Tujuan reviu, dan Tabel Tim. Format Markdown.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {savedAt.context && (
              <span className="text-xs text-green-700">✓ Tersimpan {savedAt.context}</span>
            )}
            {canEditContext ? (
              <button
                onClick={saveContextMd}
                disabled={saving === 'context'}
                className="px-4 py-1.5 text-sm rounded bg-primary text-white hover:bg-primary-dark disabled:opacity-50"
              >
                {saving === 'context' ? 'Menyimpan…' : 'Simpan Konteks'}
              </button>
            ) : (
              <span className="text-xs text-gray-400 italic">🔒 Read-only</span>
            )}
          </div>
        </div>
        <textarea
          value={contextMd}
          onChange={(e) => setContextMd(e.target.value)}
          disabled={!canEditContext}
          className="w-full p-4 font-mono text-xs h-80 border-0 resize-y focus:outline-none focus:ring-1 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-600"
          placeholder="# Konteks Penugasan: ..."
        />
      </div>

      {/* === SASARAN-ASSIGNMENT === */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">
              2. Sasaran Reviu &amp; Assignment ({sasaran?.length || 0})
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Daftar sasaran yang akan dianalisis Anggota Tim. Setiap sasaran punya ID unik
              (mis. S-PBJ-01), deskripsi, dan minimal 1 nama anggota di "Assigned to".
            </p>
          </div>
          <div className="flex items-center gap-3">
            {savedAt.sasaran && (
              <span className="text-xs text-green-700">✓ Tersimpan {savedAt.sasaran}</span>
            )}
            {canEditSasaran ? (
              <button
                onClick={saveSasaran}
                disabled={saving === 'sasaran'}
                className="px-4 py-1.5 text-sm rounded bg-primary text-white hover:bg-primary-dark disabled:opacity-50"
              >
                {saving === 'sasaran' ? 'Menyimpan…' : 'Simpan Sasaran'}
              </button>
            ) : (
              <span className="text-xs text-gray-400 italic">🔒 Read-only untuk AT</span>
            )}
          </div>
        </div>

        {(!sasaran || sasaran.length === 0) && (
          <div className="p-5 text-center text-sm text-gray-500">
            Belum ada sasaran.{' '}
            {canEditSasaran ? (
              <>Klik <strong>+ Tambah Sasaran</strong> untuk mulai.</>
            ) : (
              <>Tunggu Ketua Tim setup sasaran terlebih dahulu.</>
            )}
          </div>
        )}

        {sasaran && sasaran.length > 0 && (
          <div className="divide-y divide-gray-100">
            {sasaran.map((s, idx) => (
              <div key={idx} className="p-4 hover:bg-gray-50">
                <div className="grid grid-cols-12 gap-3 mb-2">
                  <div className="col-span-2">
                    <label className="text-xs text-gray-500 mb-1 block">Sasaran ID *</label>
                    <input
                      value={s.sasaran_id}
                      onChange={(e) => updateSasaran(idx, { sasaran_id: e.target.value })}
                      placeholder="S-PBJ-01"
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm font-mono disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                  <div className="col-span-7">
                    <label className="text-xs text-gray-500 mb-1 block">Deskripsi *</label>
                    <input
                      value={s.deskripsi}
                      onChange={(e) => updateSasaran(idx, { deskripsi: e.target.value })}
                      placeholder="Mis. Kewajaran HPS"
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs text-gray-500 mb-1 block">Status</label>
                    <select
                      value={s.status}
                      onChange={(e) => updateSasaran(idx, { status: e.target.value })}
                      disabled={!canEditSasaran}
                      className={`w-full border rounded px-2 py-1.5 text-sm disabled:opacity-80 ${
                        s.status === 'DISETUJUI_KT' ? 'border-emerald-400 bg-emerald-50' :
                        s.status === 'SELESAI_KKP' ? 'border-amber-400 bg-amber-50' :
                        s.status === 'DITOLAK_KT' ? 'border-red-400 bg-red-50' :
                        'border-gray-300'
                      }`}
                    >
                      <option value="AKTIF">AKTIF (menunggu temuan AT)</option>
                      <option value="SELESAI_KKP">SELESAI_KKP (sudah ada temuan)</option>
                      <option value="DISETUJUI_KT">✓ DISETUJUI_KT (KKP di-approve)</option>
                      <option value="DITOLAK_KT">✗ DITOLAK_KT (perlu revisi AT)</option>
                      <option value="DIBATALKAN">DIBATALKAN</option>
                    </select>
                  </div>
                  {canEditSasaran && (
                    <div className="col-span-1 flex items-end">
                      <button
                        onClick={() => removeSasaran(idx)}
                        className="w-full px-2 py-1.5 text-xs rounded text-red-600 hover:bg-red-50 border border-red-200"
                        title="Hapus sasaran"
                      >
                        Hapus
                      </button>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-12 gap-3">
                  <div className="col-span-5">
                    <label className="text-xs text-gray-500 mb-1 block">
                      Assigned to (1 nama per baris)
                    </label>
                    <textarea
                      value={s.assigned_to.join('\n')}
                      onChange={(e) =>
                        updateSasaran(idx, {
                          assigned_to: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean),
                        })
                      }
                      placeholder="Sarah Aulia&#10;Citra Lestari"
                      rows={3}
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                  <div className="col-span-7">
                    <label className="text-xs text-gray-500 mb-1 block">
                      Langkah kerja (1 langkah per baris, opsional)
                    </label>
                    <textarea
                      value={s.langkah_kerja.join('\n')}
                      onChange={(e) =>
                        updateSasaran(idx, {
                          langkah_kerja: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean),
                        })
                      }
                      placeholder="Cek 7 blok KAK&#10;Verifikasi SLA &amp; jadwal"
                      rows={3}
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {canEditSasaran && (
          <div className="px-5 py-3 bg-gray-50 border-t border-gray-200">
            <button
              onClick={addSasaran}
              className="px-3 py-1.5 text-sm rounded border border-primary text-primary hover:bg-primary hover:text-white transition"
            >
              + Tambah Sasaran
            </button>
          </div>
        )}
      </div>

      {canEditSasaran && (
        <div className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded p-3">
          <strong>Tips:</strong> setelah simpan, AT bisa mulai upload dokumen +
          analisis. Status sasaran otomatis upgrade ke <code>SELESAI_KKP</code> saat AT
          input temuan; KT ubah ke <code>DISETUJUI_KT</code> setelah review KKP, baru
          bisa lanjut ke Draft LHR.
        </div>
      )}
    </div>
  );
}

function OutputTab({ penugasan }: { penugasan: Penugasan }) {
  const [categories, setCategories] = useState<FileCategory[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<{ path: string; content: string; truncated: boolean } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const res = await api.listFiles(penugasan.id);
      setCategories(res.categories);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasan.id]);

  const handleDownload = async (file: FileEntry) => {
    try {
      const blob = await api.downloadFile(penugasan.id, file.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handlePreview = async (file: FileEntry) => {
    setPreviewLoading(true);
    try {
      const res = await api.previewFile(penugasan.id, file.path);
      setPreview({ path: res.path, content: res.content, truncated: res.truncated });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const isEmpty = !loading && (categories === null || categories.length === 0);

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-bold text-primary-dark">Output &amp; Laporan QC</h2>
        <button
          onClick={fetchFiles}
          className="px-3 py-1.5 text-xs rounded border border-gray-300 hover:bg-gray-50"
          disabled={loading}
        >
          {loading ? 'Memuat…' : '↻ Refresh'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-5 text-sm text-gray-500">
          Memuat daftar file…
        </div>
      )}

      {isEmpty && (
        <div className="bg-white border border-gray-200 rounded-lg p-5 text-sm text-gray-600">
          <p className="mb-2">
            Belum ada file output. Jalankan agen di tab <strong>Chat</strong> untuk men-generate KKP, LHR, laporan QA.
          </p>
          <p className="text-xs text-gray-500">
            Folder server: <code className="bg-gray-100 px-1 rounded">{penugasan.folder_path}</code>
          </p>
        </div>
      )}

      {!loading && categories && categories.length > 0 && (
        <div className="space-y-4">
          {categories.map((cat) => (
            <div key={cat.key} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex justify-between items-center">
                <div>
                  <span className="font-semibold text-sm text-primary-dark">{cat.label}</span>
                  <span className="ml-2 text-xs text-gray-500">({cat.files.length} file)</span>
                </div>
                <code className="text-xs text-gray-400">{cat.key}</code>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {cat.files.map((f) => (
                    <tr key={f.path} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-2 w-8 text-base">{iconForExt(f.ext)}</td>
                      <td className="px-2 py-2">
                        <div className="font-medium">{f.name}</div>
                        <div className="text-xs text-gray-400 font-mono">{f.path}</div>
                      </td>
                      <td className="px-2 py-2 text-xs text-gray-500 whitespace-nowrap">
                        {formatBytes(f.size_bytes)}
                      </td>
                      <td className="px-2 py-2 text-xs text-gray-500 whitespace-nowrap">
                        {formatTime(f.mtime)}
                      </td>
                      <td className="px-2 py-2 text-right whitespace-nowrap">
                        {PREVIEWABLE.has(f.ext) && (
                          <button
                            onClick={() => handlePreview(f)}
                            className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-100 mr-1"
                            disabled={previewLoading}
                          >
                            Preview
                          </button>
                        )}
                        <button
                          onClick={() => handleDownload(f)}
                          className="text-xs px-2 py-1 rounded bg-primary text-white hover:bg-primary-dark"
                        >
                          Download
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-6 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[85vh] flex flex-col">
            <div className="flex justify-between items-center px-5 py-3 border-b border-gray-200">
              <div className="font-mono text-sm">{preview.path}</div>
              <button
                onClick={() => setPreview(null)}
                className="text-gray-500 hover:text-gray-800 text-xl"
                aria-label="Tutup preview"
              >
                ×
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-5 text-xs whitespace-pre-wrap font-mono bg-gray-50">
              {preview.content}
            </pre>
            {preview.truncated && (
              <div className="px-5 py-2 text-xs text-amber-700 bg-amber-50 border-t border-amber-200">
                File besar — hanya 50 KB awal yang ditampilkan. Klik Download untuk file lengkap.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
