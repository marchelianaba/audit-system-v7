'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, getSession, clearToken, Penugasan, Session, Skill, SkillInfo } from '@/lib/api';
import { AppShell } from '@/components/AppShell';

// Status penugasan (di-derive backend dari artefak) → label + warna yang ramah.
const STATUS_META: Record<string, { label: string; cls: string }> = {
  DRAFT: { label: 'Draft — belum analisis', cls: 'bg-gray-100 text-gray-700' },
  INGESTING: { label: '⟳ Ekstraksi dokumen', cls: 'bg-amber-50 text-amber-700' },
  KKP_IN_PROGRESS: { label: 'KKP berjalan', cls: 'bg-blue-50 text-blue-700' },
  KKP_QC: { label: 'KKP — QC', cls: 'bg-blue-50 text-blue-700' },
  KKP_DONE: { label: 'KKP disetujui KT', cls: 'bg-indigo-50 text-indigo-700' },
  LHP_IN_PROGRESS: { label: 'LHP berjalan', cls: 'bg-violet-50 text-violet-700' },
  LHP_QC: { label: 'LHP — QC', cls: 'bg-violet-50 text-violet-700' },
  LHP_DONE: { label: '✓ LHP selesai', cls: 'bg-emerald-50 text-emerald-700' },
};

function statusMeta(status: string) {
  return STATUS_META[status] || { label: status, cls: 'bg-gray-100 text-gray-700' };
}

