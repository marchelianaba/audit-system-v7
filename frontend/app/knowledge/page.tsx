'use client';

// Halaman Knowledge / Wiki.
// W1 (AKTIF): panel "Cari Wiki" — baca vault pengetahuan organisasi (read-only).
// W2 (AKTIF): Promosi Pattern — agregasi usulan pattern dari feedback agen.
// W3 (AKTIF): Tulis-balik Vault — penugasan LHP_DONE → draft catatan vault
//             (Karpathy format) dengan Download .md (opsi A, Obsidian) atau
//             Apply ke vault (opsi B). Lihat lib/api.ts → getWritebackCandidates.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, clearToken, getSession, Session, SkillInfo } from '@/lib/api';
import { AppShell } from '@/components/AppShell';

type SearchResult = {
  name: string;
  section: string;
  summary: string;
  path: string;
  score: number;
  snippet: string;
};

type PatternCandidate = {
  judul: string;
  id_proposed: string;
  count: number;
  rationales: string[];
  skills: Record<string, number>;
  suggested_skill: string;
  penugasan: { folder: string; obyek: string; skill: string }[];
  already_exists: boolean;
  existing_id: string | null;
};

export default function KnowledgePage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [session, setSession] = useState<Session | null>(null);

  // Cari Wiki (W1)
  const [q, setQ] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [notConfigured, setNotConfigured] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Preview catatan
  const [selected, setSelected] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string>('');
  const [loadingPage, setLoadingPage] = useState(false);

  useEffect(() => {
    setMounted(true);
    const s = getSession();
    setSession(s);
    if (!s) router.push('/login');
  }, [router]);

  const handleLogout = () => {
    clearToken();
    router.push('/login');
  };

  const runSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!q.trim()) return;
    setSearching(true);
    setError(null);
    setNotConfigured(null);
    setSelected(null);
    setPageContent('');
    try {
      const res = await api.searchWiki(q.trim(), 20);
      if (!res.configured) {
        setNotConfigured(res.message || 'Vault tidak dikonfigurasi (set APP_VAULT_PATH).');
        setResults([]);
      } else {
        setResults(res.results);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const openPage = async (name: string) => {
    setSelected(name);
    setLoadingPage(true);
    setPageContent('');
    try {
      const res = await api.getWikiPage(name);
      setPageContent(res.found ? (res.content || '') : (res.message || 'Catatan tidak ditemukan.'));
    } catch (err: any) {
      setPageContent(`Gagal memuat: ${err.message}`);
    } finally {
      setLoadingPage(false);
    }
  };

  if (!mounted) return <main className="min-h-screen" />;
  if (!session) return null;

  return (
    <AppShell>

      <div className="max-w-6xl mx-auto p-6">
        <h1 className="text-2xl font-bold text-primary-dark mb-1">Knowledge / Wiki</h1>
        <p className="text-sm text-gray-500 mb-2">
          Pusat pengetahuan tim Inspektorat II. Empat panel di bawah saling melengkapi:
        </p>
        <ul className="text-xs text-gray-500 mb-5 space-y-0.5 list-disc list-inside">
          <li><b>Pattern Temuan</b> — 65+ pattern terkurasi yang dipakai agen sebagai acuan menyusun temuan (semua role bisa baca).</li>
          <li><b>Kriteria CACM</b> — definisi MERAH/KUNING/HIJAU yang dipakai mesin evaluator v7-native atas data SIRUP/DIPA/SPSE/Kinerja.</li>
          <li><b>Cari Wiki</b> — pencarian luas di vault organisasi (catatan BPK, profil auditi, dll).</li>
          <li><b>Promosi Pattern</b> & <b>Graduasi Skill</b> — workflow PT/PM untuk memperkaya pengetahuan dari penugasan nyata.</li>
          <li><b>Tulis-balik Vault</b> — saat penugasan selesai, hasilnya ditulis ke vault sebagai catatan operasional.</li>
        </ul>

        {/* ===== Pattern Library (semua role) — dinaikkan ke atas supaya tinggi visibility ===== */}
        <PatternLibraryPanel />

        {/* ===== Kriteria CACM (semua role baca) ===== */}
        <CacmKriteriaPanel />

        {/* ===== W1: Cari Wiki ===== */}
        <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold text-primary-dark mb-1">Cari Wiki (vault organisasi)</h2>
          <p className="text-xs text-gray-500 mb-3">
            Pencarian luas di catatan vault <code>llm-wiki</code> (ratusan dokumen non-rahasia hasil ingest: profil
            auditi, riwayat BPK, vendor, regulasi). Beda dari <b>Pattern Temuan</b> di atas — pattern adalah
            template terkurasi; vault ini sumber konteks bebas-format. Agen juga memanggil pencarian ini.
          </p>
          <form onSubmit={runSearch} className="flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="mis. temuan BPK PSTE, profil Ditjen Ekosdig, vendor …"
              className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={searching || !q.trim()}
              className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-dark disabled:opacity-40"
            >
              {searching ? 'Mencari…' : 'Cari'}
            </button>
          </form>

          {error && (
            <div className="mt-3 p-2 rounded bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
          )}
          {notConfigured && (
            <div className="mt-3 p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-sm">
              {notConfigured}
            </div>
          )}

          {results && (
            <div className="mt-4 grid md:grid-cols-2 gap-4">
              {/* Daftar hasil */}
              <div className="space-y-2 max-h-[460px] overflow-y-auto">
                {results.length === 0 && !notConfigured ? (
                  <p className="text-sm text-gray-400 italic">Tidak ada hasil untuk "{q}".</p>
                ) : (
                  results.map((r) => (
                    <button
                      key={r.path}
                      onClick={() => openPage(r.name)}
                      className={`w-full text-left border rounded p-3 hover:bg-gray-50 transition ${
                        selected === r.name ? 'border-primary bg-blue-50/40' : 'border-gray-200'
                      }`}
                    >
                      <div className="flex justify-between items-baseline gap-2">
                        <span className="font-medium text-sm text-primary-dark">{r.name}</span>
                        {r.section && (
                          <span className="text-[11px] text-gray-400 shrink-0">{r.section}</span>
                        )}
                      </div>
                      {r.summary && <div className="text-xs text-gray-600 mt-0.5">{r.summary}</div>}
                      {r.snippet && (
                        <div className="text-xs text-gray-400 mt-1 line-clamp-2">…{r.snippet}</div>
                      )}
                    </button>
                  ))
                )}
              </div>

              {/* Preview catatan */}
              <div className="border border-gray-200 rounded p-3 bg-gray-50 max-h-[460px] overflow-y-auto">
                {!selected ? (
                  <p className="text-sm text-gray-400 italic">Klik salah satu hasil untuk membaca isinya.</p>
                ) : loadingPage ? (
                  <p className="text-sm text-gray-400 italic">Memuat {selected}…</p>
                ) : (
                  <>
                    <div className="text-xs font-semibold text-gray-500 mb-2">{selected}.md</div>
                    <pre className="text-xs whitespace-pre-wrap font-sans text-gray-800">{pageContent}</pre>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ===== W2: Promosi Pattern (PT/PM) ===== */}
        {(session.role_aktif === 'PT' || session.role_aktif === 'PM') && <PatternMonitorPanel />}

        {/* ===== Graduasi (PT/PM) ===== */}
        {(session.role_aktif === 'PT' || session.role_aktif === 'PM') && <GraduasiPanel />}

        {/* ===== W3: Tulis-balik Vault (semua role bisa lihat; aksi tergantung role) ===== */}
        <WritebackPanel role={session.role_aktif} />
      </div>
    </AppShell>
  );
}

// Panel Promosi Pattern (PT/PM): pantau usulan pattern dari feedback agen lintas
// penugasan, lalu promote yang berulang jadi pattern wiki resmi. Human-in-the-loop.
type PromoteForm = {
  skill: string;
  pattern_id: string;
  judul: string;
  kategori: string;
  severity: string;
  kriteria_baku: string;
  kondisi: string;
  akibat: string;
  rekomendasi: string;
  bukti: string;
  tags: string;
  sumber_penugasan: string[];
};

const EMPTY_FORM: PromoteForm = {
  skill: '', pattern_id: '', judul: '', kategori: '', severity: 'MEDIUM',
  kriteria_baku: '', kondisi: '', akibat: '', rekomendasi: '', bukti: '', tags: '', sumber_penugasan: [],
};

function PatternMonitorPanel() {
  const [candidates, setCandidates] = useState<PatternCandidate[]>([]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [totalSug, setTotalSug] = useState(0);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<PromoteForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    api.getPatternMonitor(90)
      .then((r) => { setCandidates(r.candidates); setTotalSug(r.total_suggestions); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    refresh();
    api.getSkills().then(setSkills).catch(() => {});
  }, []);

  const openFromCandidate = (c: PatternCandidate) => {
    setMsg(null);
    setForm({
      ...EMPTY_FORM,
      skill: c.suggested_skill || '',
      pattern_id: c.already_exists ? '' : c.id_proposed,
      judul: c.judul,
      kondisi: c.rationales.join('\n'),
      sumber_penugasan: c.penugasan.map((p) => p.obyek).filter(Boolean),
    });
  };

  const setField = (k: keyof PromoteForm, v: string) =>
    setForm((f) => (f ? { ...f, [k]: v } : f));

  const submit = async () => {
    if (!form) return;
    if (!form.skill || !form.pattern_id.trim() || !form.judul.trim()) {
      setMsg('Skill, ID pattern, dan judul wajib.');
      return;
    }
    setBusy(true); setMsg(null);
    try {
      const r = await api.promotePattern({
        skill: form.skill,
        pattern_id: form.pattern_id.trim(),
        judul: form.judul.trim(),
        kategori: form.kategori.trim(),
        severity: form.severity,
        kriteria_baku: form.kriteria_baku.trim(),
        kondisi: form.kondisi.trim(),
        akibat: form.akibat.trim(),
        rekomendasi: form.rekomendasi.trim(),
        bukti: form.bukti.trim(),
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        sumber_penugasan: form.sumber_penugasan,
      });
      setMsg(`Pattern ${r.id} ditulis ke ${r.file}${r.readme_updated ? ' (index README diperbarui)' : ''}.`);
      setForm(null);
      refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="mb-6 bg-white border border-emerald-200 rounded-lg p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold text-primary-dark">Promosi Pattern (PT/PM)</h2>
        <button
          onClick={() => { setMsg(null); setForm({ ...EMPTY_FORM }); }}
          className="text-[11px] px-2 py-0.5 rounded border border-emerald-300 text-emerald-700 hover:bg-emerald-50"
        >
          + Pattern manual
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-2">
        Usulan pattern dari feedback agen lintas penugasan (90 hari). Yang <b>berulang</b> &amp;
        belum ada di wiki = kandidat kuat. Klik kandidat untuk menyunting lalu <b>Promote</b> jadi
        pattern resmi. {totalSug > 0 && <span className="text-gray-400">({totalSug} usulan mentah)</span>}
      </p>

      <HowToUse
        color="emerald"
        when="Setelah beberapa penugasan jalan, agen meninggalkan pattern_suggestions di feedback. Anda sebagai PT/PM kurasi mana yg layak jadi pattern resmi (akan dipakai agen di penugasan berikutnya)."
        steps={[
          'Lihat daftar kandidat — sistem auto-group judul yang mirip dan menghitung frekuensi (×N) lintas penugasan.',
          'Klik kandidat → form pre-filled (skill, judul, kondisi dari feedback). Lengkapi kriteria_baku (pasal/ayat WAJIB), akibat, rekomendasi standar.',
          'Severity: CRITICAL untuk pelanggaran peraturan inti (Perpres/PMK/UU); HIGH = kepatuhan substantif; MEDIUM/LOW = best-practice.',
          'Klik Promote → file pattern .md ditulis ke wiki/temuan-patterns/{skill}/; README index ter-update.',
        ]}
        example="3 penugasan terakhir feedback agen menyarankan pattern 'HPS tidak mencantumkan Perpres 12/2021' (×3, belum ada). Klik → isi kriteria_baku 'Perpres 16/2018 jo. Perpres 12/2021 Pasal 26' → severity MEDIUM → Promote."
      />

      {msg && <div className="mb-3 p-2 rounded bg-emerald-50 text-emerald-800 text-xs">{msg}</div>}

      {form ? (
        <PromoteFormView
          form={form} skills={skills} busy={busy}
          onField={setField} onCancel={() => setForm(null)} onSubmit={submit}
        />
      ) : (
        <div className="border border-gray-200 rounded max-h-80 overflow-y-auto divide-y">
          {loading ? (
            <div className="p-3 text-xs text-gray-400 italic">Memuat kandidat…</div>
          ) : candidates.length === 0 ? (
            <div className="p-3 text-xs text-gray-400 italic">
              Belum ada usulan pattern dari feedback agen. Jalankan agen AT/KT — usulan muncul di sini.
            </div>
          ) : candidates.map((c) => (
            <button
              key={c.judul}
              onClick={() => openFromCandidate(c)}
              className="w-full text-left p-3 hover:bg-emerald-50/40 transition"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium text-gray-800">{c.judul}</span>
                <span className="flex items-center gap-1 shrink-0">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">×{c.count}</span>
                  {c.already_exists ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">sudah ada: {c.existing_id}</span>
                  ) : c.id_proposed ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">{c.id_proposed}</span>
                  ) : null}
                </span>
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5">
                {c.suggested_skill && <span className="uppercase">{c.suggested_skill}</span>}
                {c.penugasan.length > 0 && <span> · {c.penugasan.length} penugasan</span>}
              </div>
              {c.rationales[0] && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{c.rationales[0]}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function PromoteFormView({
  form, skills, busy, onField, onCancel, onSubmit,
}: {
  form: PromoteForm;
  skills: SkillInfo[];
  busy: boolean;
  onField: (k: keyof PromoteForm, v: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const inp = 'w-full border border-gray-300 rounded px-2 py-1.5 text-xs';
  const lbl = 'block text-[11px] font-semibold text-gray-600 mb-0.5';
  return (
    <div className="border border-gray-200 rounded p-3 space-y-2.5">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={lbl}>Skill (folder target) *</label>
          <select value={form.skill} onChange={(e) => onField('skill', e.target.value)} className={inp}>
            <option value="">— pilih skill —</option>
            {skills.map((s) => <option key={s.slug} value={s.slug}>{s.slug}</option>)}
          </select>
        </div>
        <div>
          <label className={lbl}>ID Pattern * (mis. RP-17)</label>
          <input value={form.pattern_id} onChange={(e) => onField('pattern_id', e.target.value)} className={inp} placeholder="RP-17" />
        </div>
      </div>
      <div>
        <label className={lbl}>Judul *</label>
        <input value={form.judul} onChange={(e) => onField('judul', e.target.value)} className={inp} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={lbl}>Kategori</label>
          <input value={form.kategori} onChange={(e) => onField('kategori', e.target.value)} className={inp} placeholder="mis. PBJ-KONTRAK" />
        </div>
        <div>
          <label className={lbl}>Severity</label>
          <select value={form.severity} onChange={(e) => onField('severity', e.target.value)} className={inp}>
            {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className={lbl}>Kriteria Baku (sebut pasal/ayat)</label>
        <input value={form.kriteria_baku} onChange={(e) => onField('kriteria_baku', e.target.value)} className={inp} placeholder="mis. Perpres 16/2018 Pasal 26 ayat (5)" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={lbl}>Kondisi</label>
          <textarea value={form.kondisi} onChange={(e) => onField('kondisi', e.target.value)} className={inp} rows={3} />
        </div>
        <div>
          <label className={lbl}>Akibat</label>
          <textarea value={form.akibat} onChange={(e) => onField('akibat', e.target.value)} className={inp} rows={3} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={lbl}>Bukti yang dicari</label>
          <textarea value={form.bukti} onChange={(e) => onField('bukti', e.target.value)} className={inp} rows={2} />
        </div>
        <div>
          <label className={lbl}>Rekomendasi</label>
          <textarea value={form.rekomendasi} onChange={(e) => onField('rekomendasi', e.target.value)} className={inp} rows={2} />
        </div>
      </div>
      <div>
        <label className={lbl}>Tags (pisahkan koma)</label>
        <input value={form.tags} onChange={(e) => onField('tags', e.target.value)} className={inp} placeholder="kontrak, sla, denda" />
      </div>
      {form.sumber_penugasan.length > 0 && (
        <div className="text-[11px] text-gray-400">Sumber: {form.sumber_penugasan.join(', ')}</div>
      )}
      <div className="flex gap-2 pt-1">
        <button onClick={onSubmit} disabled={busy} className="text-xs px-3 py-1.5 rounded bg-emerald-600 text-white font-medium disabled:opacity-50">
          {busy ? 'Menyimpan…' : 'Promote ke Wiki'}
        </button>
        <button onClick={onCancel} disabled={busy} className="text-xs px-3 py-1.5 rounded border border-gray-300 text-gray-600 disabled:opacity-50">
          Batal
        </button>
      </div>
    </div>
  );
}

// Panel Graduasi (PT/PM): pilih penugasan sejenis → suling jadi DRAFT skill →
// reviu → promote ke registry. Human-in-the-loop.
function GraduasiPanel() {
  const [groups, setGroups] = useState<{ skill: string; penugasan: { kode: string; obyek: string; n_temuan: number }[] }[]>([]);
  const [drafts, setDrafts] = useState<{ nama: string; skill_induk?: string; n_temuan?: number }[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = () => {
    api.getGraduasiCandidates().then((r) => setGroups(r.groups)).catch(() => {});
    api.getGraduasiDrafts().then((r) => setDrafts(r.drafts)).catch(() => {});
  };
  useEffect(() => { refresh(); }, []);

  const toggle = (kode: string) => setPicked((p) => ({ ...p, [kode]: !p[kode] }));
  const selected = Object.keys(picked).filter((k) => picked[k]);

  const run = async () => {
    if (selected.length === 0) { setMsg('Pilih ≥1 penugasan dulu.'); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await api.runGraduasi(selected);
      setMsg(`Draft "${r.nama}" dibuat (${r.n_temuan} temuan, ${r.n_redflag} pola). Reviu lalu Promote.`);
      setPicked({}); refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };
  const act = async (nama: string, kind: 'promote' | 'reject') => {
    if (kind === 'reject' && !confirm(`Tolak & hapus draft "${nama}"?`)) return;
    if (kind === 'promote' && !confirm(`Promote draft "${nama}" jadi skill aktif di registry?`)) return;
    setBusy(true); setMsg(null);
    try {
      if (kind === 'promote') { await api.promoteGraduasi(nama); setMsg(`Skill "${nama}" dipromote & terdaftar.`); }
      else { await api.rejectGraduasi(nama); setMsg(`Draft "${nama}" ditolak.`); }
      refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="mb-6 bg-white border border-violet-200 rounded-lg p-5">
      <h2 className="font-semibold text-primary-dark mb-1">Graduasi Skill (PT/PM)</h2>
      <p className="text-xs text-gray-500 mb-2">
        Suling pola dari penugasan sejenis (skill sama) menjadi DRAFT skill spesifik. Generate = draft;
        Anda reviu lalu <b>Promote</b> agar terdaftar. Human-in-the-loop.
      </p>

      <HowToUse
        color="violet"
        when="Setelah ≥2 penugasan dengan skill yang sama selesai dan punya temuan, pola berulang yang muncul lintas penugasan layak di-graduasi jadi skill turunan spesifik (mis. reviu-pengadaan → reviu-pengadaan-cloud)."
        steps={[
          'Lihat kandidat penugasan ber-temuan, di-group per skill induk.',
          'Centang ≥2 penugasan dari skill induk yang sama (skill berbeda akan ditolak).',
          'Klik ⚗ Graduasikan → algoritma deteksi domain term, konsolidasi kriteria, cluster temuan (Jaccard). Output: file DRAFT di knowledge/skills/_draft/<nama>/ (SKILL.md + regulasi.md + checklist.md).',
          'Reviu draft di kolom kanan → Promote (skill aktif di registry, ikut muncul di dropdown jenis penugasan) atau Tolak.',
        ]}
        example="3 penugasan reviu-pengadaan terakhir semua tentang cloud (AWS/Azure/GCP). Centang ketiganya → ⚗ → draft 'reviu-pengadaan-cloud' dgn regulasi & checklist khusus cloud → Promote."
      />

      {msg && <div className="mb-3 p-2 rounded bg-violet-50 text-violet-800 text-xs">{msg}</div>}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <div className="text-xs font-semibold text-gray-600 mb-1">Kandidat penugasan (punya temuan)</div>
          <div className="border border-gray-200 rounded max-h-60 overflow-y-auto divide-y">
            {groups.length === 0 ? (
              <div className="p-3 text-xs text-gray-400 italic">Belum ada penugasan ber-temuan.</div>
            ) : groups.map((g) => (
              <div key={g.skill} className="p-2">
                <div className="text-[11px] uppercase text-gray-400 mb-1">{g.skill}</div>
                {g.penugasan.map((p) => (
                  <label key={p.kode} className="flex items-start gap-2 text-xs py-0.5 cursor-pointer">
                    <input type="checkbox" checked={!!picked[p.kode]} onChange={() => toggle(p.kode)} className="mt-0.5" />
                    <span className="text-gray-700">{p.obyek} <span className="text-gray-400">({p.n_temuan} temuan)</span></span>
                  </label>
                ))}
              </div>
            ))}
          </div>
          <button onClick={run} disabled={busy} className="mt-2 text-xs px-3 py-1.5 rounded bg-violet-600 text-white font-medium disabled:opacity-50">
            ⚗ Graduasikan {selected.length > 0 ? `(${selected.length})` : ''}
          </button>
        </div>

        <div>
          <div className="text-xs font-semibold text-gray-600 mb-1">Draft skill (perlu reviu)</div>
          <div className="border border-gray-200 rounded max-h-60 overflow-y-auto divide-y">
            {drafts.length === 0 ? (
              <div className="p-3 text-xs text-gray-400 italic">Belum ada draft.</div>
            ) : drafts.map((d) => (
              <div key={d.nama} className="p-2 flex items-center justify-between gap-2">
                <span className="text-xs text-gray-700">{d.nama} <span className="text-gray-400">← {d.skill_induk}</span></span>
                <span className="flex gap-1 shrink-0">
                  <button onClick={() => act(d.nama, 'promote')} disabled={busy} className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 text-white disabled:opacity-50">Promote</button>
                  <button onClick={() => act(d.nama, 'reject')} disabled={busy} className="text-[11px] px-2 py-0.5 rounded bg-gray-400 text-white disabled:opacity-50">Tolak</button>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// W3 — Tulis-balik Vault
//
// Penugasan LHP_DONE → draft pengawasan-<kode>.md (Karpathy format) + delta
// index/log. Auditor (PT/PM/KT) klik "Generate", review preview, lalu pilih:
//   • Download .md (opsi A — rekomendasi, di-apply manual via Obsidian; semua role)
//   • Apply ke vault (opsi B — app tulis langsung; PT/PM only)
//   • Regenerate / Reject
// =============================================================================

type WritebackCandidate = {
  penugasan_id: number;
  kode: string;
  obyek: string;
  skill: string;
  lhp_done_at: string | null;
  proposal_status: 'NONE' | 'DRAFT' | 'APPLIED' | 'REJECTED';
  nama_file: string | null;
};

type WritebackProposal = {
  id: number;
  penugasan_id: number;
  nama_file: string;
  ringkasan: string | null;
  status: string;
  konten_md: string;
  delta_index: string | null;
  delta_log: string | null;
  dibuat_at?: string | null;
  diupdate_at?: string | null;
  applied_at?: string | null;
};

function statusBadge(s: WritebackCandidate['proposal_status']) {
  const cls =
    s === 'APPLIED' ? 'bg-emerald-100 text-emerald-800' :
    s === 'DRAFT'   ? 'bg-amber-100 text-amber-800' :
    s === 'REJECTED'? 'bg-gray-200 text-gray-600' :
                      'bg-gray-100 text-gray-500';
  const label = s === 'NONE' ? 'belum digenerate' : s.toLowerCase();
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${cls}`}>{label}</span>;
}

function WritebackPanel({ role }: { role: string }) {
  const canEdit = role === 'PT' || role === 'PM' || role === 'KT';
  const canApply = role === 'PT' || role === 'PM';

  const [items, setItems] = useState<WritebackCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<WritebackCandidate | null>(null);
  const [proposal, setProposal] = useState<WritebackProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<'md' | 'index' | 'log'>('md');

  const refresh = () => {
    setLoading(true);
    api.getWritebackCandidates()
      .then((r) => setItems(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { refresh(); }, []);

  const openCandidate = async (c: WritebackCandidate) => {
    setSelected(c); setProposal(null); setMsg(null); setTab('md');
    if (c.proposal_status !== 'NONE') {
      try {
        setBusy(true);
        const p = await api.getWritebackProposal(c.penugasan_id);
        setProposal(p);
      } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
    }
  };

  const doGenerate = async () => {
    if (!selected) return;
    setBusy(true); setMsg(null);
    try {
      const p = await api.generateWritebackProposal(selected.penugasan_id);
      setProposal(p);
      setMsg('Draft dibuat ulang (status: DRAFT).');
      refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  const doApply = async () => {
    if (!selected) return;
    if (!confirm(`Apply ke vault?\n\nFile pengawasan-<kode>.md akan ditulis langsung ke folder vault. Index & log juga di-update.\n\nKalau ragu, pilih "Download .md" sebagai gantinya — lebih aman, kamu apply manual via Obsidian.`)) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.applyWritebackProposal(selected.penugasan_id);
      setMsg(`Diterapkan ke vault. index: ${r.apply_result.index.reason}; log: ${r.apply_result.log.reason}.`);
      if (proposal) setProposal({ ...proposal, status: r.status });
      refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  const doReject = async () => {
    if (!selected) return;
    if (!confirm('Tolak proposal ini? (status → REJECTED, tidak masuk vault)')) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.rejectWritebackProposal(selected.penugasan_id);
      if (proposal) setProposal({ ...proposal, status: r.status });
      setMsg('Proposal ditolak.');
      refresh();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };

  const doDownload = () => {
    if (!selected) return;
    window.location.href = api.getWritebackDownloadUrl(selected.penugasan_id);
  };

  return (
    <div className="mb-6 bg-white border border-sky-200 rounded-lg p-5">
      <h2 className="font-semibold text-primary-dark mb-1">Tulis-balik Vault (W3)</h2>
      <p className="text-xs text-gray-500 mb-2">
        Penugasan yang sudah <b>LHP_DONE</b> bisa diringkas jadi catatan vault (format Karpathy +
        sitasi). Auditor PT/PM/KT generate draft, lalu pilih <b>Download .md</b> (rekomendasi —
        apply manual lewat Obsidian) atau <b>Apply ke vault</b> (app tulis langsung; PT/PM saja).
      </p>

      <HowToUse
        color="sky"
        when="LHP penugasan terbit. Anda ingin pengetahuan operasional (siapa diaudit, ditemukan apa, dasar hukum mana) terakumulasi di vault organisasi, supaya bisa di-cite agen pada penugasan berikutnya via Cari Wiki."
        steps={[
          'Lihat daftar kandidat di kiri (penugasan LHP_DONE) — badge status: belum digenerate / draft / applied / rejected.',
          'Klik kandidat → kalau belum, tombol Generate draft (PT/PM/KT) menyusun pengawasan-{kode}.md deterministik dari temuan.json + rekomendasi.json.',
          'Preview 3 tab: file .md, delta index.md, delta log.md.',
          'Pilih jalur apply: Download .md (auditor curate manual via Obsidian, REKOMENDASI) atau Apply ke vault (PT/PM, app tulis langsung).',
        ]}
        example="Reviu RKA-K/L Dit. Pengembangan Ekosdig selesai. Generate → 4 temuan masuk catatan dgn cite Surat Tugas + KKP. Apply → file pengawasan-2026-05-reviurkakl-xxx.md tambah di vault, otomatis ter-index."
      />

      {msg && <div className="mb-3 p-2 rounded bg-sky-50 text-sky-800 text-xs">{msg}</div>}

      <div className="grid md:grid-cols-2 gap-3">
        {/* Daftar kandidat */}
        <div className="border border-gray-200 rounded max-h-[460px] overflow-y-auto divide-y">
          {loading ? (
            <div className="p-3 text-xs text-gray-400 italic">Memuat kandidat…</div>
          ) : items.length === 0 ? (
            <div className="p-3 text-xs text-gray-400 italic">
              Belum ada penugasan LHP_DONE. Selesaikan satu penugasan dulu (laporan terbit) — akan muncul di sini.
            </div>
          ) : items.map((c) => (
            <button
              key={c.penugasan_id}
              onClick={() => openCandidate(c)}
              className={`w-full text-left p-3 hover:bg-sky-50/40 transition ${selected?.penugasan_id === c.penugasan_id ? 'bg-sky-50' : ''}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium text-gray-800 line-clamp-2">{c.obyek}</span>
                {statusBadge(c.proposal_status)}
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5">
                <span className="uppercase">{c.skill}</span>
                <span> · {c.kode}</span>
                {c.lhp_done_at && <span> · {c.lhp_done_at.slice(0, 10)}</span>}
              </div>
            </button>
          ))}
        </div>

        {/* Preview proposal */}
        <div className="border border-gray-200 rounded p-3 min-h-[260px]">
          {!selected ? (
            <p className="text-xs text-gray-400 italic">Pilih satu penugasan di kiri untuk lihat draft.</p>
          ) : (
            <>
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="text-xs font-semibold text-gray-700">{selected.obyek}</div>
                  <div className="text-[11px] text-gray-400">
                    {selected.kode} · <span className="uppercase">{selected.skill}</span>
                  </div>
                </div>
                {proposal && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{proposal.status}</span>}
              </div>

              {!proposal ? (
                <div className="text-center py-6">
                  <p className="text-xs text-gray-500 mb-3">
                    Belum ada draft untuk penugasan ini.
                  </p>
                  {canEdit ? (
                    <button onClick={doGenerate} disabled={busy} className="px-3 py-1.5 rounded bg-sky-600 text-white text-xs font-semibold hover:bg-sky-700 disabled:opacity-50">
                      {busy ? 'Membuat…' : 'Generate draft'}
                    </button>
                  ) : (
                    <p className="text-[11px] text-gray-400 italic">Hanya PT/PM/KT yang bisa generate.</p>
                  )}
                </div>
              ) : (
                <>
                  <div className="flex gap-1 mb-2 text-[11px]">
                    {(['md', 'index', 'log'] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={`px-2 py-0.5 rounded ${tab === t ? 'bg-sky-600 text-white' : 'bg-gray-100 text-gray-600'}`}
                      >
                        {t === 'md' ? `${proposal.nama_file}` : t === 'index' ? 'delta index.md' : 'delta log.md'}
                      </button>
                    ))}
                  </div>
                  <pre className="text-[11px] whitespace-pre-wrap font-mono text-gray-800 bg-gray-50 rounded p-2 max-h-[300px] overflow-y-auto">
                    {tab === 'md' ? proposal.konten_md
                      : tab === 'index' ? (proposal.delta_index || '(kosong)')
                      : (proposal.delta_log || '(kosong)')}
                  </pre>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button onClick={doDownload} disabled={busy} className="px-3 py-1.5 rounded bg-primary text-white text-xs font-semibold hover:bg-primary-dark disabled:opacity-50">
                      Download .md
                    </button>
                    {canApply && (
                      <button onClick={doApply} disabled={busy || proposal.status === 'APPLIED'} className="px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
                        {proposal.status === 'APPLIED' ? 'Sudah di-apply' : 'Apply ke vault'}
                      </button>
                    )}
                    {canEdit && (
                      <button onClick={doGenerate} disabled={busy} className="px-3 py-1.5 rounded bg-gray-100 text-gray-700 text-xs font-semibold hover:bg-gray-200 disabled:opacity-50">
                        Regenerate
                      </button>
                    )}
                    {canApply && proposal.status !== 'REJECTED' && (
                      <button onClick={doReject} disabled={busy} className="px-3 py-1.5 rounded bg-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-400 disabled:opacity-50">
                        Tolak
                      </button>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// HowToUse — collapsible "Cara pakai" block, dipakai semua panel agar UX jelas.
// =============================================================================

function HowToUse({
  steps,
  when,
  example,
  color = 'sky',
}: {
  steps: string[];
  when: string;
  example?: string;
  color?: 'sky' | 'emerald' | 'violet' | 'amber';
}) {
  const [open, setOpen] = useState(false);
  const cls =
    color === 'emerald' ? 'border-emerald-200 bg-emerald-50/50 text-emerald-900' :
    color === 'violet'  ? 'border-violet-200 bg-violet-50/50 text-violet-900' :
    color === 'amber'   ? 'border-amber-200 bg-amber-50/50 text-amber-900' :
                          'border-sky-200 bg-sky-50/50 text-sky-900';
  return (
    <div className={`text-[11px] border rounded mb-3 ${cls}`}>
      <button onClick={() => setOpen(!open)} className="w-full px-2.5 py-1.5 flex items-center justify-between text-left">
        <span className="font-semibold">▸ Cara pakai &amp; kapan dipakai</span>
        <span className="opacity-60">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-3 pb-2.5 space-y-2">
          <div>
            <div className="font-semibold mb-0.5">Kapan dipakai</div>
            <p className="opacity-90">{when}</p>
          </div>
          <div>
            <div className="font-semibold mb-0.5">Langkah</div>
            <ol className="list-decimal list-inside space-y-0.5 opacity-90">
              {steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>
          {example && (
            <div>
              <div className="font-semibold mb-0.5">Contoh</div>
              <p className="opacity-90 italic">{example}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// PatternLibraryPanel — browser pattern temuan terkurasi (semua role).
// 65+ pattern lintas 12 skill, dgn filter skill / severity / search dan
// modal preview frontmatter + body markdown.
// =============================================================================

type PatternLibItem = {
  id: string;
  skill: string;
  kategori: string;
  severity: string;
  judul: string;
  kriteria_baku: string;
  tags: string[];
  file: string;
};

type PatternLibResp = {
  skills_available: string[];
  severities_available: string[];
  categories_available: string[];
  total_all: number;
  total_filtered: number;
  items: PatternLibItem[];
};

const SEV_COLOR: Record<string, string> = {
  CRITICAL: 'bg-red-100 text-red-800 border-red-300',
  HIGH:     'bg-orange-100 text-orange-800 border-orange-300',
  MEDIUM:   'bg-yellow-100 text-yellow-800 border-yellow-300',
  LOW:      'bg-gray-100 text-gray-600 border-gray-300',
};

function PatternLibraryPanel() {
  const [resp, setResp] = useState<PatternLibResp | null>(null);
  const [skill, setSkill] = useState('');
  const [severity, setSeverity] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ frontmatter: PatternLibItem; body: string } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const refresh = async () => {
    setLoading(true); setErr(null);
    try {
      const r = await api.listPatternLibrary({
        skill: skill || undefined,
        severity: severity || undefined,
        search: search || undefined,
      });
      setResp(r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    const t = setTimeout(() => { refresh(); }, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [skill, severity, search]);

  const openDetail = async (id: string) => {
    setSelected(id); setDetail(null); setDetailLoading(true);
    try {
      const r = await api.getPattern(id);
      const fm: PatternLibItem = {
        id: r.id, skill: r.skill, kategori: r.kategori, severity: r.severity,
        judul: r.judul, kriteria_baku: r.kriteria_baku, tags: r.tags, file: r.file,
      };
      setDetail({ frontmatter: fm, body: r.body_md });
    } catch (e: any) {
      setDetail({ frontmatter: null as any, body: `Gagal memuat: ${e.message}` });
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="mb-6 bg-white border border-sky-200 rounded-lg p-5">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <h2 className="font-semibold text-primary-dark">Pattern Temuan (jelajah manual)</h2>
        {resp && (
          <span className="text-[11px] text-gray-500">
            menampilkan <b>{resp.total_filtered}</b> / {resp.total_all} pattern
            {resp.skills_available.length > 0 && ` di ${resp.skills_available.length} skill`}
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-2">
        Daftar pattern temuan terkurasi yang dipakai agen sebagai acuan. Pelajari pola yang umum di
        organisasi sebelum/sesudah penugasan, atau jadikan referensi saat reviu KKP manual.
      </p>

      <HowToUse
        color="sky"
        when="Mau memahami pola temuan yang dipakai agen — atau cek apakah pola yang ada di pikiran kamu sudah pernah dirumuskan tim."
        steps={[
          'Pilih skill (mis. reviu-pengadaan) atau biarkan kosong untuk lihat semua.',
          'Filter severity (CRITICAL/HIGH/MEDIUM/LOW) bila ingin fokus risiko tertentu.',
          'Ketik kata kunci di Search (id, judul, kategori, regulasi, tag).',
          'Klik kartu untuk baca detail lengkap (kondisi, kriteria, akibat, rekomendasi, bukti).',
        ]}
        example="Cari 'hps' di skill reviu-pengadaan → muncul RP-08 (CRITICAL: HPS tidak didukung 2 sumber harga independen)."
      />

      <div className="grid sm:grid-cols-3 gap-2 mb-3">
        <select value={skill} onChange={(e) => setSkill(e.target.value)} className="border border-gray-300 rounded px-2 py-1.5 text-xs">
          <option value="">Semua skill ({resp?.skills_available.length ?? '…'})</option>
          {resp?.skills_available.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="border border-gray-300 rounded px-2 py-1.5 text-xs">
          <option value="">Semua severity</option>
          {resp?.severities_available.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="cari id/judul/regulasi/tag…" className="border border-gray-300 rounded px-2 py-1.5 text-xs" />
      </div>

      {err && <div className="mb-2 p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">{err}</div>}

      <div className="grid md:grid-cols-2 gap-3">
        {/* List */}
        <div className="border border-gray-200 rounded max-h-[480px] overflow-y-auto divide-y">
          {loading ? (
            <div className="p-3 text-xs text-gray-400 italic">Memuat pattern…</div>
          ) : (resp?.items.length ?? 0) === 0 ? (
            <div className="p-3 text-xs text-gray-400 italic">
              Tidak ada pattern yg cocok. Coba longgarkan filter atau cek folder <code>knowledge/wiki/temuan-patterns/</code>.
            </div>
          ) : resp!.items.map((p) => (
            <button
              key={`${p.skill}/${p.id}`}
              onClick={() => openDetail(p.id)}
              className={`w-full text-left p-2.5 hover:bg-sky-50/40 transition ${selected === p.id ? 'bg-sky-50' : ''}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-[11px] text-gray-500 shrink-0">{p.id}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${SEV_COLOR[p.severity] ?? 'bg-gray-100 text-gray-500 border-gray-300'}`}>
                  {p.severity || '—'}
                </span>
              </div>
              <div className="text-xs font-medium text-gray-800 mt-0.5">{p.judul || '(tanpa judul)'}</div>
              <div className="text-[10px] text-gray-400 mt-0.5">
                <span className="uppercase">{p.skill}</span>
                {p.kategori && <span> · {p.kategori}</span>}
              </div>
            </button>
          ))}
        </div>

        {/* Preview */}
        <div className="border border-gray-200 rounded p-3 bg-gray-50 min-h-[300px] max-h-[480px] overflow-y-auto">
          {!selected ? (
            <p className="text-xs text-gray-400 italic">Klik salah satu pattern di kiri untuk baca detail.</p>
          ) : detailLoading ? (
            <p className="text-xs text-gray-400 italic">Memuat {selected}…</p>
          ) : !detail ? (
            <p className="text-xs text-gray-400 italic">Tidak ada detail.</p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2 mb-2">
                <div>
                  <span className="font-mono text-[11px] text-gray-500">{detail.frontmatter?.id}</span>
                  <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded border ${SEV_COLOR[detail.frontmatter?.severity ?? ''] ?? 'bg-gray-100 text-gray-500 border-gray-300'}`}>
                    {detail.frontmatter?.severity || '—'}
                  </span>
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(detail.frontmatter?.id || '')}
                  className="text-[10px] px-1.5 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                  title="Salin ID — pakai di Chat KT/AT sebagai referensi pattern"
                >
                  ⧉ salin ID
                </button>
              </div>
              {detail.frontmatter && (
                <>
                  <div className="text-sm font-semibold text-gray-800 mb-1">{detail.frontmatter.judul}</div>
                  <div className="text-[11px] text-gray-500 mb-1">
                    <b>Skill:</b> {detail.frontmatter.skill} · <b>Kategori:</b> {detail.frontmatter.kategori || '—'}
                  </div>
                  <div className="text-[11px] text-gray-500 mb-2">
                    <b>Kriteria baku:</b> {detail.frontmatter.kriteria_baku || '—'}
                  </div>
                  {detail.frontmatter.tags.length > 0 && (
                    <div className="text-[10px] text-gray-400 mb-2">
                      tags: {detail.frontmatter.tags.map(t => `#${t}`).join(' · ')}
                    </div>
                  )}
                </>
              )}
              <pre className="text-[11px] whitespace-pre-wrap font-sans text-gray-800 leading-relaxed">{detail.body}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// CacmKriteriaPanel — browser kriteria CACM v7-native (semua role baca).
// =============================================================================

type CacmKriteriaItem = {
  id: string;
  revisi: string;
  nama: string;
  tipe: string;
  dimensi: string;
  sumber_data: string;
  satker_terapkan: string[];
  regulasi: string[];
  metric: { expression: string; satuan: string | null; format_display: string | null };
  thresholds: Array<{ status: string; condition: string; catatan: string | null }>;
  evidence_fields: string[];
  promote: any;
  catatan_revisi: string | null;
};

const CACM_STATUS_COLOR: Record<string, string> = {
  MERAH: 'bg-red-100 text-red-800 border-red-300',
  KUNING: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  HIJAU: 'bg-green-100 text-green-800 border-green-300',
  INFO: 'bg-gray-100 text-gray-600 border-gray-300',
};

function CacmKriteriaPanel() {
  const [items, setItems] = useState<CacmKriteriaItem[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);
  const [dimensi, setDimensi] = useState('');
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<CacmKriteriaItem | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true); setErr(null);
    try {
      const r = await api.listCacmKriteria(dimensi || undefined);
      setItems(r.items);
      setDimensions(r.dimensi_available);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    const t = setTimeout(() => refresh(), 150);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [dimensi]);

  return (
    <div className="mb-6 bg-white border border-amber-200 rounded-lg p-5">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <h2 className="font-semibold text-primary-dark">Kriteria CACM (mesin evaluator v7-native)</h2>
        <span className="text-[11px] text-gray-500">
          {items.length} kriteria {dimensi ? `di ${dimensi}` : 'aktif'}
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-2">
        Definisi MERAH/KUNING/HIJAU yang dipakai mesin evaluator atas data SIRUP/DIPA/SPSE/Kinerja.
        Sumber: <code>knowledge/cacm/kriteria/&lt;id&gt;.yaml</code>. Revisi via Pull Request (Git audit trail).
      </p>

      <HowToUse
        color="amber"
        when="Mau memahami logika threshold yang dipakai sistem saat menilai sinyal CACM. Cek metric, regulasi, threshold per status, dan revisi YAML."
        steps={[
          'Pilih dimensi (PENGADAAN_RENCANA / ANGGARAN / dst) atau biarkan kosong untuk lihat semua.',
          'Klik kartu untuk preview lengkap: metric DSL expression, threshold per status, regulasi, evidence_fields.',
          'Bila threshold perlu direvisi (mis. setelah workshop kalibrasi): edit YAML di knowledge/cacm/kriteria/, buat PR. Re-evaluate run lama via tombol di /cacm.',
        ]}
        example="Klik PBJ-PDN-RASIO → metric: sum(pagu WHERE pdn=PDN) / sum(pagu) * 100; threshold MERAH <40, KUNING 40-60, HIJAU >=60. Regulasi: Inpres 2/2022 + Perpres 12/2021 Pasal 66."
      />

      <div className="mb-3">
        <select value={dimensi} onChange={(e) => setDimensi(e.target.value)} className="border border-gray-300 rounded px-2 py-1.5 text-xs">
          <option value="">Semua dimensi ({dimensions.length})</option>
          {dimensions.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {err && <div className="mb-2 p-2 rounded bg-red-50 border border-red-200 text-red-700 text-xs">{err}</div>}

      <div className="grid md:grid-cols-2 gap-3">
        <div className="border border-gray-200 rounded max-h-[480px] overflow-y-auto divide-y">
          {loading ? (
            <div className="p-3 text-xs text-gray-400 italic">Memuat kriteria…</div>
          ) : items.length === 0 ? (
            <div className="p-3 text-xs text-gray-400 italic">
              Belum ada kriteria. Cek folder <code>knowledge/cacm/kriteria/</code>.
            </div>
          ) : items.map((k) => (
            <button
              key={k.id}
              onClick={() => setSelected(k)}
              className={`w-full text-left p-2.5 hover:bg-amber-50/40 transition ${selected?.id === k.id ? 'bg-amber-50' : ''}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-[11px] text-gray-500 shrink-0">{k.id}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 shrink-0">{k.revisi}</span>
              </div>
              <div className="text-xs font-medium text-gray-800 mt-0.5">{k.nama}</div>
              <div className="text-[10px] text-gray-400 mt-0.5">
                <span className="uppercase">{k.dimensi}</span>
                <span> · {k.sumber_data}</span>
                <span> · {k.satker_terapkan.join(', ')}</span>
              </div>
            </button>
          ))}
        </div>

        <div className="border border-gray-200 rounded p-3 bg-gray-50 min-h-[300px] max-h-[480px] overflow-y-auto">
          {!selected ? (
            <p className="text-xs text-gray-400 italic">Klik salah satu kriteria di kiri untuk baca detail.</p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="font-mono text-[11px] text-gray-500">{selected.id}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{selected.tipe}</span>
              </div>
              <div className="text-sm font-semibold text-gray-800 mb-1">{selected.nama}</div>
              <div className="text-[11px] text-gray-500 mb-2">
                <b>Dimensi:</b> {selected.dimensi} · <b>Sumber:</b> {selected.sumber_data}
              </div>
              {selected.regulasi.length > 0 && (
                <div className="text-[11px] text-gray-600 mb-2">
                  <b>Regulasi:</b>
                  <ul className="list-disc list-inside ml-2">
                    {selected.regulasi.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
              <div className="text-[11px] text-gray-600 mb-2">
                <b>Metric:</b> {selected.metric.satuan && <span className="text-gray-500">({selected.metric.satuan})</span>}
                <pre className="text-[10px] bg-white border border-gray-200 rounded p-2 mt-1 whitespace-pre-wrap font-mono text-gray-800">{selected.metric.expression}</pre>
              </div>
              <div className="text-[11px] text-gray-600 mb-2">
                <b>Thresholds:</b>
                <table className="w-full text-[10px] mt-1 border border-gray-200 rounded overflow-hidden">
                  <thead>
                    <tr className="bg-gray-100">
                      <th className="px-1.5 py-1 text-left">Status</th>
                      <th className="px-1.5 py-1 text-left">Condition</th>
                      <th className="px-1.5 py-1 text-left">Catatan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.thresholds.map((t, i) => (
                      <tr key={i} className="border-t border-gray-200">
                        <td className="px-1.5 py-1">
                          <span className={`px-1 py-0.5 rounded border ${CACM_STATUS_COLOR[t.status] || 'bg-gray-100 text-gray-500 border-gray-300'}`}>{t.status}</span>
                        </td>
                        <td className="px-1.5 py-1 font-mono">{t.condition}</td>
                        <td className="px-1.5 py-1 text-gray-500">{t.catatan || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {selected.evidence_fields.length > 0 && (
                <div className="text-[11px] text-gray-500 mb-1">
                  <b>Evidence fields:</b> {selected.evidence_fields.join(', ')}
                </div>
              )}
              {selected.satker_terapkan.length > 0 && (
                <div className="text-[11px] text-gray-500">
                  <b>Berlaku utk satker:</b> {selected.satker_terapkan.join(', ')}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
