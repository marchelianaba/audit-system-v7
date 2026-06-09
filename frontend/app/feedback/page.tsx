'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, clearToken, getSession, Session } from '@/lib/api';
import { AppShell } from '@/components/AppShell';

type Aggregate = Awaited<ReturnType<typeof api.getFeedbackAggregate>>;
type ListResp = Awaited<ReturnType<typeof api.listFeedback>>;

const WINDOW_OPTIONS = [
  { label: '7 hari', value: 7 },
  { label: '30 hari', value: 30 },
  { label: '90 hari', value: 90 },
] as const;

const SEVERITY_COLOR: Record<string, string> = {
  blocker: 'bg-red-100 text-red-800 border-red-300',
  major: 'bg-amber-100 text-amber-800 border-amber-300',
  minor: 'bg-blue-100 text-blue-800 border-blue-300',
};

const CONFIDENCE_COLOR: Record<string, string> = {
  HIGH: 'bg-emerald-100 text-emerald-800',
  MEDIUM: 'bg-amber-100 text-amber-800',
  LOW: 'bg-red-100 text-red-800',
};

const AGENT_LABEL: Record<string, string> = {
  ingestion: 'Ingestion',
  anggota_tim: 'Anggota Tim',
  ketua_tim: 'Ketua Tim',
  qc_saipi: 'QC SAIPI',
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function FeedbackDashboardPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [days, setDays] = useState(30);
  const [agg, setAgg] = useState<Aggregate | null>(null);
  const [list, setList] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSession(s);
    if (!s) {
      router.push('/login');
    }
  }, [router]);

  const load = async (d: number) => {
    setLoading(true);
    setError(null);
    try {
      const [a, l] = await Promise.all([
        api.getFeedbackAggregate(d),
        api.listFeedback(d),
      ]);
      setAgg(a);
      setList(l);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (mounted && session) load(days);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, session, days]);

  const heatmapAgents = useMemo(
    () => (agg ? Object.keys(agg.severity_heatmap) : []),
    [agg]
  );

  const handleLogout = () => {
    clearToken();
    router.push('/login');
  };

  if (!mounted) return <main className="min-h-screen" />;
  if (!session) return null;

  return (
    <AppShell>

      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary-dark">Feedback Aggregate</h1>
            <p className="text-sm text-gray-600 mt-1">
              Refleksi retrospective agen lintas penugasan — bahan input mingguan untuk
              perbaiki prompt, tambah pattern wiki, dan fix bug bridge.
            </p>
          </div>
          <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1">
            {WINDOW_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={`px-3 py-1.5 text-sm rounded transition ${
                  days === opt.value
                    ? 'bg-primary text-white font-semibold'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {loading && (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500 text-sm">
            Memuat agregat feedback…
          </div>
        )}

        {!loading && agg && (
          <>
            {/* === KPI ROW === */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <KpiCard
                label="Total Feedback"
                value={agg.total_feedback}
                hint={`${days} hari terakhir`}
              />
              <KpiCard
                label="Confidence HIGH"
                value={agg.by_confidence.HIGH || 0}
                hint="Run lancar / no issue"
                accent="emerald"
              />
              <KpiCard
                label="Confidence MEDIUM"
                value={agg.by_confidence.MEDIUM || 0}
                hint="Ada hambatan"
                accent="amber"
              />
              <KpiCard
                label="Confidence LOW"
                value={agg.by_confidence.LOW || 0}
                hint="Hambatan serius"
                accent="red"
              />
            </div>

            {/* === BY AGENT === */}
            <Card title="Feedback per Agen">
              {Object.keys(agg.by_agent).length === 0 ? (
                <EmptyState text="Belum ada feedback dalam window ini." />
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(agg.by_agent).map(([agent, count]) => (
                    <div
                      key={agent}
                      className="border border-gray-200 rounded p-3 bg-gray-50"
                    >
                      <div className="text-xs text-gray-500 uppercase">
                        {AGENT_LABEL[agent] || agent}
                      </div>
                      <div className="text-2xl font-bold text-primary-dark">{count}</div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* === SEVERITY HEATMAP === */}
            <Card title="Severity Heatmap (Issue per Agen × Severity)">
              {heatmapAgents.length === 0 ? (
                <EmptyState text="Belum ada issue ter-report." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2 text-xs uppercase text-gray-600">Agen</th>
                        <th className="text-right p-2 text-xs uppercase text-gray-600">
                          Blocker
                        </th>
                        <th className="text-right p-2 text-xs uppercase text-gray-600">
                          Major
                        </th>
                        <th className="text-right p-2 text-xs uppercase text-gray-600">
                          Minor
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {heatmapAgents.map((agent) => {
                        const row = agg.severity_heatmap[agent] || {};
                        return (
                          <tr key={agent} className="border-t border-gray-100">
                            <td className="p-2 font-medium">
                              {AGENT_LABEL[agent] || agent}
                            </td>
                            <HeatCell value={row.blocker || 0} kind="blocker" />
                            <HeatCell value={row.major || 0} kind="major" />
                            <HeatCell value={row.minor || 0} kind="minor" />
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {/* === TOP WORKFLOW & SUBSTANSI === */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card title="Top 5 Workflow Issues">
                <IssueList items={agg.top_workflow_issues} />
              </Card>
              <Card title="Top 5 Substansi Issues">
                <IssueList items={agg.top_substansi_issues} />
              </Card>
            </div>

            {/* === TOP PATTERN SUGGESTIONS === */}
            <Card
              title="Top 5 Usulan Pattern Wiki Baru"
              subtitle="Usulan dari agen — kalau muncul ≥2 kali, pertimbangkan add ke wiki/temuan-patterns/"
            >
              {agg.top_pattern_suggestions.length === 0 ? (
                <EmptyState text="Belum ada usulan pattern." />
              ) : (
                <div className="space-y-3">
                  {agg.top_pattern_suggestions.map((p, i) => (
                    <div
                      key={i}
                      className="border border-gray-200 rounded p-3 bg-yellow-50/30"
                    >
                      <div className="flex justify-between items-start mb-1">
                        <div className="flex-1">
                          <div className="font-semibold text-sm text-gray-800">
                            {p.judul}
                          </div>
                          {p.id_proposed && (
                            <code className="text-xs text-gray-500">{p.id_proposed}</code>
                          )}
                        </div>
                        <span className="px-2 py-0.5 text-xs rounded bg-accent text-white font-mono">
                          ×{p.count}
                        </span>
                      </div>
                      {p.rationales.length > 0 && (
                        <ul className="mt-2 text-xs text-gray-600 list-disc list-inside space-y-1">
                          {p.rationales.map((r, j) => (
                            <li key={j}>{r}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* === RECENT FILES === */}
            <Card
              title="Feedback Terbaru"
              subtitle="Klik penugasan untuk drill-down ke file feedback mentah."
            >
              {!list || list.items.length === 0 ? (
                <EmptyState text="Belum ada file feedback." />
              ) : (
                <div className="overflow-x-auto -mx-5">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-5 py-2 text-xs uppercase text-gray-600">
                          Waktu
                        </th>
                        <th className="text-left px-2 py-2 text-xs uppercase text-gray-600">
                          Agen
                        </th>
                        <th className="text-left px-2 py-2 text-xs uppercase text-gray-600">
                          Conf
                        </th>
                        <th className="text-left px-2 py-2 text-xs uppercase text-gray-600">
                          Penugasan
                        </th>
                        <th className="text-left px-2 py-2 text-xs uppercase text-gray-600">
                          Ringkasan
                        </th>
                        <th className="text-right px-5 py-2 text-xs uppercase text-gray-600">
                          Issues
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.items.slice(0, 30).map((it, i) => (
                        <tr
                          key={i}
                          className="border-t border-gray-100 hover:bg-gray-50"
                        >
                          <td className="px-5 py-2 text-xs text-gray-600 whitespace-nowrap">
                            {formatTime(it.timestamp)}
                          </td>
                          <td className="px-2 py-2 text-xs">
                            {AGENT_LABEL[it.agent] || it.agent}
                          </td>
                          <td className="px-2 py-2">
                            <span
                              className={`px-2 py-0.5 text-xs rounded font-mono ${
                                CONFIDENCE_COLOR[it.confidence] ||
                                'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {it.confidence}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-xs">
                            {it.penugasan_id ? (
                              <Link
                                href={`/penugasan/${it.penugasan_id}`}
                                className="text-primary hover:underline"
                                title={it.penugasan_folder}
                              >
                                {it.penugasan_obyek.slice(0, 40) ||
                                  it.penugasan_folder.slice(0, 40)}
                              </Link>
                            ) : (
                              <span className="text-gray-500">{it.penugasan_folder}</span>
                            )}
                          </td>
                          <td className="px-2 py-2 text-xs text-gray-700">{it.summary}</td>
                          <td className="px-5 py-2 text-xs text-right whitespace-nowrap">
                            <span className="text-amber-700">W:{it.workflow_count}</span>{' '}
                            <span className="text-red-700">S:{it.substansi_count}</span>{' '}
                            <span className="text-blue-700">P:{it.pattern_count}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {list.items.length > 30 && (
                    <div className="px-5 py-2 text-xs text-gray-500 italic">
                      Menampilkan 30 dari {list.items.length} file. Persempit window untuk lihat lebih spesifik.
                    </div>
                  )}
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </AppShell>
  );
}

// ============================================================
// Helper components
// ============================================================

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-200 bg-gray-50">
        <h2 className="font-semibold text-primary-dark">{title}</h2>
        {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
  accent = 'gray',
}: {
  label: string;
  value: number;
  hint?: string;
  accent?: 'gray' | 'emerald' | 'amber' | 'red';
}) {
  const accentMap = {
    gray: 'text-primary-dark',
    emerald: 'text-emerald-700',
    amber: 'text-amber-700',
    red: 'text-red-700',
  } as const;
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className={`text-3xl font-bold mt-1 ${accentMap[accent]}`}>{value}</div>
      {hint && <div className="text-xs text-gray-500 mt-1">{hint}</div>}
    </div>
  );
}

