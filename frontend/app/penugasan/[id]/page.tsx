'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api, getSession, Dokumen, Penugasan, Role, Session, GateStatus } from '@/lib/api';
import { AppShell } from '@/components/AppShell';
import { HeroPenugasan } from '@/components/HeroPenugasan';
import { TemplatePickerKpPkp } from '@/components/TemplatePickerKpPkp';

// NAVIGASI = KARTU TAHAPAN (ala SIMWAS "Detail Pelaksanaan Penugasan").
// Tidak ada tab bar terpisah — klik kartu tahapan di hero membuka workspace
// tahapan itu di bawahnya. v7 hanya engine; struktur halaman mengikuti SIMWAS.
//   0 Survey (audit-*) · 1 KP (PT) · 2 PKP (KT) · 3 KKP (workspace AT)
//   4 LRS KK · 5 Konsep Laporan (workspace KT) · 6 LRS LHP (PT/PM) · 7 Laporan Hasil

// Tahapan default sesuai peran — buka langsung di tahapan tanggung jawabnya.
function defaultStageForRole(role: Role): number {
  if (role === 'PT') return 1; // Kartu Penugasan
  if (role === 'KT') return 2; // PKP
  if (role === 'AT') return 3; // KKP
  return 6; // PM → LRS LHP
}