export default function DashboardPage() {
  const router = useRouter();
  const [penugasan, setPenugasan] = useState<Penugasan[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [obyek, setObyek] = useState('');
  const [skill, setSkill] = useState<Skill>('reviu-rka-kl');
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [nomorSt, setNomorSt] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Hydration-safe: session di-baca dari localStorage HANYA setelah mount.
  // Awalnya null di server-render dan first client-render, lalu di-set di useEffect.
  const [session, setSessionState] = useState<Session | null>(null);
  const [mounted, setMounted] = useState(false);
  const [cacmPending, setCacmPending] = useState(0);

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSessionState(s);
    if (!s) {
      router.push('/login');
      return;
    }
    api
      .listPenugasan()
      .then(setPenugasan)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    // Badge notifikasi usulan CACM (abaikan error — fitur opsional)
    api.getCacmPending().then((r) => setCacmPending(r.count)).catch(() => {});
    // Daftar skill untuk dropdown (folder-driven). Fallback ke 2 skill pipeline.
    api
      .getSkills()
      .then((rows) => {
        setSkills(rows);
        if (rows.length && !rows.some((r) => r.slug === skill)) setSkill(rows[0].slug);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!obyek.trim()) {
      setError('Obyek penugasan wajib diisi.');
      return;
    }
    // Nomor ST kosong → context.md memuat placeholder [DIISI AUDITOR] → QC SAIPI
    // KRITIS (REN-003). Warn tegas tapi tetap izinkan (bisa dilengkapi via Konteks).
    if (!nomorSt.trim()) {
      const lanjut = confirm(
        'Nomor ST belum diisi.\n\nContext.md akan memuat placeholder dan QC SAIPI akan KRITIS (REN-003) ' +
          'sampai Nomor ST + tanggal dilengkapi (via tab Konteks/Setup).\n\nTetap buat penugasan?'
      );
      if (!lanjut) return;
    }
    try {
      const p = await api.createPenugasan({
        obyek,
        skill,
        nomor_st: nomorSt || undefined,
      });
      setPenugasan([p, ...penugasan]);
      setShowForm(false);
      setObyek('');
      setNomorSt('');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleLogout = () => {
    clearToken();
    router.push('/login');
  };

  const [deleting, setDeleting] = useState<number | null>(null);
  const handleDelete = async (p: Penugasan) => {
    if (
      !confirm(
        `Hapus penugasan "${p.obyek}"?\n\nSeluruh dokumen, hasil ingest, KKP, dan LHP akan DIHAPUS PERMANEN dari disk. Tindakan ini tidak bisa dibatalkan.`
      )
    )
      return;
    setDeleting(p.id);
    try {
      await api.deletePenugasan(p.id);
      setPenugasan((prev) => prev.filter((x) => x.id !== p.id));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDeleting(null);
    }
  };

  // SSR + first paint: render shell kosong (atau null) supaya HTML server === HTML
  // client. Setelah mount, session di-load dari localStorage.
  if (!mounted) {
    return <main className="min-h-screen" />;
  }
  if (!session) return null;

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto">
        <div className="text-sm text-gray-500 mb-1">INTEGRAL / Penugasan</div>
        <div className="flex justify-between items-center mb-5">
          <h1 className="text-2xl font-bold text-primary-dark">Daftar Penugasan</h1>
          <div className="flex items-center gap-3">
            <Link
              href="/cacm"
              className="relative px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
              title="CACM — Continuous Audit / Continuous Monitoring"
            >
              🔔 CACM
              {cacmPending > 0 && (
                <span
                  className="absolute -top-2 -right-2 min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[11px] font-bold flex items-center justify-center"
                  title={`${cacmPending} usulan CACM menunggu review`}
                >
                  {cacmPending}
                </span>
              )}
            </Link>
            <Link
              href="/knowledge"
              className="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
              title="Knowledge — wiki pattern temuan & konteks"
            >
              📚 Knowledge
            </Link>
            <Link
              href="/feedback"
              className="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
              title="Dashboard agregat feedback agen cross-penugasan"
            >
              📊 Feedback Agen
            </Link>
            {session?.role_aktif === 'PT' ? (
              <button
                onClick={() => setShowForm(!showForm)}
                className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-dark"
              >
                {showForm ? '× Batal' : '+ Penugasan Baru'}
              </button>
            ) : (
              <span className="text-xs text-gray-400 italic">
                🔒 Hanya Pengendali Teknis yang dapat membuat penugasan
              </span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {showForm && session?.role_aktif === 'PT' && (
          <form
            onSubmit={handleCreate}
            className="bg-white border border-gray-200 rounded-lg p-5 mb-5 grid gap-3"
          >
            <h3 className="font-semibold text-primary-dark">Penugasan Baru</h3>
            <label className="block">
              <span className="text-sm text-gray-700">Obyek penugasan</span>
              <input
                value={obyek}
                onChange={(e) => setObyek(e.target.value)}
                required
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="Contoh: RKA-K/L Dit. Pengendalian 2027"
              />
            </label>
            <label className="block">
              <span className="text-sm text-gray-700">Skill</span>
              <select
                value={skill}
                onChange={(e) => setSkill(e.target.value as Skill)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
              >
                {skills.length === 0 ? (
                  <>
                    <option value="reviu-rka-kl">Reviu RKA-K/L</option>
                    <option value="reviu-pengadaan">Reviu Pengadaan</option>
                  </>
                ) : (
                  skills.map((s) => (
                    <option key={s.slug} value={s.slug}>
                      {s.jenis || s.name}
                      {s.has_pipeline ? '' : ' · criteria-driven'}
                    </option>
                  ))
                )}
              </select>
            </label>
            <label className="block">
              <span className="text-sm text-gray-700">Nomor ST (opsional)</span>
              <input
                value={nomorSt}
                onChange={(e) => setNomorSt(e.target.value)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="51 IJ.3 KP.01.06 10.03.2026"
              />
            </label>
            <button
              type="submit"
              className="px-4 py-2 rounded bg-primary text-white font-semibold text-sm"
            >
              Buat
            </button>
          </form>
        )}

        {loading ? (
          <div className="text-gray-500 text-sm">Memuat…</div>
        ) : penugasan.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500">
            {session?.role_aktif === 'PT'
              ? <>Belum ada penugasan. Klik <strong>+ Penugasan Baru</strong>.</>
              : <>Belum ada penugasan. Tunggu Pengendali Teknis membuat penugasan terlebih dahulu.</>}
          </div>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 font-semibold text-gray-600 uppercase text-xs">No</th>
                  <th className="text-left p-3 font-semibold text-gray-600 uppercase text-xs">Obyek</th>
                  <th className="text-left p-3 font-semibold text-gray-600 uppercase text-xs">Skill</th>
                  <th className="text-left p-3 font-semibold text-gray-600 uppercase text-xs">Status</th>
                  <th className="text-left p-3 font-semibold text-gray-600 uppercase text-xs">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {penugasan.map((p, i) => (
                  <tr key={p.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="p-3">{i + 1}</td>
                    <td className="p-3 font-medium">{p.obyek}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 text-xs rounded bg-blue-50 text-blue-700">
                        {p.skill}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 text-xs rounded ${statusMeta(p.status).cls}`}>
                        {statusMeta(p.status).label}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-3">
                        <Link
                          href={`/penugasan/${p.id}`}
                          className="text-primary hover:underline"
                        >
                          Buka →
                        </Link>
                        {session?.role_aktif === 'PT' && (
                          <button
                            onClick={() => handleDelete(p)}
                            disabled={deleting === p.id}
                            className="text-red-600 hover:text-red-800 hover:underline disabled:opacity-50"
                            title="Hapus penugasan (permanen)"
                          >
                            {deleting === p.id ? 'Menghapus…' : 'Hapus'}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
