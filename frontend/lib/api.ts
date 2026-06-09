// API client untuk backend Audit AI v7.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('audit_v7_token');
}

export function setToken(token: string): void {
  localStorage.setItem('audit_v7_token', token);
}

export function clearToken(): void {
  localStorage.removeItem('audit_v7_token');
  localStorage.removeItem('audit_v7_session');
}

export function getSession(): Session | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem('audit_v7_session');
  return raw ? (JSON.parse(raw) as Session) : null;
}

export function setSession(session: Session): void {
  localStorage.setItem('audit_v7_session', JSON.stringify(session));
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (!(init.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

// ===== Types =====
export type Role = 'AT' | 'KT' | 'PT' | 'PM';
// Skill kini folder-driven di backend (registry) — bukan enum tetap. Tetap
// alias `string` supaya komponen lama yang mereferensikan `Skill` tidak rusak.
export type Skill = string;

export interface SkillInfo {
  slug: string;
  name: string;
  jenis: string;
  output: string;
  has_pipeline: boolean;
}

export interface GateItem {
  id: string;
  judul: string;
  status?: 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'NEEDS_REVISION';
  catatan?: string;
}
export interface GateStatus {
  gated: boolean;
  skill: string;
  gates: GateItem[];
  progress: {
    skill: string;
    total_gates: number;
    current_gate: string | null;
    gates: GateItem[];
    updated_at?: string;
  } | null;
}

export interface User {
  id: number;
  email: string;
  nama_lengkap: string;
  nip: string;
  role_default: Role;
}

export interface Session {
  user: User;
  role_aktif: Role;
  token: string;
}

export interface Penugasan {
  id: number;
  kode: string;
  obyek: string;
  skill: Skill;
  nomor_st: string | null;
  tanggal_st: string | null;
  status: string;
  folder_path: string;
  created_at: string;
  updated_at: string;
}

export interface Dokumen {
  id: number;
  penugasan_id: number;
  nama_file: string;
  jenis: string | null;
  sha256: string;
  size_bytes: number;
  status: 'UPLOADED' | 'INGESTING' | 'READY' | 'FAILED';
  ingested_json_path: string | null;
  error_message: string | null;
  uploaded_at: string;
  ingested_at: string | null;
}

// ===== API =====
export const api = {
  /** Prototype login: cukup pilih role. Backend auto-pick user seed pertama
   * dengan `role_default == role`. Email optional untuk override pilih user
   * tertentu (production nanti SSO). */
  login: (role: Role, email?: string) =>
    request<Session>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ role, email }),
    }),

  /** Daftar user seed (opsional filter role). Dipakai layar login untuk
   * memilih orang saat satu role punya >1 user (mis. beberapa Anggota Tim),
   * dan oleh KT untuk dropdown assignment sasaran. Publik (prototype). */
  listUsers: (role?: Role) =>
    request<User[]>(`/auth/users${role ? `?role=${role}` : ''}`),

  /** Daftar skill pengawasan terdaftar (folder-driven) untuk dropdown. */
  getSkills: () => request<SkillInfo[]>('/skills'),

  /** Status evaluasi bertahap (gate-based). gated=false untuk skill non-bertahap. */
  getGates: (penugasanId: number) =>
    request<GateStatus>(`/penugasan/${penugasanId}/gates`),

  // ===== Graduasi (meta-skill) =====
  getGraduasiCandidates: () =>
    request<{ groups: { skill: string; penugasan: { kode: string; obyek: string; n_temuan: number }[] }[] }>(
      '/graduasi/candidates'
    ),
  getGraduasiDrafts: () =>
    request<{ drafts: { nama: string; fungsi?: string; skill_induk?: string; n_temuan?: number; generated_at?: string }[] }>(
      '/graduasi/drafts'
    ),
  runGraduasi: (penugasanKodes: string[], nama?: string) =>
    request<{ ok: boolean; nama: string; n_temuan: number; n_redflag: number; sumber_penugasan: string[] }>(
      '/graduasi/run',
      { method: 'POST', body: JSON.stringify({ penugasan_kodes: penugasanKodes, nama }) }
    ),
  promoteGraduasi: (nama: string) =>
    request<{ ok: boolean; nama: string; skill_terdaftar: boolean }>('/graduasi/promote', {
      method: 'POST',
      body: JSON.stringify({ nama }),
    }),
  rejectGraduasi: (nama: string) =>
    request<{ ok: boolean; nama: string }>('/graduasi/reject', {
      method: 'POST',
      body: JSON.stringify({ nama }),
    }),

  /** Keputusan auditor atas satu gate: LANJUT / KOREKSI / ULANG. */
  recordGateDecision: (
    penugasanId: number,
    gateId: string,
    decision: 'LANJUT' | 'KOREKSI' | 'ULANG',
    catatan?: string
  ) =>
    request<{ ok: boolean; progress: GateStatus['progress'] }>(
      `/penugasan/${penugasanId}/gates/${gateId}/decision`,
      { method: 'POST', body: JSON.stringify({ decision, catatan }) }
    ),

  listPenugasan: () => request<Penugasan[]>('/penugasan'),

  getPenugasan: (id: number) => request<Penugasan>(`/penugasan/${id}`),

  /** Hapus penugasan + seluruh file di disk (hard delete). Hanya PT. */
  deletePenugasan: (id: number) =>
    request<{ ok: boolean; deleted: string; folder_removed: string }>(
      `/penugasan/${id}`,
      { method: 'DELETE' }
    ),

  createPenugasan: (payload: {
    obyek: string;
    skill: Skill;
    nomor_st?: string;
    tanggal_st?: string;
  }) =>
    request<Penugasan>('/penugasan', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listDokumen: (penugasanId: number) =>
    request<Dokumen[]>(`/dokumen?penugasan_id=${penugasanId}`),

  uploadDokumen: async (penugasanId: number, file: File, jenis?: string) => {
    const fd = new FormData();
    fd.append('penugasan_id', String(penugasanId));
    fd.append('file', file);
    if (jenis) fd.append('jenis', jenis);
    return request<Dokumen>('/dokumen', { method: 'POST', body: fd });
  },

  /** Hapus 1 dokumen (file + hasil ingest) lalu reset analisis turunan. Hanya AT. */
  deleteDokumen: (dokumenId: number) =>
    request<{ ok: boolean; deleted: string; reset_downstream: string[] }>(
      `/dokumen/${dokumenId}`,
      { method: 'DELETE' }
    ),

  triggerIngestion: (penugasanId: number) =>
    request<{ penugasan_id: number; reset_downstream: string[]; dokumen_diproses: any[] }>(
      `/agen/ingest/${penugasanId}`,
      { method: 'POST' }
    ),

  /** URL untuk EventSource SSE — bukan fetch(). */
  agentStreamUrl: (
    agent: 'ingestion' | 'anggota_tim' | 'ketua_tim' | 'qc_saipi',
    penugasanId: number,
    prompt: string
  ) => {
    const token = getToken() || '';
    const qs = new URLSearchParams({
      penugasan_id: String(penugasanId),
      prompt,
    });
    // Token via query param (EventSource tidak mendukung custom headers di browser
    // standar). Untuk produksi, gunakan cookie session.
    return `${API_BASE}/agen/${agent}/stream?${qs.toString()}&_token=${encodeURIComponent(token)}`;
  },

  /** URL EventSource untuk RECONNECT ke run aktif (replay buffer + tail).
   * Bila tak ada run aktif, server kirim event `idle` lalu tutup. */
  agentAttachUrl: (
    agent: 'ingestion' | 'anggota_tim' | 'ketua_tim' | 'qc_saipi',
    penugasanId: number
  ) => {
    const token = getToken() || '';
    const qs = new URLSearchParams({ penugasan_id: String(penugasanId) });
    return `${API_BASE}/agen/${agent}/attach?${qs.toString()}&_token=${encodeURIComponent(token)}`;
  },

  /** Cek cepat (non-stream) apakah ada run agen aktif di backend. */
  getActiveRun: (
    agent: 'ingestion' | 'anggota_tim' | 'ketua_tim' | 'qc_saipi',
    penugasanId: number
  ) =>
    request<{ active: boolean; run_id?: number; text_so_far?: string }>(
      `/agen/${agent}/active?penugasan_id=${penugasanId}`
    ),
  /** History semua run agen pada penugasan ini, urutan oldest → newest.
   * Dipakai untuk persist percakapan lampau saat user login ulang. */
  getAgentHistory: (
    agent: 'ingestion' | 'anggota_tim' | 'ketua_tim' | 'qc_saipi',
    penugasanId: number
  ) =>
    request<{
      agent_name: string;
      penugasan_id: number;
      total: number;
      runs: Array<{
        id: number;
        status: string;
        input_summary: string;
        output_summary: string;
        tool_calls: Array<{ tool: string; input: any }>;
        tokens_in: number;
        tokens_out: number;
        started_at: string | null;
        ended_at: string | null;
        error_message: string | null;
      }>;
    }>(`/agen/${agent}/history?penugasan_id=${penugasanId}`),

  // ===== File output access =====

  listFiles: (penugasanId: number) =>
    request<{
      penugasan_id: number;
      folder_path: string;
      categories: Array<{
        key: string;
        label: string;
        files: Array<{
          name: string;
          path: string;
          size_bytes: number;
          mtime: string;
          ext: string;
        }>;
      }>;
    }>(`/penugasan/${penugasanId}/files`),

  /** Download file sebagai Blob — pakai untuk Save As / open. */
  downloadFile: async (penugasanId: number, path: string): Promise<Blob> => {
    const token = getToken() || '';
    const url = `${API_BASE}/penugasan/${penugasanId}/files/download?path=${encodeURIComponent(path)}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.blob();
  },

  /** Preview text-based file (.md, .json, .txt). Return content string. */
  previewFile: (penugasanId: number, path: string, maxBytes = 50_000) =>
    request<{
      path: string;
      size_bytes: number;
      ext: string;
      truncated: boolean;
      content: string;
    }>(`/penugasan/${penugasanId}/files/preview?path=${encodeURIComponent(path)}&max_bytes=${maxBytes}`),

  // ===== Setup Penugasan (Ketua Tim only — endpoint return 403 untuk AT) =====

  getSasaranAssignment: (penugasanId: number) =>
    request<{
      penugasan_id: string;
      skill: string;
      schema_version: string;
      sasaran: Array<{
        sasaran_id: string;
        deskripsi: string;
        assigned_to: string[];
        langkah_kerja: string[];
        status: string;
      }>;
    }>(`/penugasan/${penugasanId}/sasaran-assignment`),

  saveSasaranAssignment: (
    penugasanId: number,
    sasaran: Array<{
      sasaran_id: string;
      deskripsi: string;
      assigned_to: string[];
      langkah_kerja: string[];
      status: string;
    }>
  ) =>
    request<{ ok: boolean; total_sasaran: number; path: string }>(
      `/penugasan/${penugasanId}/sasaran-assignment`,
      { method: 'PUT', body: JSON.stringify({ sasaran }) }
    ),

  // ===== Preload Context Bundle (Prioritas 1 — peningkatan kualitas output agen) =====
  /** Bangun bundle konteks pra-loaded (vault + pattern + glossary + riwayat W3) */
  buildPreloadContext: (penugasanId: number) =>
    request<{
      ok: boolean;
      path: string;
      stats: {
        char_count: number;
        n_vault_notes: number;
        n_patterns: number;
        n_konteks: number;
        n_writeback_history: number;
        vault_keywords: string[];
      };
    }>(`/penugasan/${penugasanId}/preload-context`, { method: 'POST' }),

  /** Cek status bundle (apakah sudah dibangun + statistik). */
  getPreloadContextStatus: (penugasanId: number) =>
    request<{
      exists: boolean;
      size_bytes?: number;
      modified_at?: string;
      char_count?: number;
      preview_head?: string;
    }>(`/penugasan/${penugasanId}/preload-context/status`),

  // ===== Per-Temuan Review (Prioritas 2 — HITL per-temuan) =====
  /** List semua temuan + status review-nya. */
  listTemuanReview: (penugasanId: number) =>
    request<{
      total: number;
      counts: Record<string, number>;
      items: Array<{
        id_temuan: string;
        judul: string;
        sasaran_id: string;
        kondisi: string;
        kriteria: string;
        akibat: string;
        anggota: string;
        dokumen_sumber_count: number;
        status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EDITED';
        note: string | null;
        reviewed_at: string | null;
        reviewed_by_user_id: number | null;
        has_edits?: boolean;
        edited_fields?: {
          judul_temuan?: string;
          kondisi?: string;
          kriteria?: string;
          akibat?: string;
        } | null;
      }>;
    }>(`/penugasan/${penugasanId}/temuan-review`),

  /** Setujui 1 temuan (AT/KT/PT/PM). */
  approveTemuan: (penugasanId: number, temuanId: string, note?: string) =>
    request<{ ok: boolean; id_temuan: string; status: string; reviewed_at: string | null }>(
      `/penugasan/${penugasanId}/temuan-review/${encodeURIComponent(temuanId)}/approve`,
      { method: 'POST', body: JSON.stringify({ note: note ?? null }) }
    ),

  /** Tolak 1 temuan (KT/PT/PM). */
  rejectTemuan: (penugasanId: number, temuanId: string, note?: string) =>
    request<{ ok: boolean; id_temuan: string; status: string; reviewed_at: string | null }>(
      `/penugasan/${penugasanId}/temuan-review/${encodeURIComponent(temuanId)}/reject`,
      { method: 'POST', body: JSON.stringify({ note: note ?? null }) }
    ),

  /** Bulk approve semua temuan PENDING (KT/PT/PM). */
  bulkApproveTemuan: (penugasanId: number) =>
    request<{ ok: boolean; approved_count: number; total_temuan: number }>(
      `/penugasan/${penugasanId}/temuan-review/bulk-approve`,
      { method: 'POST' }
    ),

  /** Edit field temuan via overlay (KT/PT/PM). String "" eksplisit → hapus
   * overlay key (revert ke versi agen). Field undefined → tidak ubah. */
  editTemuan: (
    penugasanId: number,
    temuanId: string,
    edits: {
      judul_temuan?: string;
      kondisi?: string;
      kriteria?: string;
      akibat?: string;
      note?: string;
    }
  ) =>
    request<{
      ok: boolean;
      id_temuan: string;
      status: string;
      edited_fields: Record<string, string> | null;
      has_edits: boolean;
      reviewed_at: string | null;
    }>(
      `/penugasan/${penugasanId}/temuan-review/${encodeURIComponent(temuanId)}/edit`,
      { method: 'PUT', body: JSON.stringify(edits) }
    ),

  /** W1.1 — sync sasaran dari payload PKP SIMWAS (manual paste/upload hari ini;
   * source='api' placeholder 501 sampai kontrak API + SSO SIMWAS resmi). PT/KT. */
  syncSasaranFromSimwas: (
    penugasanId: number,
    payload: {
      source?: 'manual' | 'api';
      strategy?: 'replace' | 'append';
      pkp_rows: Array<{
        sasaran: string;
        langkah_kerja?: string;
        dilaksanakan_oleh?: string;
        waktu?: string;
        no_kkp?: string;
        sasaran_id?: string;
      }>;
    }
  ) =>
    request<{
      ok: boolean;
      source: string;
      strategy: string;
      total_input_rows: number;
      total_sasaran: number;
      added_sasaran: string[];
      added_count: number;
      skipped_duplicate: number;
    }>(`/penugasan/${penugasanId}/sasaran/sync-from-simwas`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getContextMd: (penugasanId: number) =>
    request<{ content: string; exists: boolean }>(
      `/penugasan/${penugasanId}/context-md`
    ),

  /** Prasyarat Generate Context: sasaran (KT) + dokumen ter-digest (AT). */
  getContextReadiness: (penugasanId: number) =>
    request<{ ready: boolean; has_sasaran: boolean; has_ingested: boolean; reason: string }>(
      `/penugasan/${penugasanId}/context-readiness`
    ),

  saveContextMd: (penugasanId: number, content: string) =>
    request<{ ok: boolean; size_bytes: number; path: string }>(
      `/penugasan/${penugasanId}/context-md`,
      { method: 'PUT', body: JSON.stringify({ content }) }
    ),

  // ===== Knowledge / Wiki vault (W1 — baca vault pengetahuan) =====

  /** Cari catatan di vault pengetahuan organisasi (read-only). */
  searchWiki: (q: string, limit = 12) =>
    request<{
      configured: boolean;
      total: number;
      message?: string;
      results: Array<{
        name: string;
        section: string;
        summary: string;
        path: string;
        score: number;
        snippet: string;
      }>;
    }>(`/knowledge/wiki/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  /** Baca isi lengkap satu catatan vault by name. */
  getWikiPage: (name: string) =>
    request<{
      found: boolean;
      configured: boolean;
      message?: string;
      name?: string;
      path?: string;
      content?: string;
      truncated?: boolean;
    }>(`/knowledge/wiki/page?name=${encodeURIComponent(name)}`),

  // ===== Pattern Library Browser (W4) =====
  // Jelajah 65+ pattern temuan terkurasi di knowledge/wiki/temuan-patterns/<skill>/.
  // Semua role boleh baca (read-only). Lihat backend/app/knowledge_browse.py.

  /** List pattern terkurasi. Filter opsional: skill, severity, search. */
  listPatternLibrary: (params: { skill?: string; severity?: string; search?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.skill) qs.set('skill', params.skill);
    if (params.severity) qs.set('severity', params.severity);
    if (params.search) qs.set('search', params.search);
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return request<{
      skills_available: string[];
      severities_available: string[];
      categories_available: string[];
      total_all: number;
      total_filtered: number;
      items: Array<{
        id: string;
        skill: string;
        kategori: string;
        severity: string;
        judul: string;
        kriteria_baku: string;
        tags: string[];
        file: string;
      }>;
    }>(`/knowledge/patterns/library${tail}`);
  },

  /** Baca isi lengkap satu pattern (frontmatter + body markdown). */
  getPattern: (patternId: string) =>
    request<{
      id: string;
      skill: string;
      kategori: string;
      severity: string;
      judul: string;
      kriteria_baku: string;
      tags: string[];
      file: string;
      body_md: string;
    }>(`/knowledge/patterns/library/${encodeURIComponent(patternId)}`),

  // ===== Sasaran Template Suggestions =====
  // 3-sumber paralel untuk membantu KT setup penugasan tanpa start-from-zero.

  /** Saran template setup dari penugasan historis / skeleton pattern / catatan W3 vault. */
  getSasaranTemplates: (penugasanId: number, source: 'all' | 'historis' | 'patterns' | 'writeback' = 'all') =>
    request<{
      skill: string;
      obyek: string;
      historis?: Array<{
        kode: string;
        obyek: string;
        skill: string;
        status: string;
        similarity: number;
        total_sasaran: number;
        sasaran: Array<{
          sasaran_id: string;
          deskripsi: string;
          assigned_to: string[];
          langkah_kerja: string[];
        }>;
      }>;
      patterns?: {
        skill: string;
        total_patterns: number;
        sasaran: Array<{
          sasaran_id: string;
          deskripsi: string;
          langkah_kerja: string[];
          assigned_to: string[];
          kategori: string;
          pattern_ids: string[];
        }>;
      };
      writeback?: Array<{
        nama_file: string;
        judul: string;
        skill_label: string;
        obyek: string;
        jumlah_temuan: number;
        similarity: number;
      }>;
    }>(`/penugasan/${penugasanId}/sasaran/templates?source=${source}`),

  // ===== Promosi Pattern (W2) =====

  /** Agregasi usulan pattern dari feedback agen lintas penugasan (kandidat promosi). */
  getPatternMonitor: (days = 90) =>
    request<{
      days: number;
      total_feedback: number;
      total_suggestions: number;
      candidates: Array<{
        judul: string;
        id_proposed: string;
        count: number;
        rationales: string[];
        skills: Record<string, number>;
        suggested_skill: string;
        penugasan: Array<{ folder: string; obyek: string; skill: string }>;
        already_exists: boolean;
        existing_id: string | null;
      }>;
      missed_pattern_issues: Array<{
        description: string;
        suggested_action: string;
        severity: string;
        penugasan_folder: string;
        skill: string;
      }>;
    }>(`/knowledge/pattern-monitor?days=${days}`),

  /** Promote satu usulan jadi pattern wiki resmi (tulis file .md). PT/PM only. */
  promotePattern: (payload: {
    skill: string;
    pattern_id: string;
    judul: string;
    kategori?: string;
    severity?: string;
    kriteria_baku?: string;
    kondisi?: string;
    akibat?: string;
    rekomendasi?: string;
    bukti?: string;
    tags?: string[];
    sumber_penugasan?: string[];
  }) =>
    request<{
      ok: boolean;
      id: string;
      skill: string;
      kategori: string;
      severity: string;
      file: string;
      readme_updated: boolean;
    }>('/knowledge/patterns', { method: 'POST', body: JSON.stringify(payload) }),

  // ===== Tulis-balik Vault (W3) =====
  // Penugasan LHP_DONE → draft pengawasan-<kode>.md (Karpathy format) + delta
  // index/log. Auditor preview → Download .md (opsi A, Obsidian flow) atau Apply
  // ke vault (opsi B). Lihat backend/app/wiki_writeback.py.

  /** Daftar penugasan LHP_DONE + status proposal. Role-agnostik. */
  getWritebackCandidates: () =>
    request<{
      total: number;
      items: Array<{
        penugasan_id: number;
        kode: string;
        obyek: string;
        skill: string;
        lhp_done_at: string | null;
        proposal_status: 'NONE' | 'DRAFT' | 'APPLIED' | 'REJECTED';
        nama_file: string | null;
      }>;
    }>('/knowledge/writeback/candidates'),

  /** Generate (atau regenerate) draft proposal. PT/PM/KT only. */
  generateWritebackProposal: (penugasanId: number) =>
    request<{
      id: number;
      penugasan_id: number;
      nama_file: string;
      ringkasan: string | null;
      status: string;
      konten_md: string;
      delta_index: string | null;
      delta_log: string | null;
    }>(`/knowledge/writeback/${penugasanId}/generate`, { method: 'POST' }),

  /** Ambil proposal terkini (lengkap dengan konten). */
  getWritebackProposal: (penugasanId: number) =>
    request<{
      id: number;
      penugasan_id: number;
      nama_file: string;
      ringkasan: string | null;
      status: string;
      konten_md: string;
      delta_index: string | null;
      delta_log: string | null;
      dibuat_at: string | null;
      diupdate_at: string | null;
      applied_at: string | null;
    }>(`/knowledge/writeback/${penugasanId}/proposal`),

  /** URL unduh .md (mencegah CORS issue dgn fetch — pakai window.open). */
  getWritebackDownloadUrl: (penugasanId: number) => {
    const token = getToken() || '';
    return `${API_BASE}/knowledge/writeback/${penugasanId}/download?_token=${encodeURIComponent(token)}`;
  },

  /** Apply proposal ke vault. PT/PM only. */
  applyWritebackProposal: (penugasanId: number) =>
    request<{
      status: string;
      apply_result: {
        ok: boolean;
        path: string;
        index: { changed: boolean; reason: string };
        log: { changed: boolean; reason: string };
      };
    }>(`/knowledge/writeback/${penugasanId}/apply`, { method: 'POST' }),

  /** Tolak proposal (REJECTED). PT/PM only. */
  rejectWritebackProposal: (penugasanId: number) =>
    request<{ status: string }>(`/knowledge/writeback/${penugasanId}/reject`, { method: 'POST' }),

  // ===== CACM / EWS SIRUP (C1a — ingest offline + usulan penugasan) =====

  /** Ingest fixture contoh hasil EWS (demo tanpa deploy agent). PT only. */
  ingestCacmSample: () =>
    request<{ ok: boolean; id: number; run_id: string; summary: Record<string, number> }>(
      '/cacm/ingest-sample',
      { method: 'POST' }
    ),

  /** Daftar run EWS yang sudah masuk. */
  getCacmRuns: () =>
    request<{
      total: number;
      runs: Array<{
        id: number;
        run_id: string;
        source: string;
        tanggal_evaluasi: string | null;
        summary: Record<string, number>;
        total_findings: number;
        received_at: string | null;
      }>;
    }>('/cacm/runs'),

  /** Detail 1 run: rekap + findings. */
  getCacmRun: (id: number) =>
    request<{
      id: number;
      run_id: string;
      source: string;
      tanggal_evaluasi: string | null;
      summary: Record<string, number>;
      rekap: Array<Record<string, any>>;
      findings: Array<{
        id: number;
        kode: string;
        satker: string;
        satker_kode: string | null;
        status: string;
        judul: string | null;
        penjelasan: string | null;
        ringkasan: string | null;
        nilai_aktual: string | null;
        jumlah_paket_terdampak: number;
        total_nilai_terdampak: number;
        threshold: string | null;
        regulasi: string | null;
        rekomendasi: string | null;
        paket_detail: Array<Record<string, any>>;
        tindak_lanjut: string;
        penugasan_id: number | null;
        promotable: boolean;
      }>;
    }>(`/cacm/runs/${id}`),

  /** Jadikan finding usulan penugasan (status USULAN_CACM). PT only. */
  promoteFinding: (findingId: number) =>
    request<{ ok: boolean; penugasan_id: number; kode: string; obyek: string }>(
      `/cacm/findings/${findingId}/promote`,
      { method: 'POST' }
    ),

  /** Abaikan finding. PT only. */
  dismissFinding: (findingId: number) =>
    request<{ ok: boolean; finding_id: number; tindak_lanjut: string }>(
      `/cacm/findings/${findingId}/dismiss`,
      { method: 'POST' }
    ),

  /** Terima usulan CACM → penugasan jadi DRAFT (masuk alur normal). PT only. */
  acceptUsulan: (penugasanId: number) =>
    request<{ ok: boolean; penugasan_id: number; status: string }>(
      `/cacm/usulan/${penugasanId}/accept`,
      { method: 'POST' }
    ),

  /** Pull run terbaru dari agent EWS tim via REST (C1b). PT only. */
  syncCacm: () =>
    request<{ ok: boolean; id: number; run_id: string; summary: Record<string, number> }>(
      '/cacm/sync',
      { method: 'POST' }
    ),

  /** Minta agent EWS jalankan run baru (C1b). PT only. */
  triggerCacm: () =>
    request<{ ok: boolean; agent_response: any }>('/cacm/trigger', { method: 'POST' }),

  /** Jumlah usulan CACM yang menunggu review (status USULAN_CACM) — untuk badge. */
  getCacmPending: () =>
    request<{ count: number; items: Array<{ id: number; kode: string; obyek: string }> }>(
      '/cacm/usulan/pending'
    ),

  // ===== CACM Mesin Kriteria (Fase 1 — backend core wire-up commit-2) =====

  /** List kriteria CACM v7-native dari knowledge/cacm/kriteria/*.yaml. Semua role. */
  listCacmKriteria: (dimensi?: string) => {
    const qs = dimensi ? `?dimensi=${encodeURIComponent(dimensi)}` : '';
    return request<{
      total: number;
      dimensi_available: string[];
      items: Array<{
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
        promote: { skill: string; pattern_ids_hint: string[]; prefilled_obyek_tpl: string | null; prefilled_dasar_permintaan: string | null } | null;
        catatan_revisi: string | null;
      }>;
    }>(`/cacm/kriteria/library${qs}`);
  },

  /** Detail 1 kriteria CACM. */
  getCacmKriteria: (id: string) =>
    request<{
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
    }>(`/cacm/kriteria/${encodeURIComponent(id)}`),

  /** List CacmFinding v7-native utk satu run (paralel dgn EwsFinding legacy). */
  getCacmV7Findings: (runId: number) =>
    request<{
      total: number;
      findings: Array<{
        id: number;
        kriteria_id: string;
        kriteria_revisi: string;
        status: string;
        metric_value: number | null;
        metric_display: string | null;
        metric_satuan: string | null;
        satker_kode: string | null;
        satker_nama: string;
        periode_label: string;
        dimensi: string;
        narasi: string;
        evidence: Record<string, any>;
        bukti_observasi_ids: number[];
        tindak_lanjut: string;
        penugasan_id: number | null;
        evaluated_at: string | null;
      }>;
    }>(`/cacm/runs/${runId}/findings/v7-native`),

  /** Re-evaluate v7-native untuk satu run — PT/PM. Dipakai setelah revisi YAML. */
  reEvaluateCacmRun: (runId: number) =>
    request<{
      ok: boolean;
      run_id: number;
      removed_observasi: number;
      removed_findings_old: number;
      new_findings: number;
      note?: string;
    }>(`/cacm/runs/${runId}/re-evaluate`, { method: 'POST' }),

  /** Diff CacmFinding v7-native vs EwsFinding legacy untuk satu run.
   * Pair per (satker_nama, kode EWS / kriteria_id v7) via mapping di
   * `app/cacm_mapping.py`. Dipakai untuk validasi cut-over sebelum
   * auto-promote v7-native dinyalakan. */
  getCacmDiff: (runId: number) =>
    request<{
      run_id: number;
      summary: {
        n_ews_total: number;
        n_v7_total: number;
        n_matched_pairs: number;
        n_match_status: number;
        n_mismatch: number;
        n_v7_only: number;
        n_ews_only: number;
      };
      matched: Array<{
        satker_nama: string;
        satker_kode: string | null;
        ews_kode: string;
        v7_kriteria_id: string;
        ews_status: string;
        v7_status: string;
        is_match: boolean;
        ews_finding_id: number;
        v7_finding_id: number;
        ews_nilai: string | null;
        v7_metric_display: string | null;
        ews_judul: string | null;
        v7_narasi: string;
      }>;
      v7_only: Array<{
        satker_nama: string;
        satker_kode: string | null;
        v7_kriteria_id: string;
        v7_status: string;
        v7_finding_id: number;
        v7_metric_display: string | null;
        v7_narasi: string;
        reason: string;
      }>;
      ews_only: Array<{
        satker_nama: string;
        satker_kode: string | null;
        ews_kode: string;
        expected_v7_kriteria_id: string | null;
        ews_status: string;
        ews_finding_id: number;
        ews_nilai: string | null;
        ews_judul: string | null;
        reason: string;
      }>;
    }>(`/cacm/runs/${runId}/findings/diff`),

  /** Promote CacmFinding v7-native ke Penugasan USULAN_CACM (PT only).
   * Paralel dengan promote EwsFinding existing. */
  promoteCacmFinding: (findingId: number) =>
    request<{
      ok: boolean;
      penugasan_id: number;
      penugasan_kode: string;
      status: string;
    }>(`/cacm/cacm-findings/${findingId}/promote`, { method: 'POST' }),

  // ===== Feedback Aggregate Dashboard (Phase 2) =====

  /** Ringkasan agregat feedback agen cross-penugasan untuk N hari ke belakang. */
  getFeedbackAggregate: (days = 30) =>
    request<{
      days: number;
      total_feedback: number;
      by_agent: Record<string, number>;
      by_confidence: Record<string, number>;
      top_workflow_issues: Array<{
        category: string;
        severity: string;
        count: number;
        examples: string[];
      }>;
      top_substansi_issues: Array<{
        category: string;
        severity: string;
        count: number;
        examples: string[];
      }>;
      top_pattern_suggestions: Array<{
        id_proposed: string;
        judul: string;
        count: number;
        rationales: string[];
      }>;
      severity_heatmap: Record<string, Record<string, number>>;
      recent_files: Array<{
        path: string;
        full_path: string;
        agent: string;
        confidence: string;
        summary: string;
        penugasan_folder: string;
        timestamp: string | null;
        workflow_count: number;
        substansi_count: number;
        pattern_count: number;
      }>;
    }>(`/feedback/aggregate?days=${days}`),

  /** List file feedback mentah untuk drill-down. */
  listFeedback: (days = 30) =>
    request<{
      days: number;
      total: number;
      items: Array<{
        file: string;
        agent: string;
        confidence: string;
        summary: string;
        workflow_count: number;
        substansi_count: number;
        pattern_count: number;
        timestamp: string | null;
        penugasan_id: number | null;
        penugasan_obyek: string;
        penugasan_folder: string;
      }>;
    }>(`/feedback/list?days=${days}`),

  // ===== Templates KP & PKP (INTEGRAL workflow tahapan 1+2) =====

  /** List template KP/PKP dari wiki, filter by skill (optional).
   * Mengembalikan template `default` sebagai fallback jika skill tidak match. */
  listTemplates: (kind: 'kp' | 'pkp', skill?: string) => {
    const qs = skill ? `?skill=${encodeURIComponent(skill)}` : '';
    return request<{
      count: number;
      items: Array<{
        slug: string;
        judul: string;
        skill: string;
        jenis: string;
        field_required: string[];
        field_optional: string[];
        versi?: string;
      }>;
    }>(`/knowledge/templates/${kind}${qs}`);
  },

  /** Ambil isi lengkap 1 template KP/PKP (frontmatter + body markdown). */
  getTemplate: (kind: 'kp' | 'pkp', slug: string) =>
    request<{
      slug: string;
      kind: string;
      meta: Record<string, any>;
      body: string;
      raw: string;
    }>(`/knowledge/templates/${kind}/${encodeURIComponent(slug)}`),
};