export default function DetailPenugasanPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  // Hydration-safe: jangan baca localStorage saat render — server-render tidak
  // tahu session, jadi awalnya null lalu di-set di useEffect setelah mount.
  const [session, setSession] = useState<Session | null>(null);
  const [mounted, setMounted] = useState(false);

  const [penugasan, setPenugasan] = useState<Penugasan | null>(null);
  const [dokumen, setDokumen] = useState<Dokumen[]>([]);
  const [stage, setStage] = useState<number>(3);
  const [error, setError] = useState<string | null>(null);
  // Status reviu konsep LHP terbaru (S3.2) — dipakai HeroPenugasan untuk tahapan 6.
  const [lhpStatus, setLhpStatus] = useState<'APPROVED' | 'NEEDS_REVISION' | null>(null);
  // Prefill chat dari tombol "Jalankan Gate" di panel evaluasi bertahap. token
  // memaksa ChatTab remount agar prompt awal terisi ulang tiap klik gate.
  const [chatSeed, setChatSeed] = useState<{ prompt: string; token: number } | null>(null);
  const runGateInChat = (gateId: string) => {
    setChatSeed({ prompt: `[MODE:GATE:${gateId}]`, token: Date.now() });
    setStage(3); // gate dijalankan agen AT di tahapan 3 (KKP)
  };

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSession(s);
    if (!s) {
      router.push('/login');
      return;
    }
    // Reset semua state lokal sebelum fetch — penting saat pindah ke penugasan lain,
    // supaya UI lama (dokumen list, error message) tidak ter-display sebentar selama fetch.
    setPenugasan(null);
    setDokumen([]);
    setError(null);
    setLhpStatus(null);
    setStage(defaultStageForRole(s.role_aktif));
    Promise.all([api.getPenugasan(id), api.listDokumen(id)])
      .then(([p, d]) => {
        setPenugasan(p);
        setDokumen(d);
      })
      .catch((e) => setError(e.message));
    // Status reviu LHP — opsional, abaikan error (fitur tahapan 6).
    api.listLhpReview(id).then((r) => setLhpStatus(r.latest_status)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Poll status dokumen setiap 3 detik selama ada yang masih INGESTING.
  // Berhenti otomatis saat semua sudah READY/FAILED — tidak ada request sia-sia.
  useEffect(() => {
    const hasIngesting = dokumen.some((d) => d.status === 'INGESTING');
    if (!hasIngesting) return;
    const timer = setInterval(async () => {
      try {
        const updated = await api.listDokumen(id);
        setDokumen(updated);
      } catch {
        // abaikan error network sementara — polling akan coba lagi
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [dokumen, id]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>, jenis?: string) => {
    const files = e.target.files;
    if (!files) return;
    for (const f of Array.from(files)) {
      try {
        const d = await api.uploadDokumen(id, f, jenis || undefined);
        setDokumen((prev) => [...prev, d]);
      } catch (err: any) {
        setError(err.message);
      }
    }
    e.target.value = '';
  };

  const handleDeleteDokumen = async (d: Dokumen) => {
    if (
      !confirm(
        `Hapus dokumen "${d.nama_file}"?\n\nFile + hasil ekstraksi akan dihapus. Karena dokumen berubah, hasil analisis KKP/LHP yang lama akan di-reset agar bisa dianalisis ulang.`
      )
    )
      return;
    try {
      await api.deleteDokumen(d.id);
      setDokumen((prev) => prev.filter((x) => x.id !== d.id));
    } catch (e: any) {
      setError(e.message);
    }
  };

  // SSR + first client render: kembalikan shell kosong supaya HTML konsisten.
  if (!mounted) return <main className="min-h-screen" />;
  if (!session || !penugasan) return null;

  const allReady = dokumen.length > 0 && dokumen.every((d) => d.status === 'READY');

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-sm text-gray-500 mb-2">INTEGRAL / Penugasan / Detail Pelaksanaan</div>

        {/* Hero = navigasi utama (ala SIMWAS): info penugasan + grid tahapan.
            Klik kartu tahapan → konten tahapan itu tampil di bawah. */}
        <HeroPenugasan
          penugasan={penugasan}
          lhpReviewStatus={lhpStatus}
          activeStage={stage}
          onStageSelect={(n) => setStage(n)}
        />
      </div>

      <div className="max-w-6xl mx-auto px-6 pb-6">
        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Panel evaluasi bertahap — tampil hanya untuk skill gated (SPIP/SAKIP/RB) */}
        <GatePanel penugasanId={id} skill={penugasan.skill} role={session.role_aktif} onRunGate={runGateInChat} />

        {/* key={id} memaksa React unmount + remount setiap kali penugasan ganti,
            mencegah state lokal (chat prompt, modal preview, dll) bocor antar penugasan. */}

        {/* === Tahapan 0 — Survey Pendahuluan (hanya audit-*) === */}
        {stage === 0 && (
          <div key={`s0-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="🔎 Tahapan 0 — Survey Pendahuluan (khusus audit)"
              steps={['Upload bahan survey (jenis SURVEY)', 'KT susun profil risiko 3E', 'Turunkan ke sasaran PKP']}
            />
            <DokumenTab
              dokumen={dokumen}
              onUpload={handleUpload}
              onDelete={handleDeleteDokumen}
              allReady={allReady}
              role={session.role_aktif}
              skill={penugasan.skill}
            />
          </div>
        )}

        {/* === Tahapan 1 — Kartu Penugasan (PT isi dari template wiki) === */}
        {stage === 1 && (
          <KpTab key={`s1-${id}`} penugasan={penugasan} role={session.role_aktif} />
        )}

        {/* === Tahapan 2 — PKP: sasaran + langkah kerja (KT, detail dari KP) === */}
        {stage === 2 && (
          <div key={`s2-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="📋 Tahapan 2 — PKP (Program Kerja Pengawasan) — diisi Ketua Tim"
              steps={['Detailkan KP jadi sasaran', 'Susun langkah kerja', 'Assign anggota tim']}
            />
            <SetupPenugasanTab
              penugasanId={id}
              role={session.role_aktif}
              currentUserName={session.user.nama_lengkap}
              section="sasaran"
              skill={penugasan.skill}
            />
          </div>
        )}

        {/* === Tahapan 3 — KKP, workspace AT: konteks → dokumen → AI → HITL === */}
        {stage === 3 && (
          <div key={`s3-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="🎯 Tahapan 3 — Kertas Kerja (KKP) — workspace Anggota Tim"
              steps={['Generate Konteks', 'Upload Dokumen', 'Analisis AI', 'Review & Approval Temuan']}
            />
            <SetupPenugasanTab
              penugasanId={id}
              role={session.role_aktif}
              currentUserName={session.user.nama_lengkap}
              section="context"
            />
            <DokumenTab
              dokumen={dokumen}
              onUpload={handleUpload}
              onDelete={handleDeleteDokumen}
              allReady={allReady}
              role={session.role_aktif}
              skill={penugasan.skill}
            />
            <ChatTab
              key={`chat-at-${id}-${chatSeed?.token ?? 0}`}
              penugasanId={id}
              role="AT"
              skill={penugasan.skill}
              seedPrompt={chatSeed?.prompt}
            />
          </div>
        )}

        {/* === Tahapan 4 — LRS KK: status review/approval temuan (auto dari HITL) === */}
        {stage === 4 && (
          <div key={`s4-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="📝 Tahapan 4 — LRS Kertas Kerja (auto dari approval HITL)"
              steps={['Temuan di-approve AT/KT di tahapan 3', 'Status review = LRS KK', 'KT setujui semua sasaran → status KKP_DONE → Tahapan 5 terbuka']}
            />
            <TemuanReviewPanel penugasanId={id} key={`lrs-${id}`} />
            {session?.role_aktif === 'KT' && (
              <SasaranApprovalPanel
                penugasanId={id}
                key={`sap-${id}`}
                onSaved={() => {
                  api.getPenugasan(id).then(p => setPenugasan(p)).catch(() => {});
                }}
              />
            )}
          </div>
        )}

        {/* === Tahapan 5 — Konsep Laporan, workspace KT: generate LHP + approval === */}
        {stage === 5 && (
          <div key={`s5-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="📄 Tahapan 5 — Konsep Laporan (LHP) — workspace Ketua Tim"
              steps={['Generate Draft LHP (AI) via chat', 'Unduh & periksa hasil laporan di bawah', 'Kirim ke PT/PM untuk LRS LHP']}
            />
            <ChatTab
              key={`chat-kt-${id}`}
              penugasanId={id}
              role="KT"
              skill={penugasan.skill}
            />
            <LhpFilesPanel penugasanId={id} key={`lhp-files-kt-${id}`} />
          </div>
        )}

        {/* === Tahapan 6 — LRS LHP: PT/PM approve / minta revisi konsep === */}
        {stage === 6 && (
          <div key={`s6-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="🛡 Tahapan 6 — LRS LHP — reviu Pengendali Teknis / Mutu"
              steps={['Unduh & baca konsep LHP di bawah', 'Setujui atau minta revisi + catatan', 'Approved → lanjut finalisasi']}
            />
            <LhpFilesPanel penugasanId={id} key={`lhp-files-pt-${id}`} />
            <LhpReviewPanel
              penugasanId={id}
              role={session.role_aktif}
              onReviewed={(s) => setLhpStatus(s)}
            />
          </div>
        )}

        {/* === Tahapan 7 — Laporan Hasil: file output final === */}
        {stage === 7 && (
          <div key={`s7-${id}`} className="space-y-6">
            <WorkspaceBanner
              title="📁 Tahapan 7 — Laporan Hasil"
              steps={['Unduh KKP/LHP/QC', 'Finalisasi oleh Inspektur (via SIMWAS)']}
            />
            <OutputTab penugasan={penugasan} />
          </div>
        )}
      </div>
    </AppShell>
  );
}

// Banner ringkas urutan langkah di atas workspace per-peran (Fase A).
function WorkspaceBanner({ title, steps }: { title: string; steps: string[] }) {
  return (
    <div className="integral-card p-4 bg-primary-50/40 border-primary-100">
      <div className="font-semibold text-sm text-primary-dark mb-2">{title}</div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {steps.map((s, i) => (
          <span key={s} className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded-full bg-white border border-primary-100 text-primary-dark">
              {i + 1}. {s}
            </span>
            {i < steps.length - 1 && <span className="text-gray-300">→</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

function KpField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-gray-400 text-[10px] uppercase mb-0.5">{label}</div>
      <div className="text-gray-800">{value}</div>
    </div>
  );
}

// ============================================================
// KP TAB — Kartu Penugasan, FIELD PERSIS FORM INTEGRAL (hasil bedah live
// simwasv2 10 Jun 2026): nomor, judul, dasar, aktivitas_tingkat_risiko,
// tujuan, ruang_lingkup, sasaran[] (repeatable), tanggal + disusun_oleh.
// Bisa isi manual atau prefill dari template wiki (tujuan/ruang lingkup/
// dasar baku skill). Sasaran KP otomatis sync ke PKP (sasaran-assignment)
// — meniru INTEGRAL: bagian "II. Pelaksanaan" PKP dibangun dari sasaran KP.
// ============================================================

// Urutan & label field mengikuti form INTEGRAL.
const KP_FIELD_DEFS: Array<{ key: string; label: string; multiline: boolean; ph: string }> = [
  { key: 'nomor', label: 'Nomor Kartu', multiline: false, ph: 'KP/93/IJ.3/KP.01.06/05/2026' },
  { key: 'judul', label: 'Judul Pengawasan', multiline: true, ph: 'Isikan Judul Pengawasan' },
  { key: 'dasar', label: 'Dasar Pengawasan', multiline: true, ph: 'Isikan Dasar Pengawasan (PKPT, ST, dll — boleh daftar a/b/c)' },
  { key: 'aktivitas_tingkat_risiko', label: 'Tingkat Risiko Unit/Aktivitas', multiline: true, ph: 'Isikan Tingkat Risiko Unit/Aktivitas' },
  { key: 'tujuan', label: 'Tujuan Pengawasan', multiline: true, ph: 'Isikan Tujuan Pengawasan' },
  { key: 'ruang_lingkup', label: 'Ruang Lingkup Pengawasan', multiline: true, ph: 'Isikan Ruang Lingkup Pengawasan' },
];

/** Ambil isi teks satu section (## Heading) dari body template wiki —
 * baris placeholder {{...}} dibuang. Untuk prefill tujuan/ruang lingkup/
 * dasar baku skill dari template. */
function extractTemplateSection(body: string, heading: RegExp): string {
  const lines = body.split('\n');
  const i = lines.findIndex((l) => /^#{1,6}\s/.test(l) && heading.test(l));
  if (i === -1) return '';
  const out: string[] = [];
  for (let j = i + 1; j < lines.length; j++) {
    const l = lines[j];
    if (/^#{1,6}\s/.test(l)) break;
    if (l.includes('{{') || l.includes('}}')) continue;
    out.push(l);
  }
  return out.join('\n').trim();
}

/** Render markdown Kartu Penugasan — layout mengikuti dokumen KP INTEGRAL. */
function renderKpMarkdown(fields: Record<string, string>, sasaran: string[]): string {
  const v = (k: string) => (fields[k] || '').trim() || '[DIISI AUDITOR]';
  const sasaranMd = sasaran.filter((s) => s.trim()).length
    ? sasaran.filter((s) => s.trim()).map((s, i) => `${i + 1}. ${s.trim()}`).join('\n')
    : '[DIISI AUDITOR]';
  return `# KARTU PENUGASAN

**Nomor**: ${v('nomor')}

## Judul Pengawasan

${v('judul')}

## Dasar Pengawasan

${v('dasar')}

## Tingkat Risiko Unit/Aktivitas

${v('aktivitas_tingkat_risiko')}

## Tujuan Pengawasan

${v('tujuan')}

## Ruang Lingkup Pengawasan

${v('ruang_lingkup')}

## Sasaran Pengawasan

${sasaranMd}

---

Jakarta, ${v('tanggal')}

Disusun oleh: ${v('disusun_oleh')}
`;
}

function KpTab({ penugasan, role }: { penugasan: Penugasan; role: Role }) {
  const canEdit = role === 'PT' || role === 'KT';
  const [fields, setFields] = useState<Record<string, string>>({});
  const [sasaran, setSasaran] = useState<string[]>([]);
  const [users, setUsers] = useState<string[]>([]);
  const [templateSlug, setTemplateSlug] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showTpl, setShowTpl] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [r, allUsers] = await Promise.all([
          api.getKpMd(penugasan.id),
          api.listUsers().catch(() => []),
        ]);
        setUsers(allUsers.map((u) => u.nama_lengkap));
        // Prefill ala INTEGRAL: nomor auto dari nomor ST, judul dari ST,
        // tanggal hari ini. Nilai tersimpan menang.
        const today = new Date().toISOString().slice(0, 10);
        const base: Record<string, string> = {
          nomor: penugasan.nomor_st ? `KP/${penugasan.nomor_st}` : '',
          judul: penugasan.obyek || '',
          tanggal: today,
        };
        setFields({ ...base, ...(r.fields || {}) });
        setSasaran(r.sasaran && r.sasaran.length ? r.sasaran : ['']);
        setTemplateSlug(r.template_slug);
      } catch (e: any) {
        setErr(e.message);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasan.id]);

  // Template wiki → prefill tujuan/ruang lingkup/dasar baku skill (hanya ke
  // field yang masih kosong — isian manual PT tidak ditimpa).
  const useTemplate = (t: { slug: string; body: string; meta: Record<string, any> }) => {
    const sections: Array<[string, RegExp]> = [
      ['tujuan', /tujuan/i],
      ['ruang_lingkup', /ruang lingkup/i],
      ['dasar', /dasar|referensi regulasi/i],
    ];
    setFields((prev) => {
      const next = { ...prev };
      for (const [key, re] of sections) {
        if (!(next[key] || '').trim()) {
          const text = extractTemplateSection(t.body, re);
          if (text) next[key] = text;
        }
      }
      return next;
    });
    setTemplateSlug(t.slug);
    setShowTpl(false);
  };

  const setF = (k: string, v: string) => setFields((p) => ({ ...p, [k]: v }));
  const setSasaranAt = (i: number, v: string) =>
    setSasaran((p) => p.map((s, j) => (j === i ? v : s)));
  const cleanSasaran = sasaran.map((s) => s.trim()).filter(Boolean);
  const rendered = renderKpMarkdown(fields, sasaran);
  const missing = KP_FIELD_DEFS.filter((d) => !(fields[d.key] || '').trim()).map((d) => d.label);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const res = await api.saveKpMd(penugasan.id, rendered, fields, cleanSasaran, templateSlug);
      setSaveMsg(
        res.sasaran_synced_to_pkp > 0
          ? `Tersimpan ✓ — ${res.sasaran_synced_to_pkp} sasaran ditambahkan ke PKP (tahapan 2)`
          : 'Tersimpan ✓'
      );
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="bg-white p-5 rounded-lg text-sm text-gray-500">Memuat Kartu Penugasan…</div>;
  }

  return (
    <div className="space-y-6">
      <WorkspaceBanner
        title="📇 Tahapan 1 — Kartu Penugasan (KP) — diisi Pengendali Teknis"
        steps={['Tarik ST dari SIMWAS', 'Isi manual / pakai template wiki', 'Daftar Sasaran Pengawasan', 'Simpan → sasaran masuk PKP']}
      />

      {/* ST — read-only, sumber SIMWAS (akan terisi via sync ST, Fase C) */}
      <div className="integral-card p-4">
        <div className="text-xs uppercase text-gray-400 tracking-wider mb-2">Surat Tugas (sumber: SIMWAS)</div>
        <div className="grid md:grid-cols-2 gap-3 text-sm">
          <KpField label="Nomor ST" value={penugasan.nomor_st || '[belum ditarik dari SIMWAS]'} />
          <KpField label="Tanggal ST" value={penugasan.tanggal_st || '—'} />
          <KpField label="Obyek" value={penugasan.obyek} />
          <KpField label="Jenis Pengawasan" value={penugasan.skill} />
        </div>
      </div>

      {err && (
        <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">{err}</div>
      )}

      {canEdit && (
        <div className="integral-card p-4">
          <button onClick={() => setShowTpl((v) => !v)} className="text-sm text-primary font-medium">
            {showTpl ? '▾' : '▸'} Pakai Template KP dari Wiki
            <span className="ml-2 text-[11px] text-gray-400 font-normal">
              mengisi Tujuan / Ruang Lingkup / Dasar baku skill ke field yang masih kosong
            </span>
            {templateSlug && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-primary-50 text-primary text-[11px] font-mono">
                {templateSlug}
              </span>
            )}
          </button>
          {showTpl && (
            <div className="mt-3">
              <TemplatePickerKpPkp kind="kp" skill={penugasan.skill} onUse={useTemplate} />
            </div>
          )}
        </div>
      )}

      {/* Form — field persis INTEGRAL */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">KARTU PENUGASAN</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {canEdit ? 'Field mengikuti form INTEGRAL SIMWAS.' : 'Read-only — diisi Pengendali Teknis / Ketua Tim.'}
            </p>
          </div>
          {canEdit && (
            <div className="flex items-center gap-2">
              {missing.length > 0 && (
                <span className="text-[11px] text-amber-700" title={missing.join(', ')}>
                  ⚠ {missing.length} field kosong
                </span>
              )}
              {saveMsg && <span className="text-[11px] text-emerald-700">{saveMsg}</span>}
              <button
                onClick={save}
                disabled={saving}
                className="px-3 py-1.5 rounded bg-primary text-white text-sm font-semibold disabled:opacity-50"
              >
                {saving ? 'Menyimpan…' : 'Simpan KP'}
              </button>
            </div>
          )}
        </div>

        <div className="p-5 space-y-4">
          {KP_FIELD_DEFS.map((d) => (
            <div key={d.key} className="grid md:grid-cols-4 gap-2 items-start">
              <label className="text-sm text-gray-600 md:pt-2">{d.label}</label>
              <div className="md:col-span-3">
                {d.multiline ? (
                  <textarea
                    value={fields[d.key] || ''}
                    onChange={(e) => setF(d.key, e.target.value)}
                    disabled={!canEdit}
                    rows={d.key === 'judul' ? 2 : 3}
                    placeholder={d.ph}
                    className="block w-full border border-gray-300 rounded-md px-3 py-2 text-sm disabled:bg-gray-50"
                  />
                ) : (
                  <input
                    value={fields[d.key] || ''}
                    onChange={(e) => setF(d.key, e.target.value)}
                    disabled={!canEdit}
                    placeholder={d.ph}
                    className="block w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono disabled:bg-gray-50"
                  />
                )}
              </div>
            </div>
          ))}

          {/* Sasaran Pengawasan — repeatable, persis INTEGRAL */}
          <div className="grid md:grid-cols-4 gap-2 items-start">
            <label className="text-sm text-gray-600 md:pt-2">Sasaran Pengawasan</label>
            <div className="md:col-span-3 space-y-2">
              {sasaran.map((s, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    value={s}
                    onChange={(e) => setSasaranAt(i, e.target.value)}
                    disabled={!canEdit}
                    placeholder="Isikan Sasaran Pengawasan"
                    className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm disabled:bg-gray-50"
                  />
                  {canEdit && sasaran.length > 1 && (
                    <button
                      onClick={() => setSasaran((p) => p.filter((_, j) => j !== i))}
                      className="px-2.5 rounded border border-red-200 text-red-600 hover:bg-red-50"
                      title="Hapus sasaran"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
              {canEdit && (
                <button
                  onClick={() => setSasaran((p) => [...p, ''])}
                  className="px-3 py-1.5 text-sm rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                >
                  + Tambah Sasaran
                </button>
              )}
              <p className="text-[11px] text-gray-400">
                Saat Simpan, sasaran otomatis masuk ke PKP (tahapan 2) sebagai bagian II. Pelaksanaan.
              </p>
            </div>
          </div>

          {/* Footer: Jakarta, tanggal + Disusun Oleh — persis INTEGRAL */}
          <div className="border-t border-dashed border-gray-300 pt-4 flex flex-wrap justify-end items-center gap-3 text-sm">
            <span className="text-gray-600">Jakarta,</span>
            <input
              type="date"
              value={fields.tanggal || ''}
              onChange={(e) => setF('tanggal', e.target.value)}
              disabled={!canEdit}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm disabled:bg-gray-50"
            />
            <span className="text-gray-600">Disusun Oleh:</span>
            <select
              value={fields.disusun_oleh || ''}
              onChange={(e) => setF('disusun_oleh', e.target.value)}
              disabled={!canEdit}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm bg-white disabled:bg-gray-50"
            >
              <option value="">Pilih Nama Pegawai</option>
              {users.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
        </div>

        <details className="border-t border-gray-100">
          <summary className="px-5 py-2.5 text-xs text-gray-500 cursor-pointer hover:text-primary">
            Lihat preview Kartu Penugasan (markdown yang disimpan — dibaca agen saat Generate Konteks)
          </summary>
          <pre className="px-5 pb-4 text-[11px] whitespace-pre-wrap font-mono text-gray-700 max-h-72 overflow-y-auto">
            {rendered}
          </pre>
        </details>
      </div>
    </div>
  );
}

// Pilihan jenis dokumen per kelompok skill (untuk dropdown upload). Default
// "(auto)" = backend klasifikasi dari nama file.
const PBJ_SKILLS = ['reviu-pengadaan', 'audit-pengadaan', 'pemantauan-pengadaan', 'konsultasi-pengadaan'];
// Audit-* punya tahapan 0 Survey Pendahuluan → boleh unggah dokumen jenis SURVEY.
const AUDIT_SKILLS = ['audit-pengadaan', 'audit-kinerja', 'audit-umum'];
function jenisOptionsFor(skill: string): string[] {
  let base: string[];
  if (skill === 'reviu-rka-kl') base = ['TOR', 'RAB', 'KP', 'PKP', 'ST', 'OTHER'];
  else if (PBJ_SKILLS.includes(skill)) base = ['KAK', 'HPS', 'RFI', 'KONTRAK', 'KP', 'PKP', 'ST', 'OTHER'];
  // criteria-driven (audit-kinerja, evaluasi-*, *-umum, kepatuhan-saipi, dll)
  else base = ['KRITERIA', 'OBJEK', 'KP', 'PKP', 'ST', 'OTHER'];
  // Tahapan 0: bahan Survey Pendahuluan didahulukan untuk skill audit-*.
  return AUDIT_SKILLS.includes(skill) ? ['SURVEY', ...base] : base;
}

function DokumenTab({
  dokumen,
  onUpload,
  allReady,
  role,
  onDelete,
  skill,
}: {
  dokumen: Dokumen[];
  onUpload: (e: React.ChangeEvent<HTMLInputElement>, jenis?: string) => void;
  allReady: boolean;
  role: Role;
  onDelete: (d: Dokumen) => void;
  skill: string;
}) {
  const canUpload = role === 'AT';
  const [jenis, setJenis] = useState('');
  const isCriteriaDriven = skill !== 'reviu-rka-kl' && !PBJ_SKILLS.includes(skill);
  const isAudit = AUDIT_SKILLS.includes(skill);
  const opts = jenisOptionsFor(skill);
  return (
    <div>
      {isAudit && (
        <div className="mb-3 p-3 rounded bg-violet-50 border border-violet-200 text-violet-900 text-xs">
          🔎 <strong>Tahapan 0 — Survey Pendahuluan</strong>: unggah bahan survey (Memo SP, hasil
          entry/entry meeting, profil auditi awal) dengan jenis <strong>SURVEY</strong> atau awali
          nama file <code className="bg-violet-100 px-1 rounded">survey-</code>. Ketua Tim memakainya
          untuk menyusun <strong>profil risiko 3E</strong> sebelum merumuskan sasaran.
        </div>
      )}
      <div className="mb-4 p-3 rounded bg-amber-50 border border-amber-200 text-amber-900 text-xs">
        {isCriteriaDriven ? (
          <>
            📎 Skill <strong>{skill}</strong> bersifat <strong>criteria-driven</strong>: unggah dokumen
            <strong> KRITERIA</strong> (regulasi/SOP/juknis acuan) dan <strong>OBJEK</strong> (dokumen yang
            diperiksa). Pilih jenis di dropdown, atau awali nama file dengan
            <code className="bg-amber-100 px-1 rounded">kriteria-</code>/<code className="bg-amber-100 px-1 rounded">objek-</code>.
            Sertakan juga <strong>KP/PKP</strong> agar QC SAIPI tidak BLOKIR.
          </>
        ) : (
          <>
            📎 <strong>Wajib untuk QC SAIPI:</strong> upload juga <strong>KP</strong> (Kartu Penugasan) dan
            <strong> PKP</strong> (Program Kerja Pengawasan) dari INTEGRAL sebelum analisis — tanpa keduanya
            QC <strong>BLOKIR</strong> (REN-001/REN-002). Awali nama file
            <code className="bg-amber-100 px-1 rounded">KP</code> / <code className="bg-amber-100 px-1 rounded">PKP</code>.
          </>
        )}
      </div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-primary-dark">Dokumen Penugasan</h2>
        <div className="flex gap-2 items-center">
          {canUpload ? (
            <>
              <select
                value={jenis}
                onChange={(e) => setJenis(e.target.value)}
                title="Jenis dokumen untuk file yang diunggah berikutnya"
                className="border border-gray-300 rounded-md px-2 py-2 text-sm bg-white"
              >
                <option value="">(auto dari nama file)</option>
                {opts.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
              <label className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold cursor-pointer hover:bg-primary-dark">
                + Upload
                <input type="file" multiple onChange={(e) => onUpload(e, jenis)} className="hidden" />
              </label>
            </>
          ) : (
            <span className="px-4 py-2 rounded bg-gray-100 text-gray-500 text-sm">
              🔒 Upload hanya oleh Anggota Tim (AT)
            </span>
          )}
        </div>
      </div>

      {dokumen.length === 0 ? (
        <div className="bg-white border border-dashed border-gray-300 rounded-lg p-10 text-center text-gray-500">
          {!canUpload
            ? 'Belum ada dokumen. AT yang akan upload bukti pendukung setelah KT setup sasaran selesai.'
            : isCriteriaDriven
            ? 'Belum ada dokumen. Unggah dokumen KRITERIA (regulasi/SOP acuan) + OBJEK (yang diperiksa).'
            : skill === 'reviu-rka-kl'
            ? 'Belum ada dokumen. Upload TOR/RAB (Reviu RKA-K/L).'
            : 'Belum ada dokumen. Upload KAK/HPS/RFI/Kontrak (Pengadaan).'}
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
                {canUpload && <th className="text-left p-3 text-xs uppercase text-gray-600">Aksi</th>}
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
                  {canUpload && (
                    <td className="p-3">
                      <button
                        onClick={() => onDelete(d)}
                        className="text-red-600 hover:text-red-800 hover:underline text-xs"
                        title="Hapus dokumen (file + hasil ingest, reset analisis)"
                      >
                        Hapus
                      </button>
                    </td>
                  )}
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
  seedPrompt,
}: {
  penugasanId: number;
  role: string;
  skill: string;
  seedPrompt?: string;
}) {
  const [prompt, setPrompt] = useState(
    seedPrompt ??
      (role === 'AT'
        ? `Mulai analisis ${skill} untuk penugasan ini. Jalankan pipeline V6 dan verifikasi anomali.`
        : 'Susun draft LHR dari temuan.json yang sudah disetujui anggota tim.')
  );
  const [running, setRunning] = useState(false);
  // reconnected = run ini ditemukan masih berjalan di backend (bukan baru dimulai
  // di tab ini), mis. setelah pindah tab / reload. Dipakai untuk banner.
  const [reconnected, setReconnected] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [history, setHistory] = useState<AgentRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  // Live streaming state — text & tool_use chip yang sedang ter-stream.
  const [streamText, setStreamText] = useState('');
  const [streamTools, setStreamTools] = useState<Array<{ tool: string; input: any }>>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const esRef = useRef<EventSource | null>(null);

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

  // Cleanup: tutup EventSource saat unmount / penugasan ganti supaya tidak ada
  // koneksi nyangkut di latar setelah pindah halaman.
  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [penugasanId, agent]);

  // Auto-scroll ke bawah setelah history loaded, stream update, atau run selesai
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, running, streamText, streamTools]);

  // Streaming via Server-Sent Events. Run jalan di BACKGROUND TASK backend —
  // koneksi SSE hanya jendela ke buffer event. Disconnect (pindah tab) TIDAK
  // menghentikan run; saat kembali kita /attach untuk lanjut melihat.
  // Event: start, text, tool_use, tool_result, done, error, idle.
  const consumeStream = (url: string, opts: { isAttach: boolean }) => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    // Untuk start (klik user) → langsung running. Untuk attach (probe) → tunggu
    // event `start` dari backend supaya tidak flicker "running" saat sebenarnya idle.
    setRunning(!opts.isAttach);
    setReconnected(opts.isAttach);
    // Pada attach, backend me-replay buffer dari awal → mulai dari teks kosong
    // supaya tidak dobel dengan sisa stream sebelumnya.
    setStreamText('');
    setStreamTools([]);
    setElapsed(0);
    const startTime = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);

    let gotError: string | null = null;
    let finished = false;
    const es = new EventSource(url);
    esRef.current = es;

    const teardown = () => {
      clearInterval(timer);
      if (esRef.current === es) esRef.current = null;
      es.close();
    };

    const finalize = async () => {
      if (finished) return;
      finished = true;
      teardown();
      setRunning(false);
      setReconnected(false);
      try {
        const res = await api.getAgentHistory(agent as any, penugasanId);
        setHistory(res.runs);
      } catch {
        // abaikan; history bisa di-refresh manual
      }
      setStreamText('');
      setStreamTools([]);
    };

    es.addEventListener('idle', () => {
      // Tidak ada run aktif di backend (hanya muncul di jalur /attach).
      finished = true;
      teardown();
      setRunning(false);
      setReconnected(false);
    });

    es.addEventListener('start', () => {
      // Ada run aktif (penting untuk jalur attach: tandai running).
      setRunning(true);
    });

    es.addEventListener('text', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.text) setStreamText((prev) => prev + data.text);
      } catch {
        // ignore
      }
    });

    es.addEventListener('tool_use', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data);
        setStreamTools((prev) => [...prev, { tool: data.tool, input: data.input }]);
      } catch {
        // ignore
      }
    });

    es.addEventListener('tool_result', () => {
      // Tool result hanya untuk audit trail — sudah ter-log di tool_calls.
    });

    es.addEventListener('error', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data);
        gotError = data.message || 'Stream error';
      } catch {
        gotError = 'Koneksi SSE putus';
      }
      finalize();
    });

    es.addEventListener('done', () => finalize());

    // onerror tanpa retry. Penting: saat kita SENGAJA detach (pindah tab/Stop),
    // jangan tandai gagal — run tetap jalan di backend.
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED && !finished) {
        finalize();
      }
    };
  };

  const start = () => {
    if (running) return;
    const url = api.agentStreamUrl(agent as any, penugasanId, prompt);
    consumeStream(url, { isAttach: false });
  };

  // "Stop" sekarang = LEPAS jendela (run tetap jalan di backend). Untuk lihat
  // lagi, buka tab Chat → otomatis reconnect.
  const detach = () => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setRunning(false);
    setReconnected(false);
    setStreamText('');
    setStreamTools([]);
  };

  // Saat mount (atau pindah ke penugasan/role lain): reconnect ke run aktif di
  // backend bila ada (mis. ditinggal pindah tab). Kalau tidak ada → event idle.
  useEffect(() => {
    const url = api.agentAttachUrl(agent as any, penugasanId);
    consumeStream(url, { isAttach: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasanId, agent]);

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
          <div className="border border-blue-200 bg-blue-50/40 rounded p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-blue-700">
                <span className="inline-block w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></span>
                <span className="text-sm font-semibold">
                  {reconnected
                    ? 'Analisis masih berjalan di backend — dilanjutkan otomatis'
                    : `Agen sedang streaming… (${elapsed}s)`}
                </span>
              </div>
              <span className="text-xs text-gray-500">
                {streamTools.length > 0 ? `${streamTools.length} tool call(s)` : 'menunggu output…'}
              </span>
            </div>
            {streamText && (
              <div className="text-sm whitespace-pre-wrap text-gray-800 bg-white border border-gray-200 rounded p-2 mb-2 max-h-[300px] overflow-y-auto">
                {streamText}
                <span className="inline-block w-2 h-4 bg-blue-600 align-middle ml-0.5 animate-pulse" />
              </div>
            )}
            {streamTools.length > 0 && (
              <div className="space-y-1">
                {streamTools.slice(-10).map((tc, i) => (
                  <div
                    key={i}
                    className="bg-yellow-50 border-l-2 border-accent rounded-r p-1.5 text-xs font-mono"
                  >
                    → {tc.tool}({JSON.stringify(tc.input).slice(0, 100)}
                    {JSON.stringify(tc.input).length > 100 ? '…' : ''})
                  </div>
                ))}
                {streamTools.length > 10 && (
                  <div className="text-xs text-gray-500 italic">
                    …menampilkan 10 tool call terakhir dari {streamTools.length}.
                  </div>
                )}
              </div>
            )}
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
          {running ? `⟳ Streaming (${elapsed}s)…` : '▶ Jalankan (streaming)'}
        </button>
        {running && (
          <button
            onClick={detach}
            className="px-4 py-2 rounded border border-gray-300 text-gray-700 text-sm font-semibold hover:bg-gray-50"
            title="Berhenti melihat — analisis tetap berjalan di backend"
          >
            ✕ Lepas (tetap jalan)
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Analisis berjalan di <strong>background backend</strong> — aman ditinggal pindah tab atau
        reload; saat kembali ke tab ini progres otomatis disambung. Tombol <em>Lepas</em> hanya
        menutup tampilan, tidak menghentikan agen. Hasil di-persist ke DB dan tampil di history.
      </p>

      {/* Review Temuan inline di bawah hasil analisis chat (Prioritas 2). */}
      {/* Key berbasis history.length + running supaya auto-refresh saat agen selesai run baru. */}
      <div className="mt-5">
        <TemuanReviewPanel
          penugasanId={penugasanId}
          key={`temuan-review-${history.length}-${running ? 'run' : 'idle'}`}
        />
      </div>
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

// Kolom PKP format INTEGRAL/SIMWAS: Sasaran | Langkah Kerja | Dilaksanakan
// Oleh (assigned_to) | Waktu | No KKP.
type Sasaran = {
  sasaran_id: string;
  deskripsi: string;
  assigned_to: string[];
  langkah_kerja: string[];
  status: string;
  waktu?: string;
  no_kkp?: string;
};

function emptySasaran(idx: number): Sasaran {
  return {
    sasaran_id: `S-${String(idx).padStart(2, '0')}`,
    deskripsi: '',
    assigned_to: [],
    langkah_kerja: [],
    status: 'AKTIF',
    waktu: '',
    no_kkp: '',
  };
}

// Editor langkah kerja umum PKP (kelompok I. Perencanaan / III. Pelaporan,
// format INTEGRAL): kolom Langkah Kerja | Pelaksana | Waktu | Aksi.
type LangkahUmumRow = { langkah: string; pelaksana: string; waktu: string };

function LangkahUmumEditor({
  title,
  rows,
  onChange,
  disabled,
  placeholder,
}: {
  title: string;
  rows: LangkahUmumRow[];
  onChange: (rows: LangkahUmumRow[]) => void;
  disabled?: boolean;
  placeholder: string;
}) {
  const setRow = (i: number, patch: Partial<LangkahUmumRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div>
      <h4 className="font-semibold text-sm text-primary-dark mb-2">{title}</h4>
      {rows.length > 0 && (
        <div className="grid grid-cols-12 gap-2 mb-1 text-[11px] uppercase text-gray-400">
          <span className="col-span-6">Langkah Kerja</span>
          <span className="col-span-3">Pelaksana</span>
          <span className="col-span-2">Waktu</span>
          <span className="col-span-1">Aksi</span>
        </div>
      )}
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-12 gap-2">
            <input
              value={r.langkah}
              onChange={(e) => setRow(i, { langkah: e.target.value })}
              disabled={disabled}
              placeholder={placeholder}
              className="col-span-6 border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50"
            />
            <input
              value={r.pelaksana}
              onChange={(e) => setRow(i, { pelaksana: e.target.value })}
              disabled={disabled}
              placeholder="Nama pelaksana"
              className="col-span-3 border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50"
            />
            <input
              value={r.waktu}
              onChange={(e) => setRow(i, { waktu: e.target.value })}
              disabled={disabled}
              placeholder="Waktu"
              className="col-span-2 border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50"
            />
            {!disabled && (
              <button
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
                className="col-span-1 px-2 rounded border border-red-200 text-red-600 hover:bg-red-50 text-sm"
                title="Hapus langkah"
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
      {!disabled && (
        <button
          onClick={() => onChange([...rows, { langkah: '', pelaksana: '', waktu: '' }])}
          className="mt-2 px-3 py-1.5 text-sm rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
        >
          + Tambah Langkah
        </button>
      )}
      {rows.length === 0 && disabled && (
        <p className="text-xs text-gray-400 italic">Belum ada langkah.</p>
      )}
    </div>
  );
}

/** Ambil butir daftar di bawah heading/baris "Sasaran baku ..." dari body
 * template PKP wiki → jadi baris sasaran. Berhenti di baris kosong setelah
 * butir pertama atau heading berikutnya. */
function extractSasaranBakuFromTemplate(body: string): string[] {
  const lines = body.split('\n');
  const start = lines.findIndex((l) => /sasaran baku/i.test(l));
  if (start === -1) return [];
  const out: string[] = [];
  for (let j = start + 1; j < lines.length; j++) {
    const l = lines[j].trim();
    if (l.startsWith('- ')) out.push(l.slice(2).trim());
    else if (out.length > 0 && (l === '' || l.startsWith('#'))) break;
    else if (l.startsWith('#')) break;
  }
  return out.filter(Boolean);
}

function SetupPenugasanTab({
  penugasanId,
  role,
  currentUserName,
  section = 'all',
  skill,
}: {
  penugasanId: number;
  role: Role;
  currentUserName: string;
  // 'context' → hanya context.md (dipakai di KKP Workspace AT);
  // 'sasaran' → hanya sasaran-assignment + template/SIMWAS (dipakai di tab PKP);
  // 'all' → keduanya (kompat lama).
  section?: 'context' | 'sasaran' | 'all';
  // Skill penugasan — dipakai filter template PKP wiki.
  skill?: string;
}) {
  const showContext = section !== 'sasaran';
  const showSasaran = section !== 'context';
  const canEditSasaran = role === 'KT' || role === 'PT';
  const canEditContext = role === 'KT' || role === 'PT' || role === 'AT';
  const [sasaran, setSasaran] = useState<Sasaran[] | null>(null);
  const [contextMd, setContextMd] = useState<string>('');
  const [atUsers, setAtUsers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<'sasaran' | 'context' | null>(null);
  const [savedAt, setSavedAt] = useState<{ sasaran?: string; context?: string }>({});
  const [err, setErr] = useState<string | null>(null);
  const [genCtx, setGenCtx] = useState(false); // generate context (AI) sedang berjalan
  const [ctxReady, setCtxReady] = useState<{ ready: boolean; reason: string } | null>(null);
  const [simwasOpen, setSimwasOpen] = useState(false); // W1.1 — modal Impor dari SIMWAS
  const [templatesOpen, setTemplatesOpen] = useState(false); // Mulai dari template (3-sumber)
  const [pkpTplOpen, setPkpTplOpen] = useState(false); // Template PKP wiki → sasaran baku
  // Meta PKP format INTEGRAL: nomor PKP + langkah kelompok I (Perencanaan)
  // & III (Pelaporan). Kelompok II (Pelaksanaan) = daftar sasaran dari KP.
  const [nomorPkp, setNomorPkp] = useState('');
  const [perencanaan, setPerencanaan] = useState<Array<{ langkah: string; pelaksana: string; waktu: string }>>([]);
  const [pelaporan, setPelaporan] = useState<Array<{ langkah: string; pelaksana: string; waktu: string }>>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [sa, cm, users, rd] = await Promise.all([
        api.getSasaranAssignment(penugasanId),
        api.getContextMd(penugasanId),
        api.listUsers('AT').catch(() => []),
        api.getContextReadiness(penugasanId).catch(() => null),
      ]);
      setCtxReady(rd ? { ready: rd.ready, reason: rd.reason } : null);
      setAtUsers(users.map((u) => u.nama_lengkap));
      // Normalize: pastikan semua field array tidak undefined (data lama mungkin tidak punya langkah_kerja)
      const normalized: Sasaran[] = (sa.sasaran || []).map((s: any) => ({
        sasaran_id: String(s.sasaran_id ?? ''),
        deskripsi: String(s.deskripsi ?? ''),
        assigned_to: Array.isArray(s.assigned_to) ? s.assigned_to.map(String) : [],
        langkah_kerja: Array.isArray(s.langkah_kerja) ? s.langkah_kerja.map(String) : [],
        status: String(s.status ?? 'AKTIF'),
        waktu: String(s.waktu ?? ''),
        no_kkp: String(s.no_kkp ?? ''),
      }));
      setSasaran(normalized);
      setNomorPkp(String((sa as any).nomor_pkp ?? ''));
      setPerencanaan(Array.isArray((sa as any).langkah_perencanaan) ? (sa as any).langkah_perencanaan : []);
      setPelaporan(Array.isArray((sa as any).langkah_pelaporan) ? (sa as any).langkah_pelaporan : []);
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

  const toggleAssign = (idx: number, name: string, checked: boolean) => {
    if (!sasaran) return;
    const cur = sasaran[idx].assigned_to;
    const next = checked
      ? Array.from(new Set([...cur, name]))
      : cur.filter((n) => n !== name);
    updateSasaran(idx, { assigned_to: next });
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
      // Validasi anggota: sasaran tanpa assigned_to → QC SAIPI KRITIS (REN-006)
      // + AT tak bisa mulai. Warn tegas, tapi tetap izinkan simpan (draft).
      const noAssignee = cleaned.filter((s) => s.assigned_to.length === 0);
      if (noAssignee.length > 0) {
        const lanjut = confirm(
          `${noAssignee.length} sasaran belum punya anggota: ${noAssignee.map((s) => s.sasaran_id).join(', ')}.\n\n` +
            `Tanpa anggota, QC SAIPI akan KRITIS (REN-006) dan Anggota Tim tidak bisa mulai analisis.\n\nTetap simpan?`
        );
        if (!lanjut) {
          setSaving(null);
          return;
        }
      }
      const meta = {
        nomor_pkp: nomorPkp.trim(),
        langkah_perencanaan: perencanaan.filter((l) => l.langkah.trim()),
        langkah_pelaporan: pelaporan.filter((l) => l.langkah.trim()),
      };
      const res = await api.saveSasaranAssignment(penugasanId, cleaned, meta);
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

  // Generate context.md via agen AT (mode context-only). Run di-decouple di
  // backend; EventSource hanya untuk tahu kapan selesai → reload textarea.
  const generateContext = () => {
    if (genCtx) return;
    setGenCtx(true);
    setErr(null);
    const prompt =
      '[MODE:CONTEXT] Susun/perbarui context.md dari hasil digest dokumen + sasaran audit. ' +
      'Jangan jalankan pipeline/analisis atau susun temuan — cukup context.md lalu berhenti.';
    const es = new EventSource(api.agentStreamUrl('anggota_tim', penugasanId, prompt));
    let done = false;
    const finish = async () => {
      if (done) return;
      done = true;
      es.close();
      try {
        const cm = await api.getContextMd(penugasanId);
        setContextMd(cm.content || '');
        setSavedAt((s) => ({ ...s, context: new Date().toLocaleTimeString('id-ID') }));
      } catch {
        /* abaikan */
      }
      setGenCtx(false);
    };
    es.addEventListener('done', finish);
    es.addEventListener('error', (ev: MessageEvent) => {
      try {
        const d = JSON.parse(ev.data);
        if (d?.message) setErr(`Generate context gagal: ${d.message}`);
      } catch {
        /* error event tanpa data = koneksi; finish saja */
      }
      finish();
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) finish();
    };
  };

  if (loading) {
    return <div className="bg-white p-5 rounded-lg text-sm text-gray-500">Memuat setup penugasan…</div>;
  }

  // AT hanya melihat sasaran yang ditugaskan ke dirinya; KT/PT melihat semua.
  // idx asli dipertahankan agar updateSasaran/removeSasaran tetap benar.
  const visibleRows = (sasaran || [])
    .map((s, idx) => ({ s, idx }))
    .filter(({ s }) => canEditSasaran || s.assigned_to.includes(currentUserName));
  const myCount = (sasaran || []).filter((s) => s.assigned_to.includes(currentUserName)).length;

  return (
    <div className="space-y-6">
      {err && (
        <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
          {err}
        </div>
      )}

      {section === 'all' && (role === 'AT' ? (
        <div className="bg-blue-50 border-l-4 border-blue-400 p-4 rounded text-sm text-blue-900">
          <strong>Konteks (peran AT).</strong> Klik <strong>Generate Context (AI)</strong> di bawah —
          AI menyusun context.md dari hasil digest dokumen + sasaran. Setelah jadi, <strong>review &amp; edit</strong>{' '}
          bila perlu tambah informasi, lalu <strong>Simpan</strong>. Baru jalankan <strong>Analisis AI</strong> di tab Chat AT.
          Bagian sasaran hanya menampilkan <strong>sasaran yang ditugaskan kepada Anda</strong> ({currentUserName}) — read-only.
        </div>
      ) : (
        <div className="bg-blue-50 border-l-4 border-blue-400 p-4 rounded text-sm text-blue-900">
          <strong>Setup Penugasan (peran KT/PT).</strong> Fokus Anda: isi{' '}
          <strong>Sasaran reviu + langkah kerja</strong> di bawah dan assign ke anggota tim.
          {' '}context.md di-generate oleh <strong>Anggota Tim</strong> (tombol Generate Context) dari digest + sasaran —
          tidak perlu Anda isi manual. Bagian context di bawah <strong>opsional</strong> (override bila perlu).
        </div>
      ))}

      {showContext && (
        <>
      {/* === KONTEKS PRA-LOADED (Prioritas 1 — peningkatan kualitas output agen) === */}
      <PreloadContextPanel penugasanId={penugasanId} />

      {/* === CONTEXT.MD === */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">
              1. Konteks Penugasan (context.md) <span className="text-xs font-normal text-blue-600">· Generate AI + edit</span>
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Generate dari digest dokumen + sasaran, lalu edit bila perlu tambah info, lalu Simpan.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {savedAt.context && (
              <span className="text-xs text-green-700">✓ Tersimpan {savedAt.context}</span>
            )}
            {role === 'AT' && (
              <button
                onClick={generateContext}
                disabled={genCtx || saving === 'context' || !ctxReady?.ready}
                className="px-4 py-1.5 text-sm rounded border border-primary text-primary font-semibold hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed"
                title={
                  ctxReady && !ctxReady.ready
                    ? `Belum bisa: ${ctxReady.reason}`
                    : 'AI menyusun context.md dari digest dokumen + sasaran (±30–60 detik)'
                }
              >
                {genCtx ? '⟳ Generating…' : '✨ Generate Context (AI)'}
              </button>
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
        {role === 'AT' && ctxReady && !ctxReady.ready && (
          <div className="px-5 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">
            ⚠ Generate Context belum bisa dipakai — {ctxReady.reason}.
          </div>
        )}
        <textarea
          value={contextMd}
          onChange={(e) => setContextMd(e.target.value)}
          disabled={!canEditContext}
          className="w-full p-4 font-mono text-xs h-80 border-0 resize-y focus:outline-none focus:ring-1 focus:ring-primary disabled:bg-gray-50 disabled:text-gray-600"
          placeholder="# Konteks Penugasan: ..."
        />
      </div>
        </>
      )}

      {showSasaran && (
        <>
      {/* === PKP header (format INTEGRAL): Nomor PKP + I. Perencanaan === */}
      {role !== 'AT' && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 bg-gray-50 border-b border-gray-200">
            <h3 className="font-semibold text-primary-dark">PROGRAM KERJA PENGAWASAN</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Format INTEGRAL: Nomor PKP + langkah kerja kelompok I. Perencanaan / II. Pelaksanaan
              (sasaran dari Kartu Penugasan) / III. Pelaporan. Simpan lewat tombol <b>Simpan Sasaran</b> di bawah.
            </p>
          </div>
          <div className="p-5 space-y-4">
            <div className="grid md:grid-cols-4 gap-2 items-center">
              <label className="text-sm text-gray-600">Nomor PKP</label>
              <input
                value={nomorPkp}
                onChange={(e) => setNomorPkp(e.target.value)}
                disabled={!canEditSasaran}
                placeholder="PKP/93/IJ.3/KP.01.06/05/2026"
                className="md:col-span-3 border border-gray-300 rounded-md px-3 py-2 text-sm font-mono disabled:bg-gray-50"
              />
            </div>
            <LangkahUmumEditor
              title="I. Perencanaan"
              rows={perencanaan}
              onChange={setPerencanaan}
              disabled={!canEditSasaran}
              placeholder="Masukkan langkah kerja perencanaan"
            />
          </div>
        </div>
      )}

      {/* === SASARAN-ASSIGNMENT === */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">
              {role === 'AT'
                ? `Sasaran Saya (${myCount})`
                : `II. Pelaksanaan — Sasaran Pengawasan (${sasaran?.length || 0})`}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {role === 'AT'
                ? `Sasaran yang ditugaskan kepada ${currentUserName}. Agen Anggota Tim hanya mengerjakan sasaran ini.`
                : 'Sasaran berasal dari Kartu Penugasan (tahapan 1) — bisa juga ditambah manual di sini. Tiap sasaran: langkah kerja + Pelaksana ("Ditugaskan ke") + Waktu.'}
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

        {visibleRows.length === 0 && (
          <div className="p-5 text-center text-sm text-gray-500">
            {canEditSasaran ? (
              <>Belum ada sasaran. Klik <strong>+ Tambah Sasaran</strong> untuk mulai.</>
            ) : !sasaran || sasaran.length === 0 ? (
              <>Tunggu Ketua Tim setup sasaran terlebih dahulu.</>
            ) : (
              <>Belum ada sasaran yang ditugaskan kepada <strong>{currentUserName}</strong>. Tunggu Ketua Tim meng-assign.</>
            )}
          </div>
        )}

        {visibleRows.length > 0 && (
          <div className="divide-y divide-gray-100">
            {visibleRows.map(({ s, idx }) => (
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
                      Ditugaskan ke {canEditSasaran && '*'}
                    </label>
                    {canEditSasaran ? (
                      <div className="space-y-1 border border-gray-300 rounded px-2 py-1.5 min-h-[2.25rem]">
                        {atUsers.length === 0 && (
                          <p className="text-xs text-gray-400">
                            Belum ada user AT — jalankan <code>python -m app.init_db</code>.
                          </p>
                        )}
                        {atUsers.map((name) => (
                          <label key={name} className="flex items-center gap-2 text-xs cursor-pointer">
                            <input
                              type="checkbox"
                              checked={s.assigned_to.includes(name)}
                              onChange={(e) => toggleAssign(idx, name, e.target.checked)}
                            />
                            <span>{name}</span>
                          </label>
                        ))}
                        {s.assigned_to
                          .filter((n) => !atUsers.includes(n))
                          .map((n) => (
                            <div key={n} className="flex items-center gap-2 text-xs text-amber-700">
                              <span>• {n} (di luar daftar AT)</span>
                              <button
                                type="button"
                                onClick={() => toggleAssign(idx, n, false)}
                                className="text-red-500 hover:underline"
                              >
                                hapus
                              </button>
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1 py-1">
                        {s.assigned_to.length === 0 ? (
                          <span className="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800 border border-amber-300" title="QC SAIPI akan KRITIS (REN-006) sampai sasaran ini di-assign ke anggota">
                            ⚠ belum di-assign
                          </span>
                        ) : (
                          s.assigned_to.map((n) => (
                            <span
                              key={n}
                              className={`px-2 py-0.5 rounded-full text-xs ${
                                n === currentUserName
                                  ? 'bg-blue-100 text-blue-800 font-medium'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {n}
                            </span>
                          ))
                        )}
                      </div>
                    )}
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

                {/* Kolom PKP format INTEGRAL: Waktu + No KKP */}
                <div className="grid grid-cols-12 gap-3 mt-2">
                  <div className="col-span-5">
                    <label className="text-xs text-gray-500 mb-1 block">Waktu (periode pelaksanaan)</label>
                    <input
                      value={s.waktu || ''}
                      onChange={(e) => updateSasaran(idx, { waktu: e.target.value })}
                      placeholder="Mis. Minggu II–III Juni 2026"
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                  <div className="col-span-4">
                    <label className="text-xs text-gray-500 mb-1 block">No KKP</label>
                    <input
                      value={s.no_kkp || ''}
                      onChange={(e) => updateSasaran(idx, { no_kkp: e.target.value })}
                      placeholder="Mis. KKP-N/255/IJ.3/KP.01.06"
                      disabled={!canEditSasaran}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm font-mono disabled:bg-gray-50 disabled:text-gray-600"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {canEditSasaran && (
          <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex flex-wrap gap-2 items-center">
            <button
              onClick={addSasaran}
              className="px-3 py-1.5 text-sm rounded border border-primary text-primary hover:bg-primary hover:text-white transition"
            >
              + Tambah Sasaran
            </button>
            <button
              onClick={() => setTemplatesOpen(true)}
              className="px-3 py-1.5 text-sm rounded border border-amber-500 text-amber-700 hover:bg-amber-600 hover:text-white transition"
              title="Saran sasaran dari penugasan lalu, skeleton pattern wiki, & catatan W3 — KT tidak start-from-zero."
            >
              ⋆ Mulai dari template
            </button>
            <button
              onClick={() => setPkpTplOpen((v) => !v)}
              className="px-3 py-1.5 text-sm rounded border border-violet-500 text-violet-700 hover:bg-violet-600 hover:text-white transition"
              title="Template PKP dari wiki — daftar sasaran baku template otomatis jadi baris sasaran."
            >
              📚 Template PKP wiki
            </button>
            <button
              onClick={() => setSimwasOpen(true)}
              className="px-3 py-1.5 text-sm rounded border border-indigo-500 text-indigo-600 hover:bg-indigo-600 hover:text-white transition"
              title="Import sasaran dari payload PKP SIMWAS (paste JSON / sample). Pull API SIMWAS langsung belum aktif."
            >
              ↘ Impor dari SIMWAS
            </button>
            <span className="text-[11px] text-gray-400">
              4 cara mulai: form kosong, template penugasan lalu, template PKP wiki, atau impor SIMWAS.
            </span>
          </div>
        )}

        {canEditSasaran && pkpTplOpen && (
          <div className="px-5 py-4 border-t border-gray-200 bg-violet-50/30">
            <p className="text-xs text-gray-500 mb-3">
              Pilih template PKP wiki — butir <strong>"Sasaran baku"</strong> template otomatis
              ditambahkan sebagai baris sasaran (lengkapi waktu/assignment setelahnya).
            </p>
            <TemplatePickerKpPkp
              kind="pkp"
              skill={skill || ''}
              onUse={(t) => {
                const baku = extractSasaranBakuFromTemplate(t.body);
                if (baku.length === 0) {
                  setErr('Template ini tidak memuat daftar "Sasaran baku" — pakai sebagai referensi manual.');
                  return;
                }
                const cur = sasaran || [];
                const existing = new Set(cur.map((x) => x.deskripsi.trim().toLowerCase()));
                const rows = baku
                  .filter((d) => !existing.has(d.trim().toLowerCase()))
                  .map((d, i) => ({ ...emptySasaran(cur.length + i + 1), deskripsi: d }));
                setSasaran([...cur, ...rows]);
                setPkpTplOpen(false);
              }}
            />
          </div>
        )}
      </div>

      {/* === III. Pelaporan (format INTEGRAL) === */}
      {role !== 'AT' && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <LangkahUmumEditor
            title="III. Pelaporan"
            rows={pelaporan}
            onChange={setPelaporan}
            disabled={!canEditSasaran}
            placeholder="Masukkan langkah kerja pelaporan"
          />
        </div>
      )}

      {canEditSasaran && simwasOpen && (
        <SimwasImportModal
          penugasanId={penugasanId}
          onClose={() => setSimwasOpen(false)}
          onSuccess={() => { setSimwasOpen(false); load(); }}
        />
      )}

      {canEditSasaran && templatesOpen && (
        <TemplateSetupModal
          penugasanId={penugasanId}
          existingSasaran={sasaran || []}
          onApply={(newSasaran) => {
            setSasaran(newSasaran);
            setTemplatesOpen(false);
          }}
          onClose={() => setTemplatesOpen(false)}
        />
      )}

      {canEditSasaran && (
        <div className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded p-3">
          <strong>Tips:</strong> setelah simpan, AT bisa mulai upload dokumen +
          analisis. Status sasaran otomatis upgrade ke <code>SELESAI_KKP</code> saat AT
          input temuan; KT ubah ke <code>DISETUJUI_KT</code> setelah review KKP, baru
          bisa lanjut ke Draft LHR.
        </div>
      )}
        </>
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

// LhpReviewPanel (S3.2 — tahapan 6 LRS LHP). PT/PM menyetujui konsep LHP atau
// minta revisi dengan catatan. Role lain (AT/KT) melihat status read-only.
type LhpReviewItem = {
  id: number;
  status: 'APPROVED' | 'NEEDS_REVISION';
  catatan: string | null;
  reviewer_role: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
};

function LhpReviewPanel({
  penugasanId,
  role,
  onReviewed,
}: {
  penugasanId: number;
  role: Role;
  onReviewed?: (status: 'APPROVED' | 'NEEDS_REVISION' | null) => void;
}) {
  const [items, setItems] = useState<LhpReviewItem[]>([]);
  const [latest, setLatest] = useState<'APPROVED' | 'NEEDS_REVISION' | null>(null);
  const [catatan, setCatatan] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canReview = role === 'PT' || role === 'PM';

  const load = async () => {
    try {
      const r = await api.listLhpReview(penugasanId);
      setItems(r.items);
      setLatest(r.latest_status);
    } catch {
      /* abaikan — fitur opsional */
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [penugasanId]);

  const submit = async (status: 'APPROVED' | 'NEEDS_REVISION') => {
    if (status === 'NEEDS_REVISION' && !catatan.trim()) {
      setErr('Catatan revisi wajib diisi saat meminta revisi.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.createLhpReview(penugasanId, status, catatan.trim() || undefined);
      setCatatan('');
      await load();
      onReviewed?.(status);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const badge =
    latest === 'APPROVED'
      ? { cls: 'bg-emerald-100 text-emerald-700', label: '✓ Konsep LHP Disetujui' }
      : latest === 'NEEDS_REVISION'
      ? { cls: 'bg-amber-100 text-amber-800', label: '⟳ Perlu Revisi' }
      : { cls: 'bg-gray-100 text-gray-500', label: '○ Belum direviu' };

  return (
    <div className="mb-5 bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-violet-50 px-4 py-2.5 border-b border-violet-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-primary-dark">Tahapan 6 — Reviu Konsep LHP (PT/PM)</span>
          <span className={`px-2 py-0.5 text-[11px] rounded-full font-medium ${badge.cls}`}>{badge.label}</span>
        </div>
      </div>
      <div className="p-4">
        {err && (
          <div className="mb-3 p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">{err}</div>
        )}

        {canReview ? (
          <>
            <label className="block text-xs text-gray-600 mb-1">
              Catatan reviu (wajib bila minta revisi)
            </label>
            <textarea
              value={catatan}
              onChange={(e) => setCatatan(e.target.value)}
              rows={3}
              placeholder="Arahan perbaikan untuk Ketua Tim, atau catatan persetujuan…"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm mb-3"
            />
            <div className="flex gap-2">
              <button
                onClick={() => submit('APPROVED')}
                disabled={busy}
                className="px-4 py-2 rounded bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50"
              >
                {busy ? '…' : `✓ Setujui sebagai ${role}`}
              </button>
              <button
                onClick={() => submit('NEEDS_REVISION')}
                disabled={busy}
                className="px-4 py-2 rounded bg-amber-500 text-white text-sm font-semibold hover:bg-amber-600 disabled:opacity-50"
              >
                {busy ? '…' : '⟳ Minta Revisi'}
              </button>
            </div>
          </>
        ) : (
          <p className="text-xs text-gray-500">
            🔒 Hanya Pengendali Teknis (PT) / Pengendali Mutu (PM) yang dapat mereviu konsep LHP.
          </p>
        )}

        {items.length > 0 && (
          <div className="mt-4 border-t border-gray-100 pt-3">
            <div className="text-xs uppercase text-gray-400 tracking-wider mb-2">Riwayat Reviu</div>
            <ul className="space-y-2">
              {items.map((it) => (
                <li key={it.id} className="text-xs flex gap-2">
                  <span
                    className={`px-1.5 py-0.5 rounded font-medium h-fit ${
                      it.status === 'APPROVED'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {it.status === 'APPROVED' ? 'Disetujui' : 'Revisi'}
                  </span>
                  <div className="flex-1">
                    <div className="text-gray-700">
                      {it.reviewer_name || '—'}{' '}
                      <span className="text-gray-400">({it.reviewer_role || '?'})</span>
                      {it.reviewed_at && (
                        <span className="text-gray-400">
                          {' · '}
                          {new Date(it.reviewed_at).toLocaleString('id-ID')}
                        </span>
                      )}
                    </div>
                    {it.catatan && <div className="text-gray-500 mt-0.5">{it.catatan}</div>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

// Panel status evaluasi BERTAHAP (gate-based) — tampil hanya untuk skill gated
// (SPIP/SAKIP/RB). Read-only; eksekusi gate dijalankan via tab Chat (AT) dengan
// menulis perintah `[MODE:GATE:<id>]`.
const GATE_BADGE: Record<string, string> = {
  DONE: 'bg-emerald-100 text-emerald-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-700',
  NEEDS_REVISION: 'bg-amber-100 text-amber-700',
  PENDING: 'bg-gray-100 text-gray-500',
};

function GatePanel({
  penugasanId,
  skill,
  role,
  onRunGate,
}: {
  penugasanId: number;
  skill: string;
  role: Role;
  onRunGate: (gateId: string) => void;
}) {
  const [data, setData] = useState<GateStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = () =>
    api.getGates(penugasanId).then(setData).catch(() => {});

  useEffect(() => {
    let alive = true;
    api
      .getGates(penugasanId)
      .then((d) => alive && setData(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [penugasanId]);

  const decide = async (gateId: string, decision: 'LANJUT' | 'KOREKSI' | 'ULANG') => {
    if (decision !== 'LANJUT' && !confirm(`Tandai Gate ${gateId} sebagai ${decision}?`)) return;
    setBusy(true);
    try {
      await api.recordGateDecision(penugasanId, gateId, decision);
      await refetch();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!data || !data.gated) return null;

  const prog = data.progress;
  const statusOf = (id: string) =>
    prog?.gates.find((g) => g.id === id)?.status || 'PENDING';
  const current = prog?.current_gate ?? null;
  const doneCount = prog?.gates.filter((g) => g.status === 'DONE').length ?? 0;

  return (
    <div className="mb-4 rounded-lg border border-violet-200 bg-violet-50/50 p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-sm text-violet-900">
          Evaluasi Bertahap (gate-based) — {data.skill}
        </div>
        <div className="text-xs text-violet-700">
          {prog ? `${doneCount}/${data.gates.length} gate selesai` : 'belum dimulai'}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {data.gates.map((g) => {
          const st = statusOf(g.id);
          const isCurrent = current === g.id;
          return (
            <span
              key={g.id}
              title={g.judul + (statusOf(g.id) ? ` — ${st}` : '')}
              className={`text-[11px] px-2 py-0.5 rounded-full border ${GATE_BADGE[st]} ${
                isCurrent ? 'ring-2 ring-violet-400 font-semibold' : 'border-transparent'
              }`}
            >
              Gate {g.id}
            </span>
          );
        })}
      </div>
      <div className="mt-2 text-xs text-violet-800">
        {current
          ? <>Gate aktif: <b>Gate {current}</b>. Anggota Tim menjalankan via tab <b>Chat</b> dengan perintah <code className="bg-white px-1 rounded">[MODE:GATE:{current}]</code>. Setelah ditinjau, pilih keputusan:</>
          : prog
          ? <>✓ Semua gate selesai. Lanjut ke penyusunan LHE/LHP di tab Output.</>
          : <>Mulai dengan menjalankan <code className="bg-white px-1 rounded">[MODE:GATE:{data.gates[0]?.id}]</code> di tab Chat (Anggota Tim), lalu putuskan di sini.</>}
      </div>
      {current && (
        <div className="mt-2 flex gap-2 items-center flex-wrap">
          {role === 'AT' && (
            <button
              onClick={() => onRunGate(current)}
              className="text-xs px-3 py-1 rounded bg-violet-600 text-white font-medium"
              title={`Buka Chat dengan perintah [MODE:GATE:${current}] terisi`}
            >
              ▶ Jalankan Gate {current}
            </button>
          )}
          <button
            onClick={() => decide(current, 'LANJUT')}
            disabled={busy}
            className="text-xs px-3 py-1 rounded bg-emerald-600 text-white font-medium disabled:opacity-50"
          >
            ✓ LANJUT
          </button>
          <button
            onClick={() => decide(current, 'KOREKSI')}
            disabled={busy}
            className="text-xs px-3 py-1 rounded bg-amber-500 text-white font-medium disabled:opacity-50"
          >
            ✎ KOREKSI
          </button>
          <button
            onClick={() => decide(current, 'ULANG')}
            disabled={busy}
            className="text-xs px-3 py-1 rounded bg-gray-500 text-white font-medium disabled:opacity-50"
          >
            ↻ ULANG
          </button>
        </div>
      )}
    </div>
  );
}

// ====================================================================
// W1.1 — Modal "Impor dari SIMWAS"
//
// Paste payload PKP dari SIMWAS (atau muat sample), pilih strategy
// (replace = bersihkan sasaran lama; append = tambahkan ke yang sudah ada),
// lalu submit ke POST /penugasan/{id}/sasaran/sync-from-simwas.
// Sumber 'manual' aktif hari ini; 'api' akan hidup setelah SIMWAS REST + SSO.
// ====================================================================

const SIMWAS_SAMPLE = `{
  "source": "manual",
  "strategy": "replace",
  "pkp_rows": [
    {
      "sasaran": "Kelengkapan dan kewajaran KAK",
      "langkah_kerja": "Cek 12 komponen format TOR/KAK",
      "dilaksanakan_oleh": "Sarah Aulia"
    },
    {
      "sasaran": "Kelengkapan dan kewajaran KAK",
      "langkah_kerja": "Cek dasar hukum & SLA terukur",
      "dilaksanakan_oleh": "Sarah Aulia"
    },
    {
      "sasaran": "Kewajaran HPS",
      "langkah_kerja": "Verifikasi 2 sumber referensi harga",
      "dilaksanakan_oleh": "Citra Lestari"
    }
  ]
}`;

function SimwasImportModal({
  penugasanId,
  onClose,
  onSuccess,
}: {
  penugasanId: number;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [raw, setRaw] = useState('');
  const [strategy, setStrategy] = useState<'replace' | 'append'>('replace');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{ added_count: number; total_sasaran: number; added_sasaran: string[]; skipped_duplicate: number } | null>(null);

  const submit = async () => {
    setErr(null);
    setResult(null);
    let parsed: any;
    try {
      parsed = JSON.parse(raw);
    } catch (e: any) {
      setErr(`JSON tidak valid: ${e.message}`);
      return;
    }
    const rows = parsed.pkp_rows ?? parsed.rows ?? parsed;
    if (!Array.isArray(rows)) {
      setErr('Body harus `{"pkp_rows":[...]}` atau langsung array. Tidak ditemukan `pkp_rows`.');
      return;
    }
    setBusy(true);
    try {
      const r = await api.syncSasaranFromSimwas(penugasanId, {
        source: 'manual',
        strategy,
        pkp_rows: rows,
      });
      setResult({
        added_count: r.added_count,
        total_sasaran: r.total_sasaran,
        added_sasaran: r.added_sasaran,
        skipped_duplicate: r.skipped_duplicate,
      });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
        <div className="px-5 py-3 border-b flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-primary-dark">Impor PKP dari SIMWAS</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">
              Source: <code>manual</code> (paste JSON). Source <code>api</code> aktif setelah integrasi resmi.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">×</button>
        </div>

        <div className="p-5 overflow-y-auto space-y-3">
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">Strategi</label>
            <div className="flex gap-3 text-sm">
              <label className="flex items-center gap-1">
                <input type="radio" checked={strategy === 'replace'} onChange={() => setStrategy('replace')} />
                <span>Replace <span className="text-gray-400 text-xs">(ganti semua sasaran lama)</span></span>
              </label>
              <label className="flex items-center gap-1">
                <input type="radio" checked={strategy === 'append'} onChange={() => setStrategy('append')} />
                <span>Append <span className="text-gray-400 text-xs">(tambahkan ke yang ada, anti-dup ID)</span></span>
              </label>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="text-xs font-semibold text-gray-700">Payload JSON</label>
              <button onClick={() => setRaw(SIMWAS_SAMPLE)} className="text-[11px] text-indigo-600 hover:underline">
                ↘ Muat contoh
              </button>
            </div>
            <textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder='{"pkp_rows":[{"sasaran":"...","langkah_kerja":"...","dilaksanakan_oleh":"..."}]}'
              className="w-full h-64 border border-gray-300 rounded p-2 text-xs font-mono"
            />
            <p className="text-[11px] text-gray-500 mt-1">
              Setiap baris PKP = 1 langkah_kerja. v7 group otomatis berdasarkan field <code>sasaran</code>.
              <code>sasaran_id</code> opsional — kalau kosong, auto-generate per skill (S-PBJ-NN, S-RKA-NN, dst).
            </p>
          </div>

          {err && (
            <div className="p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">{err}</div>
          )}
          {result && (
            <div className="p-2 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs">
              ✅ Sukses. {result.added_count} sasaran baru ({result.added_sasaran.join(', ') || '—'}).
              Total di file: {result.total_sasaran}.
              {result.skipped_duplicate > 0 && ` ${result.skipped_duplicate} dilewati (ID duplikat).`}
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            Tutup
          </button>
          {result ? (
            <button
              onClick={onSuccess}
              className="px-3 py-1.5 text-sm rounded bg-primary text-white hover:bg-primary-dark"
            >
              Selesai & Refresh
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={busy || !raw.trim()}
              className="px-3 py-1.5 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40"
            >
              {busy ? 'Mengirim…' : 'Impor'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ====================================================================
// Template Setup Modal — 3-sumber paralel
// ====================================================================
//  • Historis: penugasan v7 sebelumnya dgn skill sama (similarity obyek).
//  • Pattern wiki skeleton: 1 sasaran per kategori pattern dominan.
//  • Catatan W3 vault: pengawasan-*.md sebagai konteks (bukan sasaran langsung).
// Auditor pilih sumber → preview → "Pakai" untuk replace atau merge.
// ====================================================================

type TemplateApiResp = {
  skill: string;
  obyek: string;
  historis?: Array<{
    kode: string; obyek: string; skill: string; status: string;
    similarity: number; total_sasaran: number;
    sasaran: Array<{ sasaran_id: string; deskripsi: string; assigned_to: string[]; langkah_kerja: string[] }>;
  }>;
  patterns?: {
    skill: string; total_patterns: number;
    sasaran: Array<{ sasaran_id: string; deskripsi: string; langkah_kerja: string[]; assigned_to: string[]; kategori: string; pattern_ids: string[] }>;
  };
  writeback?: Array<{ nama_file: string; judul: string; skill_label: string; obyek: string; jumlah_temuan: number; similarity: number }>;
};

function TemplateSetupModal({
  penugasanId, existingSasaran, onApply, onClose,
}: {
  penugasanId: number;
  existingSasaran: Sasaran[];
  onApply: (newSasaran: Sasaran[]) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'historis' | 'patterns' | 'writeback'>('historis');
  const [data, setData] = useState<TemplateApiResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<'replace' | 'merge'>('replace');
  const [selectedHist, setSelectedHist] = useState<string | null>(null); // kode penugasan
  const [selectedPatterns, setSelectedPatterns] = useState(true); // ambil semua skeleton

  useEffect(() => {
    setLoading(true); setErr(null);
    api.getSasaranTemplates(penugasanId, 'all')
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [penugasanId]);

  const applyHistoris = (kode: string) => {
    const h = (data?.historis || []).find((x) => x.kode === kode);
    if (!h) return;
    const fromTemplate: Sasaran[] = h.sasaran.map((s) => ({
      sasaran_id: s.sasaran_id,
      deskripsi: s.deskripsi,
      assigned_to: s.assigned_to,
      langkah_kerja: s.langkah_kerja,
      status: 'AKTIF',
    }));
    if (!confirm(strategy === 'replace'
      ? `Replace ${existingSasaran.length} sasaran existing dengan ${fromTemplate.length} sasaran dari "${h.obyek}"?`
      : `Tambahkan ${fromTemplate.length} sasaran dari "${h.obyek}" ke ${existingSasaran.length} existing? (anti-dup by sasaran_id)`)) return;
    if (strategy === 'replace') {
      onApply(fromTemplate);
    } else {
      const existingIds = new Set(existingSasaran.map((s) => s.sasaran_id));
      const merged = [...existingSasaran, ...fromTemplate.filter((s) => !existingIds.has(s.sasaran_id))];
      onApply(merged);
    }
  };

  const applyPatterns = () => {
    const fromTemplate: Sasaran[] = (data?.patterns?.sasaran || []).map((s) => ({
      sasaran_id: s.sasaran_id,
      deskripsi: s.deskripsi,
      assigned_to: [],
      langkah_kerja: s.langkah_kerja,
      status: 'AKTIF',
    }));
    if (fromTemplate.length === 0) return;
    if (!confirm(strategy === 'replace'
      ? `Replace ${existingSasaran.length} sasaran dengan ${fromTemplate.length} skeleton dari pattern wiki?`
      : `Tambahkan ${fromTemplate.length} skeleton dari pattern wiki ke ${existingSasaran.length} existing?`)) return;
    if (strategy === 'replace') {
      onApply(fromTemplate);
    } else {
      const existingIds = new Set(existingSasaran.map((s) => s.sasaran_id));
      const merged = [...existingSasaran, ...fromTemplate.filter((s) => !existingIds.has(s.sasaran_id))];
      onApply(merged);
    }
  };

  const nHist = data?.historis?.length ?? 0;
  const nPatterns = data?.patterns?.sasaran?.length ?? 0;
  const nWriteback = data?.writeback?.length ?? 0;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] flex flex-col">
        <div className="px-5 py-3 border-b flex justify-between items-start">
          <div>
            <h3 className="font-semibold text-primary-dark">Mulai dari template</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">
              3 sumber paralel: penugasan lalu (similarity obyek), skeleton pattern wiki, catatan vault W3.
              Pilih satu → preview → Pakai.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">×</button>
        </div>

        <div className="px-5 py-2 border-b flex items-center gap-3 flex-wrap">
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => setTab('historis')}
              className={`px-2.5 py-1 rounded ${tab === 'historis' ? 'bg-amber-500 text-white' : 'bg-gray-100 text-gray-700'}`}
            >
              Penugasan lalu ({nHist})
            </button>
            <button
              onClick={() => setTab('patterns')}
              className={`px-2.5 py-1 rounded ${tab === 'patterns' ? 'bg-amber-500 text-white' : 'bg-gray-100 text-gray-700'}`}
            >
              Skeleton pattern ({nPatterns})
            </button>
            <button
              onClick={() => setTab('writeback')}
              className={`px-2.5 py-1 rounded ${tab === 'writeback' ? 'bg-amber-500 text-white' : 'bg-gray-100 text-gray-700'}`}
            >
              Catatan vault ({nWriteback})
            </button>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className="text-gray-500">Strategy:</span>
            <label className="flex items-center gap-1">
              <input type="radio" checked={strategy === 'replace'} onChange={() => setStrategy('replace')} />
              <span>Replace</span>
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={strategy === 'merge'} onChange={() => setStrategy('merge')} />
              <span>Merge</span>
            </label>
          </div>
        </div>

        <div className="p-5 overflow-y-auto flex-1">
          {loading && <div className="text-xs text-gray-400 italic">Memuat saran template…</div>}
          {err && <div className="p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">{err}</div>}

          {/* HISTORIS */}
          {!loading && tab === 'historis' && (
            <>
              {nHist === 0 ? (
                <p className="text-xs text-gray-400 italic">
                  Belum ada penugasan v7 dengan skill <code>{data?.skill}</code> yang punya sasaran-assignment.json. Coba tab <b>Skeleton pattern</b>.
                </p>
              ) : (
                <div className="space-y-2">
                  {data!.historis!.map((h) => (
                    <div key={h.kode} className={`border rounded p-3 ${selectedHist === h.kode ? 'border-amber-400 bg-amber-50/40' : 'border-gray-200'}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-medium text-gray-800">{h.obyek}</div>
                          <div className="text-[11px] text-gray-400 mt-0.5">
                            {h.kode} · {h.total_sasaran} sasaran · similarity <b>{(h.similarity * 100).toFixed(0)}%</b>
                          </div>
                        </div>
                        <div className="flex flex-col gap-1 shrink-0">
                          <button
                            onClick={() => setSelectedHist(selectedHist === h.kode ? null : h.kode)}
                            className="text-[11px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                          >
                            {selectedHist === h.kode ? 'tutup preview' : 'preview'}
                          </button>
                          <button
                            onClick={() => applyHistoris(h.kode)}
                            className="text-[11px] px-2 py-0.5 rounded bg-amber-500 text-white hover:bg-amber-600"
                          >
                            Pakai
                          </button>
                        </div>
                      </div>
                      {selectedHist === h.kode && (
                        <div className="mt-2 pt-2 border-t border-amber-200 space-y-1.5">
                          {h.sasaran.map((s, i) => (
                            <div key={i} className="text-[11px]">
                              <span className="font-mono text-gray-500">{s.sasaran_id}</span> — {s.deskripsi}
                              {s.langkah_kerja.length > 0 && (
                                <div className="text-gray-500 pl-3">• {s.langkah_kerja.join(' • ')}</div>
                              )}
                              {s.assigned_to.length > 0 && (
                                <div className="text-gray-500 pl-3">→ {s.assigned_to.join(', ')}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* PATTERNS */}
          {!loading && tab === 'patterns' && (
            <>
              {nPatterns === 0 ? (
                <p className="text-xs text-gray-400 italic">
                  Skill <code>{data?.skill}</code> tidak punya pattern di wiki (criteria-driven atau skill baru). Tidak ada skeleton.
                </p>
              ) : (
                <>
                  <p className="text-xs text-gray-500 mb-2">
                    {data!.patterns!.total_patterns} pattern di skill <code>{data!.patterns!.skill}</code> di-cluster ke {nPatterns} kategori.
                    1 sasaran per kategori, langkah_kerja merefer ID pattern dominan.
                  </p>
                  <div className="space-y-2 mb-3">
                    {data!.patterns!.sasaran.map((s) => (
                      <div key={s.sasaran_id} className="border border-gray-200 rounded p-2">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <span className="font-mono text-[11px] text-gray-500">{s.sasaran_id}</span>
                            <span className="text-[10px] ml-2 px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{s.kategori}</span>
                          </div>
                        </div>
                        <div className="text-sm text-gray-800 mt-1">{s.deskripsi}</div>
                        <ul className="text-[11px] text-gray-500 mt-1 list-disc list-inside">
                          {s.langkah_kerja.map((l, i) => <li key={i}>{l}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={applyPatterns}
                    className="px-3 py-1.5 text-sm rounded bg-amber-500 text-white hover:bg-amber-600"
                  >
                    Pakai {nPatterns} sasaran ini
                  </button>
                </>
              )}
            </>
          )}

          {/* WRITEBACK */}
          {!loading && tab === 'writeback' && (
            <>
              <p className="text-xs text-gray-500 mb-2">
                Catatan vault W3 (<code>pengawasan-*.md</code>) berisi <b>temuan</b> bukan <b>sasaran</b> — disuguhkan sbg konteks pembelajaran. Buka di tab Knowledge untuk baca penuh.
              </p>
              {nWriteback === 0 ? (
                <p className="text-xs text-gray-400 italic">
                  Belum ada catatan vault yang related dgn skill <code>{data?.skill}</code>. Vault juga mungkin tak dikonfigurasi (APP_VAULT_PATH).
                </p>
              ) : (
                <div className="space-y-1.5">
                  {data!.writeback!.map((w) => (
                    <div key={w.nama_file} className="border border-gray-200 rounded p-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-medium text-gray-800">{w.judul}</div>
                          <div className="text-[11px] text-gray-400">
                            {w.nama_file} · {w.jumlah_temuan} temuan · similarity <b>{(w.similarity * 100).toFixed(0)}%</b>
                          </div>
                        </div>
                        <a
                          href={`/knowledge`}
                          className="text-[11px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100 shrink-0"
                          title="Buka tab Knowledge untuk Cari Wiki / baca catatan"
                        >
                          buka Knowledge →
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t flex justify-end">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-gray-300 text-gray-600 hover:bg-gray-50">
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}

// ====================================================================
// PreloadContextPanel (Prioritas 1) — bangun bundle konteks pra-loaded
// supaya agen mulai dgn tangan penuh. Pattern wiki + vault + glossary + W3.
// ====================================================================

function PreloadContextPanel({ penugasanId }: { penugasanId: number }) {
  const [status, setStatus] = useState<{ exists: boolean; size_bytes?: number; modified_at?: string; char_count?: number; preview_head?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [stats, setStats] = useState<any>(null);

  const refresh = async () => {
    try {
      const r = await api.getPreloadContextStatus(penugasanId);
      setStatus(r);
    } catch { /* silent */ }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [penugasanId]);

  const build = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.buildPreloadContext(penugasanId);
      setStats(r.stats);
      setMsg(`Konteks dibangun: ${r.stats.n_patterns} pattern + ${r.stats.n_vault_notes} catatan vault + ${r.stats.n_konteks} konteks + ${r.stats.n_writeback_history} riwayat. ${(r.stats.char_count / 1024).toFixed(1)} KB.`);
      refresh();
    } catch (e: any) { setMsg(`Gagal: ${e.message}`); }
    finally { setBusy(false); }
  };

  return (
    <div className="bg-amber-50/40 border border-amber-200 rounded-lg p-4 mb-4">
      <div className="flex justify-between items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-[300px]">
          <h3 className="font-semibold text-primary-dark">
            ⚡ Konteks Pra-Loaded <span className="text-xs font-normal text-amber-700">· peningkatan kualitas AI</span>
          </h3>
          <p className="text-xs text-gray-600 mt-1">
            Sebelum agen jalan, sistem bisa siapkan <strong>bundle konteks</strong> dari 4 sumber:
            pattern wiki top-severity utk skill, catatan vault terkait obyek, pola-temuan-berulang +
            glossary + regulasi, dan riwayat penugasan serupa (W3). Agen mulai dgn tangan penuh —
            output lebih konsisten & substantif.
          </p>
          {status && (
            <div className="mt-2 text-xs">
              {status.exists ? (
                <span className="text-green-700">
                  ✓ Bundle ada: <b>{((status.char_count || 0) / 1024).toFixed(1)} KB</b>
                  {status.modified_at && <span className="text-gray-500"> · update terakhir {status.modified_at.slice(0, 19).replace('T', ' ')}</span>}
                </span>
              ) : (
                <span className="text-amber-700">⚠ Bundle belum dibangun. Bangun dulu sebelum mulai chat AT/KT.</span>
              )}
            </div>
          )}
          {stats && (
            <div className="mt-1 text-[11px] text-gray-500">
              keywords vault: {stats.vault_keywords?.join(', ') || '—'}
            </div>
          )}
        </div>
        <button
          onClick={build}
          disabled={busy}
          className="px-3 py-1.5 text-sm rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 whitespace-nowrap"
        >
          {busy ? 'Membangun…' : (status?.exists ? '↻ Refresh Konteks' : '⚡ Bangun Konteks')}
        </button>
      </div>
      {msg && <div className="mt-2 p-2 text-xs rounded bg-white border border-amber-200 text-gray-700">{msg}</div>}
    </div>
  );
}

// ====================================================================
// TemuanReviewPanel (Prioritas 2) — HITL per-temuan. AT/KT/PT setujui /
// tolak tiap temuan sebelum render KKP/LHR final.
// ====================================================================

type TemuanReviewItem = Awaited<ReturnType<typeof api.listTemuanReview>>['items'][number];

const REVIEW_STATUS_COLOR: Record<string, string> = {
  PENDING: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  APPROVED: 'bg-green-100 text-green-800 border-green-300',
  REJECTED: 'bg-red-100 text-red-800 border-red-300',
  EDITED: 'bg-blue-100 text-blue-800 border-blue-300',
};

function LhpFilesPanel({ penugasanId }: { penugasanId: number }) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ path: string; content: string; truncated: boolean } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const load = async () => {
    setLoading(true); setErr(null);
    try {
      const res = await api.listFiles(penugasanId);
      const lhpCat = res.categories.find(c => c.key === '_LHP');
      setFiles(lhpCat?.files ?? []);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [penugasanId]);

  const doDownload = async (f: FileEntry) => {
    try {
      const blob = await api.downloadFile(penugasanId, f.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = f.name;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (e: any) { setErr(e.message); }
  };

  const doPreview = async (f: FileEntry) => {
    setPreviewLoading(true);
    try {
      const res = await api.previewFile(penugasanId, f.path);
      setPreview({ path: res.path, content: res.content, truncated: res.truncated });
    } catch (e: any) { setErr(e.message); }
    finally { setPreviewLoading(false); }
  };

  return (
    <div className="bg-white border border-violet-200 rounded-lg overflow-hidden">
      <div className="bg-violet-50 px-4 py-2.5 border-b border-violet-100 flex items-center justify-between">
        <span className="font-semibold text-sm text-primary-dark">File Laporan (LHP)</span>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          {loading ? '…' : '↻ Refresh'}
        </button>
      </div>

      {err && <div className="p-3 text-xs text-red-700 bg-red-50">{err}</div>}
      {loading && <div className="p-3 text-xs text-gray-400 italic">Memuat file laporan…</div>}
      {!loading && files.length === 0 && (
        <div className="p-4 text-xs text-gray-500">
          Belum ada file laporan di folder <code className="bg-gray-100 px-1 rounded">_LHP</code>. Generate laporan terlebih dahulu via chat.
        </div>
      )}
      {!loading && files.length > 0 && (
        <table className="w-full text-sm">
          <tbody>
            {files.map((f) => (
              <tr key={f.path} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-4 py-2 w-8 text-base">{iconForExt(f.ext)}</td>
                <td className="px-2 py-2">
                  <div className="font-medium text-xs">{f.name}</div>
                  <div className="text-[10px] text-gray-400 font-mono">{f.path}</div>
                </td>
                <td className="px-2 py-2 text-xs text-gray-500 whitespace-nowrap">{formatBytes(f.size_bytes)}</td>
                <td className="px-2 py-2 text-xs text-gray-500 whitespace-nowrap">{formatTime(f.mtime)}</td>
                <td className="px-2 py-2 text-right whitespace-nowrap">
                  {PREVIEWABLE.has(f.ext) && (
                    <button
                      onClick={() => doPreview(f)}
                      disabled={previewLoading}
                      className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-100 mr-1 disabled:opacity-50"
                    >
                      Lihat
                    </button>
                  )}
                  <button
                    onClick={() => doDownload(f)}
                    className="text-xs px-2 py-1 rounded bg-primary text-white hover:bg-primary-dark"
                  >
                    Unduh
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {preview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-6 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[85vh] flex flex-col">
            <div className="flex justify-between items-center px-5 py-3 border-b border-gray-200">
              <div className="font-mono text-sm">{preview.path}</div>
              <button onClick={() => setPreview(null)} className="text-gray-500 hover:text-gray-800 text-xl">×</button>
            </div>
            <pre className="flex-1 overflow-auto p-5 text-xs whitespace-pre-wrap font-mono bg-gray-50">
              {preview.content}
            </pre>
            {preview.truncated && (
              <div className="px-5 py-2 text-xs text-amber-700 bg-amber-50 border-t border-amber-200">
                File besar — hanya 50 KB awal yang ditampilkan. Klik Unduh untuk file lengkap.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SasaranApprovalPanel({ penugasanId, onSaved }: { penugasanId: number; onSaved?: () => void }) {
  const [sasaran, setSasaran] = useState<Array<{
    sasaran_id: string; deskripsi: string; assigned_to: string[];
    langkah_kerja: string[]; status: string; waktu?: string; no_kkp?: string;
  }>>([]);
  const [meta, setMeta] = useState<{ nomor_pkp?: string }>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getSasaranAssignment(penugasanId);
      setSasaran(data.sasaran || []);
      setMeta({ nomor_pkp: data.nomor_pkp });
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [penugasanId]);

  const ubahStatus = (idx: number, newStatus: string) => {
    setSasaran(prev => prev.map((s, i) => i === idx ? { ...s, status: newStatus } : s));
  };

  const setujuiSemua = async () => {
    const hasPending = sasaran.some(s => s.status !== 'DISETUJUI_KT' && s.status !== 'DIKEMBALIKAN_AT' && s.status !== 'DIBATALKAN');
    const updated = sasaran.map(s =>
      s.status === 'DIBATALKAN' || s.status === 'DIKEMBALIKAN_AT' ? s : { ...s, status: 'DISETUJUI_KT' }
    );
    setSasaran(updated);
    setSaving(true); setMsg(null);
    try {
      await api.saveSasaranAssignment(penugasanId, updated, meta);
      setMsg('Sasaran yang belum dikembalikan telah disetujui semua.');
      onSaved?.();
    } catch (e: any) { setMsg(`Gagal simpan: ${e.message}`); }
    finally { setSaving(false); }
  };

  const simpan = async () => {
    setSaving(true); setMsg(null);
    try {
      await api.saveSasaranAssignment(penugasanId, sasaran, meta);
      setMsg('Keputusan sasaran disimpan.');
      onSaved?.();
    } catch (e: any) { setMsg(`Gagal simpan: ${e.message}`); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="p-3 text-xs text-gray-400 italic">Memuat sasaran…</div>;
  if (!sasaran.length) return null;

  const disetujuiCount = sasaran.filter(s => s.status === 'DISETUJUI_KT').length;
  const dikembalikanCount = sasaran.filter(s => s.status === 'DIKEMBALIKAN_AT').length;
  const allDone = disetujuiCount === sasaran.length;
  const hasPending = sasaran.some(s => s.status !== 'DISETUJUI_KT' && s.status !== 'DIKEMBALIKAN_AT' && s.status !== 'DIBATALKAN');

  const badgeClass = (status: string) => {
    if (status === 'DISETUJUI_KT') return 'bg-green-100 text-green-700';
    if (status === 'DIKEMBALIKAN_AT') return 'bg-orange-100 text-orange-700';
    if (status === 'DIBATALKAN') return 'bg-red-100 text-red-600';
    return 'bg-yellow-100 text-yellow-700';
  };
  const badgeLabel = (status: string) => {
    if (status === 'DISETUJUI_KT') return '✓ Disetujui';
    if (status === 'DIKEMBALIKAN_AT') return '↩ Dikembalikan ke AT';
    if (status === 'DIBATALKAN') return '✗ Dibatalkan';
    return 'Menunggu';
  };

  return (
    <div className="bg-white border border-indigo-200 rounded-lg p-4">
      <div className="flex justify-between items-start mb-3 gap-2 flex-wrap">
        <div>
          <h3 className="font-semibold text-primary-dark text-sm">
            Persetujuan Sasaran PKP — Ketua Tim
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Setujui semua sasaran untuk membuka Tahapan 5 (Konsep LHP). Sasaran yang dikembalikan ke AT harus dikoreksi terlebih dahulu.
          </p>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full font-semibold ${allDone ? 'bg-green-100 text-green-700' : dikembalikanCount > 0 ? 'bg-orange-100 text-orange-700' : 'bg-yellow-100 text-yellow-700'}`}>
          {disetujuiCount}/{sasaran.length} Disetujui
          {dikembalikanCount > 0 && ` · ${dikembalikanCount} dikembalikan`}
        </span>
      </div>

      {dikembalikanCount > 0 && (
        <div className="mb-3 p-2 rounded bg-orange-50 border border-orange-200 text-xs text-orange-800">
          Ada {dikembalikanCount} sasaran yang dikembalikan ke AT untuk dikoreksi. AT perlu memperbaiki langkah kerja sasaran tersebut sebelum KT dapat melanjutkan.
        </div>
      )}

      <div className="space-y-2 mb-3">
        {sasaran.map((s, i) => (
          <div key={s.sasaran_id} className={`flex items-center gap-2 p-2 rounded border bg-gray-50 ${s.status === 'DIKEMBALIKAN_AT' ? 'border-orange-200' : 'border-gray-100'}`}>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 ${badgeClass(s.status)}`}>
              {badgeLabel(s.status)}
            </span>
            <span className="text-xs flex-1 min-w-0 truncate" title={s.deskripsi}>
              <span className="font-mono text-gray-400 mr-1">{s.sasaran_id}</span>
              {s.deskripsi}
            </span>
            {s.status !== 'DIBATALKAN' && (
              <div className="flex gap-1 shrink-0">
                {s.status !== 'DISETUJUI_KT' && (
                  <button
                    onClick={() => ubahStatus(i, 'DISETUJUI_KT')}
                    className="text-[11px] px-2 py-0.5 rounded bg-indigo-500 text-white hover:bg-indigo-600"
                  >
                    Setujui
                  </button>
                )}
                {s.status !== 'DIKEMBALIKAN_AT' && (
                  <button
                    onClick={() => ubahStatus(i, 'DIKEMBALIKAN_AT')}
                    className="text-[11px] px-2 py-0.5 rounded bg-orange-500 text-white hover:bg-orange-600"
                  >
                    Tidak Setujui
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {msg && (
        <div className={`text-xs p-2 rounded mb-3 ${msg.startsWith('Gagal') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
          {msg}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {hasPending && (
          <button
            onClick={setujuiSemua}
            disabled={saving}
            className="px-3 py-1.5 text-xs rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 font-semibold"
          >
            {saving ? 'Menyimpan…' : 'Setujui Semua yang Pending → Lanjut ke LHP'}
          </button>
        )}
        <button
          onClick={simpan}
          disabled={saving}
          className="px-3 py-1.5 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Menyimpan…' : 'Simpan Persetujuan'}
        </button>
        <button
          onClick={load}
          disabled={saving}
          className="px-2.5 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          ↻ Refresh
        </button>
      </div>
    </div>
  );
}

function TemuanReviewPanel({ penugasanId }: { penugasanId: number }) {
  const session = getSession();
  const canApprove = ['AT', 'KT', 'PT', 'PM'].includes(session?.role_aktif || '');
  const canReject = ['KT', 'PT', 'PM'].includes(session?.role_aktif || '');
  const canBulk = ['KT', 'PT', 'PM'].includes(session?.role_aktif || '');
  const canEdit = ['AT', 'KT', 'PT', 'PM'].includes(session?.role_aktif || '');

  const [items, setItems] = useState<TemuanReviewItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // Edit-mode per temuan: tid → form values
  const [editing, setEditing] = useState<Record<string, {
    judul_temuan: string;
    kondisi: string;
    kriteria: string;
    akibat: string;
  } | undefined>>({});

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.listTemuanReview(penugasanId);
      setItems(r.items);
      setCounts(r.counts);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [penugasanId]);

  const doApprove = async (tid: string) => {
    setBusy(tid); setMsg(null);
    try { await api.approveTemuan(penugasanId, tid); refresh(); }
    catch (e: any) { setMsg(`Gagal approve ${tid}: ${e.message}`); }
    finally { setBusy(null); }
  };
  const doReject = async (tid: string) => {
    if (!confirm(`Tolak temuan ${tid}? Tidak akan masuk KKP/LHR final.`)) return;
    setBusy(tid); setMsg(null);
    try { await api.rejectTemuan(penugasanId, tid); refresh(); }
    catch (e: any) { setMsg(`Gagal reject ${tid}: ${e.message}`); }
    finally { setBusy(null); }
  };
  const startEdit = (t: TemuanReviewItem) => {
    // Pre-fill dengan edit overlay yg sudah ada, atau pakai versi agen.
    const ef = t.edited_fields || {};
    setEditing((p) => ({
      ...p,
      [t.id_temuan]: {
        judul_temuan: ef.judul_temuan ?? t.judul ?? '',
        kondisi: ef.kondisi ?? t.kondisi ?? '',
        kriteria: ef.kriteria ?? t.kriteria ?? '',
        akibat: ef.akibat ?? t.akibat ?? '',
      },
    }));
    setExpanded((p) => ({ ...p, [t.id_temuan]: true })); // auto-expand
  };
  const cancelEdit = (tid: string) => {
    setEditing((p) => { const c = { ...p }; delete c[tid]; return c; });
  };
  const saveEdit = async (t: TemuanReviewItem) => {
    const form = editing[t.id_temuan];
    if (!form) return;
    // Hanya kirim field yang BERUBAH dari versi asli agen (atau dari overlay sebelumnya)
    // Strategi sederhana: kirim semua 4 field; bila sama dengan versi agen
    // dan tidak ada overlay sebelumnya, backend tetap simpan (idempoten).
    setBusy(t.id_temuan); setMsg(null);
    try {
      await api.editTemuan(penugasanId, t.id_temuan, {
        judul_temuan: form.judul_temuan,
        kondisi: form.kondisi,
        kriteria: form.kriteria,
        akibat: form.akibat,
      });
      setMsg(`Edit tersimpan untuk ${t.id_temuan}.`);
      cancelEdit(t.id_temuan);
      refresh();
    } catch (e: any) {
      setMsg(`Gagal edit ${t.id_temuan}: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };
  const clearOverlay = async (t: TemuanReviewItem) => {
    if (!confirm(`Hapus semua edit overlay untuk ${t.id_temuan}? Kembali ke versi asli agen.`)) return;
    setBusy(t.id_temuan); setMsg(null);
    try {
      await api.editTemuan(penugasanId, t.id_temuan, {
        judul_temuan: '',
        kondisi: '',
        kriteria: '',
        akibat: '',
      });
      setMsg(`Overlay edit ${t.id_temuan} dihapus.`);
      refresh();
    } catch (e: any) {
      setMsg(`Gagal hapus edit ${t.id_temuan}: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };
  const doBulkApprove = async () => {
    const pending = counts['PENDING'] || 0;
    if (!pending) return;
    if (!confirm(`Setujui ${pending} temuan PENDING sekaligus?`)) return;
    setBusy('bulk'); setMsg(null);
    try {
      const r = await api.bulkApproveTemuan(penugasanId);
      setMsg(`${r.approved_count} temuan disetujui.`);
      refresh();
    } catch (e: any) { setMsg(`Gagal bulk approve: ${e.message}`); }
    finally { setBusy(null); }
  };

  if (loading) {
    return <div className="mb-4 p-3 text-xs text-gray-400 italic">Memuat status review temuan…</div>;
  }
  if (items.length === 0) {
    return null; // hide panel jika tidak ada temuan
  }

  return (
    <div className="mb-4 bg-white border border-emerald-200 rounded-lg p-4">
      <div className="flex justify-between items-start mb-2 gap-2 flex-wrap">
        <div>
          <h3 className="font-semibold text-primary-dark">
            ✓ Review Temuan <span className="text-xs font-normal text-emerald-700">· {items.length} temuan · HITL per-temuan</span>
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Setujui/tolak tiap temuan sebelum render KKP & LHR final. Default <code>PENDING</code> saat agen baru tulis.
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
        <button
          onClick={refresh}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          title="Refresh daftar temuan"
        >
          {loading ? '…' : '↻ Refresh'}
        </button>
        {canBulk && (counts['PENDING'] || 0) > 0 && (
          <button
            onClick={doBulkApprove}
            disabled={busy !== null}
            className="px-3 py-1.5 text-xs rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 whitespace-nowrap"
          >
            {busy === 'bulk' ? 'Memproses…' : `✓ Setujui semua ${counts['PENDING']} pending`}
          </button>
        )}
        </div>
      </div>

      <div className="text-xs text-gray-600 mb-2 flex gap-3 flex-wrap">
        {Object.entries(counts).map(([s, n]) =>
          n > 0 ? (
            <span key={s} className={`px-1.5 py-0.5 rounded border ${REVIEW_STATUS_COLOR[s] || 'bg-gray-100'}`}>
              {s}: {n}
            </span>
          ) : null
        )}
      </div>

      {msg && <div className="mb-2 p-2 text-xs rounded bg-emerald-50 border border-emerald-200 text-emerald-800">{msg}</div>}

      <div className="space-y-1.5">
        {items.map((t) => (
          <div key={t.id_temuan} className="border border-gray-200 rounded">
            <div className="px-3 py-2 flex justify-between items-start gap-2 flex-wrap">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-[11px] text-gray-500">{t.id_temuan}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${REVIEW_STATUS_COLOR[t.status] || 'bg-gray-100'}`}>
                    {t.status}
                  </span>
                  {t.sasaran_id && <span className="text-[10px] text-gray-400">{t.sasaran_id}</span>}
                  {t.anggota && <span className="text-[10px] text-gray-400">· {t.anggota}</span>}
                  <span className="text-[10px] text-gray-400">· {t.dokumen_sumber_count} sumber</span>
                </div>
                <div className="text-xs text-gray-800 mt-0.5">
                  {t.judul}
                  {t.has_edits && (
                    <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300">
                      ✎ diedit
                    </span>
                  )}
                </div>
                {expanded[t.id_temuan] && !editing[t.id_temuan] && (
                  <div className="text-[11px] text-gray-600 mt-2 space-y-1 pl-3 border-l-2 border-gray-200">
                    {t.kondisi && <div><b>Kondisi:</b> {t.kondisi}</div>}
                    {t.kriteria && <div><b>Kriteria:</b> {t.kriteria}</div>}
                    {t.akibat && <div><b>Akibat:</b> {t.akibat}</div>}
                  </div>
                )}
                {editing[t.id_temuan] && (
                  <div className="text-[11px] mt-2 space-y-2 pl-3 border-l-2 border-amber-300">
                    <div>
                      <label className="block text-gray-500 mb-0.5">Judul</label>
                      <input
                        type="text"
                        value={editing[t.id_temuan]!.judul_temuan}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            [t.id_temuan]: { ...p[t.id_temuan]!, judul_temuan: e.target.value },
                          }))
                        }
                        className="w-full px-2 py-1 border border-gray-300 rounded text-[11px]"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-500 mb-0.5">Kondisi</label>
                      <textarea
                        value={editing[t.id_temuan]!.kondisi}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            [t.id_temuan]: { ...p[t.id_temuan]!, kondisi: e.target.value },
                          }))
                        }
                        rows={3}
                        className="w-full px-2 py-1 border border-gray-300 rounded text-[11px] font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-500 mb-0.5">Kriteria</label>
                      <textarea
                        value={editing[t.id_temuan]!.kriteria}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            [t.id_temuan]: { ...p[t.id_temuan]!, kriteria: e.target.value },
                          }))
                        }
                        rows={3}
                        className="w-full px-2 py-1 border border-gray-300 rounded text-[11px] font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-500 mb-0.5">Akibat</label>
                      <textarea
                        value={editing[t.id_temuan]!.akibat}
                        onChange={(e) =>
                          setEditing((p) => ({
                            ...p,
                            [t.id_temuan]: { ...p[t.id_temuan]!, akibat: e.target.value },
                          }))
                        }
                        rows={2}
                        className="w-full px-2 py-1 border border-gray-300 rounded text-[11px] font-mono"
                      />
                    </div>
                    <div className="flex gap-1 pt-1">
                      <button
                        onClick={() => saveEdit(t)}
                        disabled={busy !== null}
                        className="text-[11px] px-2.5 py-0.5 rounded bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
                      >
                        {busy === t.id_temuan ? '…' : '💾 Simpan edit'}
                      </button>
                      <button
                        onClick={() => cancelEdit(t.id_temuan)}
                        disabled={busy !== null}
                        className="text-[11px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                      >
                        Batal
                      </button>
                      {t.has_edits && (
                        <button
                          onClick={() => clearOverlay(t)}
                          disabled={busy !== null}
                          className="text-[11px] px-2 py-0.5 rounded border border-red-300 text-red-600 hover:bg-red-50 ml-auto"
                          title="Hapus semua overlay edit, kembali ke versi agen"
                        >
                          ↶ Hapus edit
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  onClick={() => setExpanded((p) => ({ ...p, [t.id_temuan]: !p[t.id_temuan] }))}
                  className="text-[11px] px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                >
                  {expanded[t.id_temuan] ? 'tutup' : 'detail'}
                </button>
                {canEdit && !editing[t.id_temuan] && (
                  <button
                    onClick={() => startEdit(t)}
                    disabled={busy !== null}
                    className="text-[11px] px-2 py-0.5 rounded border border-amber-400 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                  >
                    ✎ Edit
                  </button>
                )}
                {canApprove && t.status !== 'APPROVED' && (
                  <button
                    onClick={() => doApprove(t.id_temuan)}
                    disabled={busy !== null}
                    className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {busy === t.id_temuan ? '…' : '✓ Setujui'}
                  </button>
                )}
                {canReject && t.status !== 'REJECTED' && (
                  <button
                    onClick={() => doReject(t.id_temuan)}
                    disabled={busy !== null}
                    className="text-[11px] px-2 py-0.5 rounded bg-red-500 text-white hover:bg-red-600 disabled:opacity-50"
                  >
                    ✗ Tolak
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