function HeatCell({ value, kind }: { value: number; kind: 'blocker' | 'major' | 'minor' }) {
  if (value === 0) {
    return <td className="p-2 text-right text-gray-300">—</td>;
  }
  const cls = SEVERITY_COLOR[kind];
  return (
    <td className="p-2 text-right">
      <span className={`inline-block min-w-[2.5rem] px-2 py-0.5 text-xs rounded border font-mono ${cls}`}>
        {value}
      </span>
    </td>
  );
}

function IssueList({
  items,
}: {
  items: Array<{ category: string; severity: string; count: number; examples: string[] }>;
}) {
  if (items.length === 0) {
    return <EmptyState text="Belum ada issue ter-report." />;
  }
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <div key={i} className="border-l-4 pl-3 py-1 border-gray-300">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-xs text-gray-700">{it.category}</span>
            <span
              className={`px-2 py-0.5 text-xs rounded border ${
                SEVERITY_COLOR[it.severity] || 'bg-gray-100 text-gray-700 border-gray-300'
              }`}
            >
              {it.severity}
            </span>
            <span className="ml-auto text-xs font-mono text-gray-600">×{it.count}</span>
          </div>
          {it.examples.length > 0 && (
            <ul className="text-xs text-gray-600 list-disc list-inside space-y-0.5">
              {it.examples.map((ex, j) => (
                <li key={j}>{ex}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="text-sm text-gray-500 italic text-center py-3">{text}</div>;
}
