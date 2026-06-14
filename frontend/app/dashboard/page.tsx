'use client';

/**
 * Dashboard — ringkasan portofolio pengawasan INTEGRAL AI Workspace.
 *
 * Landing utama setelah login. Menyajikan:
 * - Kartu ringkas: total penugasan, sedang berjalan, LHP selesai, usulan CACM
 * - Sebaran status (progress bar per kelompok status)
 * - Penugasan terbaru (5) dengan tautan ke detail
 *
 * Semua angka di-derive dari /penugasan (status sudah dihitung backend) —
 * tidak ada endpoint statistik khusus, jadi halaman ini murni agregasi sisi klien.
 */
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, getSession, Penugasan, Session, SkillInfo } from '@/lib/api';
import { AppShell } from '@/components/AppShell';

// Selaras dengan STATUS_META di app/penugasan/page.tsx.
const STATUS_META: Record<string, { label: string; cls: string }> = {
  USULAN_CACM: { label: '🔔 Usulan CACM', cls: 'bg-rose-50 text-rose-700' },
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

// Kelompokkan status mentah → "sedang berjalan" untuk kartu ringkas.
const IN_PROGRESS = new Set([
  'INGESTING',
  'KKP_IN_PROGRESS',
  'KKP_QC',
  'KKP_DONE',
  'LHP_IN_PROGRESS',
  'LHP_QC',
]);

export default function DashboardPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [penugasan, setPenugasan] = useState<Penugasan[]>([]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [cacmPending, setCacmPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSession(s);
    if (!s) {
      router.push('/login');
      return;
    }
    api
      .listPenugasan()
      .then(setPenugasan)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    api.getCacmPending().then((r) => setCacmPending(r.count)).catch(() => {});
    api.getSkills().then(setSkills).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const skillLabel = useMemo(() => {
    const m = new Map(skills.map((s) => [s.slug, s.jenis || s.name]));
    return (slug: string) => m.get(slug) || slug;
  }, [skills]);

  const stats = useMemo(() => {
    const total = penugasan.length;
    const byStatus = new Map<string, number>();
    let berjalan = 0;
    let selesai = 0;
    let usulan = 0;
    for (const p of penugasan) {
      byStatus.set(p.status, (byStatus.get(p.status) || 0) + 1);
      if (IN_PROGRESS.has(p.status)) berjalan += 1;
      if (p.status === 'LHP_DONE') selesai += 1;
      if (p.status === 'USULAN_CACM') usulan += 1;
    }
    const sorted = Array.from(byStatus.entries()).sort((a, b) => b[1] - a[1]);
    return { total, berjalan, selesai, usulan, sorted };
  }, [penugasan]);

  const recent = useMemo(
    () =>
      [...penugasan]
        .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        .slice(0, 5),
    [penugasan]
  );

  const fmtDate = (iso: string | null) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('id-ID', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return iso.slice(0, 10);
    }
  };

  return (
    <AppShell>
      <div className="text-xs text-gray-400 mb-2">INTEGRAL / Dashboard</div>
      <div className="flex items-end justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-ink">Dashboard</h2>
          <p className="text-sm text-gray-500">
            {mounted && session
              ? `Selamat datang, ${session.user.nama_lengkap} — ringkasan portofolio pengawasan.`
              : 'Ringkasan portofolio pengawasan.'}
          </p>
        </div>
        <Link
          href="/penugasan"
          className="px-4 py-2 rounded-lg integral-gradient text-white text-sm font-semibold shadow-integral hover:opacity-95"
        >
          Buka Daftar Penugasan →
        </Link>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-rose-50 text-rose-700 text-sm">
          Gagal memuat data: {error}
        </div>
      )}

      {/* Kartu ringkas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Penugasan" value={stats.total} icon="🗂" href="/penugasan" />
        <StatCard label="Sedang Berjalan" value={stats.berjalan} icon="⟳" tone="blue" />
        <StatCard label="LHP Selesai" value={stats.selesai} icon="✓" tone="emerald" />
        <StatCard
          label="Usulan CACM"
          value={cacmPending || stats.usulan}
          icon="🔔"
          tone="rose"
          href="/cacm"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sebaran status */}
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-ink mb-4">Sebaran Status</h3>
          {loading ? (
            <p className="text-sm text-gray-400">Memuat…</p>
          ) : stats.sorted.length === 0 ? (
            <p className="text-sm text-gray-400">Belum ada penugasan.</p>
          ) : (
            <div className="space-y-3">
              {stats.sorted.map(([status, n]) => {
                const meta = statusMeta(status);
                const pct = stats.total ? Math.round((n / stats.total) * 100) : 0;
                return (
                  <div key={status}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className={`px-2 py-0.5 rounded ${meta.cls}`}>{meta.label}</span>
                      <span className="text-gray-500">
                        {n} · {pct}%
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full integral-gradient rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Penugasan terbaru */}
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-ink">Penugasan Terbaru</h3>
            <Link href="/penugasan" className="text-xs text-primary hover:underline">
              Lihat semua →
            </Link>
          </div>
          {loading ? (
            <p className="text-sm text-gray-400">Memuat…</p>
          ) : recent.length === 0 ? (
            <p className="text-sm text-gray-400">Belum ada penugasan.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {recent.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/penugasan/${p.id}`}
                    className="flex items-center gap-3 py-2.5 hover:bg-gray-50 -mx-2 px-2 rounded-lg transition"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-ink truncate">
                        {p.obyek || p.kode || `Penugasan #${p.id}`}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {skillLabel(p.skill)} · {fmtDate(p.created_at)}
                      </div>
                    </div>
                    <span
                      className={`shrink-0 px-2 py-0.5 text-xs rounded ${statusMeta(p.status).cls}`}
                    >
                      {statusMeta(p.status).label}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function StatCard({
  label,
  value,
  icon,
  tone = 'primary',
  href,
}: {
  label: string;
  value: number;
  icon: string;
  tone?: 'primary' | 'blue' | 'emerald' | 'rose';
  href?: string;
}) {
  const toneCls: Record<string, string> = {
    primary: 'text-primary',
    blue: 'text-blue-600',
    emerald: 'text-emerald-600',
    rose: 'text-rose-600',
  };
  const inner = (
    <div className="bg-white border border-gray-200 rounded-xl p-4 h-full hover:shadow-card transition">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-gray-400">{label}</span>
        <span className="text-lg">{icon}</span>
      </div>
      <div className={`mt-2 text-3xl font-bold ${toneCls[tone]}`}>{value}</div>
    </div>
  );
  return href ? (
    <Link href={href} className="block">
      {inner}
    </Link>
  ) : (
    inner
  );
}
