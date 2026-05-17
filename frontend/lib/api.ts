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
  login: (email: string, nip: string, role?: Role) =>
    request<Session>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, nip, role }),
    }),

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
};
