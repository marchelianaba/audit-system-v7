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

  triggerIngestion: (penugasanId: number) =>
    request<{ penugasan_id: number; dokumen_diproses: any[] }>(
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
