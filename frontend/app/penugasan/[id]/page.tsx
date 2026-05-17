'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, getSession, Dokumen, Penugasan } from '@/lib/api';

type Tab = 'dokumen' | 'chat' | 'output';

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
    Promise.all([api.getPenugasan(id), api.listDokumen(id)])
      .then(([p, d]) => {
        setPenugasan(p);
        setDokumen(d);
      })
      .catch((e) => setError(e.message));
  }, [id, router]);

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
          {(['dokumen', 'chat', 'output'] as Tab[]).map((t) => (
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

        {tab === 'dokumen' && (
          <DokumenTab
            dokumen={dokumen}
            onUpload={handleUpload}
            onIngest={triggerIngest}
            allReady={allReady}
          />
        )}

        {tab === 'chat' && <ChatTab penugasanId={id} role={session.role_aktif} skill={penugasan.skill} />}

        {tab === 'output' && <OutputTab penugasan={penugasan} />}
      </div>
    </main>
  );
}

function DokumenTab({
  dokumen,
  onUpload,
  onIngest,
  allReady,
}: {
  dokumen: Dokumen[];
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onIngest: () => void;
  allReady: boolean;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-primary-dark">Dokumen Penugasan</h2>
        <div className="flex gap-2">
          <label className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold cursor-pointer hover:bg-primary-dark">
            + Upload
            <input type="file" multiple onChange={onUpload} className="hidden" />
          </label>
          <button
            onClick={onIngest}
            disabled={dokumen.length === 0}
            className="px-4 py-2 rounded bg-ing text-white text-sm font-semibold hover:opacity-90 disabled:opacity-40"
          >
            Mulai Ingestion
          </button>
        </div>
      </div>

      {dokumen.length === 0 ? (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-10 text-center text-gray-500">
          Belum ada dokumen. Upload TOR/RAB (Reviu RKA-K/L) atau KAK/HPS/RFI/Kontrak (Reviu Pengadaan).
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
  const [result, setResult] = useState<{
    output: string;
    tool_calls: Array<{ tool: string; input: any }>;
    error: string | null;
  } | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const start = async () => {
    setResult(null);
    setRunning(true);
    setElapsed(0);
    const startTime = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);

    try {
      const agent = role === 'AT' ? 'anggota_tim' : 'ketua_tim';
      const res = await api.runAgent(agent as any, penugasanId, prompt);
      setResult({ output: res.output, tool_calls: res.tool_calls, error: res.error });
    } catch (e: any) {
      setResult({ output: '', tool_calls: [], error: e.message });
    } finally {
      clearInterval(timer);
      setRunning(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-bold text-primary-dark mb-3">
        {role === 'AT' ? 'Chat dengan Agen Anggota Tim' : 'Chat dengan Agen Ketua Tim'}
      </h2>

      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3 min-h-[300px] max-h-[600px] overflow-y-auto">
        {!result && !running && (
          <p className="text-gray-400 text-sm italic">Belum ada hasil…</p>
        )}
        {running && (
          <div className="flex items-center gap-2 text-blue-600">
            <span className="inline-block w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></span>
            <span className="text-sm">Agen sedang bekerja… ({elapsed}s)</span>
          </div>
        )}
        {result?.error && (
          <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">
            Error: {result.error}
          </div>
        )}
        {result?.output && (
          <div className="bg-gray-50 rounded-lg p-3 text-sm whitespace-pre-wrap mb-3">
            {result.output}
          </div>
        )}
        {result?.tool_calls && result.tool_calls.length > 0 && (
          <div className="mt-3">
            <h4 className="text-xs uppercase text-gray-500 font-semibold mb-2">Tool calls ({result.tool_calls.length})</h4>
            {result.tool_calls.map((tc, i) => (
              <div key={i} className="bg-yellow-50 border-l-2 border-accent rounded-r-lg p-2 text-xs font-mono mb-1">
                → {tc.tool}({JSON.stringify(tc.input).slice(0, 120)}…)
              </div>
            ))}
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
function OutputTab({ penugasan }: { penugasan: Penugasan }) {
  return (
    <div>
      <h2 className="text-lg font-bold text-primary-dark mb-3">Output &amp; Laporan QC</h2>
      <div className="bg-white border border-gray-200 rounded-lg p-5 text-sm text-gray-600">
        <p className="mb-2">
          File output disimpan di folder server: <code className="bg-gray-100 px-1 rounded">{penugasan.folder_path}</code>
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li><code>_KKP/temuan.json</code> — master temuan</li>
          <li><code>_KKP/KKP-{`{nama-anggota}`}.docx</code> — KKP per anggota</li>
          <li><code>_LHP/LHR-DRAFT.docx</code> — LHR (oleh Ketua Tim)</li>
          <li><code>_QA-SAIPI/laporan-qa-kkp.md</code>, <code>laporan-qa-lhp.md</code></li>
        </ul>
        <p className="mt-3 text-xs text-gray-500">
          (Halaman download &amp; preview akan ditambahkan setelah workflow ujicoba berhasil.)
        </p>
      </div>
    </div>
  );
}
