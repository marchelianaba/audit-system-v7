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
export type Skill = 'reviu-rka-kl' | 'reviu-pengadaan';

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
runAgent: (
    agent: 'ingestion' | 'anggota_tim' | 'ketua_tim' | 'qc_saipi',
    penugasanId: number,
    prompt: string
  ) =>
    request<{
      run_id: number;
      status: string;
      output: string;
      tool_calls: Array<{ tool: string; input: any }>;
      error: string | null;
    }>(`/agen/${agent}/run`, {
      method: 'POST',
      body: JSON.stringify({ penugasan_id: penugasanId, prompt }),
    }),

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

  getContextMd: (penugasanId: number) =>
    request<{ content: string; exists: boolean }>(
      `/penugasan/${penugasanId}/context-md`
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
};
