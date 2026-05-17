'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setToken, setSession, Role } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('auditor.at@komdigi.go.id');
  const [nip, setNip] = useState('198501012010011001');
  const [role, setRole] = useState<Role | ''>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const session = await api.login(email, nip, role || undefined);
      setToken(session.token);
      setSession(session);
      router.push('/penugasan');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <form
        onSubmit={handleLogin}
        className="w-full max-w-md bg-white rounded-xl shadow-md p-8 border border-gray-200"
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-lg bg-primary text-white font-bold text-lg flex items-center justify-center">
            v7
          </div>
          <div>
            <h1 className="text-xl font-bold text-primary-dark">Audit AI v7</h1>
            <p className="text-xs text-gray-500">Inspektorat II Komdigi</p>
          </div>
        </div>

        <label className="block mb-3">
          <span className="text-sm font-medium text-gray-700">Email Komdigi</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            required
          />
        </label>

        <label className="block mb-3">
          <span className="text-sm font-medium text-gray-700">NIP (18 digit)</span>
          <input
            type="text"
            value={nip}
            onChange={(e) => setNip(e.target.value)}
            pattern="\d{18}"
            maxLength={18}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            required
          />
        </label>

        <label className="block mb-5">
          <span className="text-sm font-medium text-gray-700">Peran (opsional)</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role | '')}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 text-sm bg-white"
          >
            <option value="">Default (sesuai akun)</option>
            <option value="AT">Anggota Tim</option>
            <option value="KT">Ketua Tim</option>
            <option value="PT">Pengendali Teknis</option>
            <option value="PM">Pengendali Mutu</option>
          </select>
        </label>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 rounded-md bg-primary text-white font-semibold hover:bg-primary-dark transition disabled:opacity-50"
        >
          {loading ? 'Memproses…' : 'Masuk'}
        </button>

        <p className="mt-4 text-xs text-gray-500 text-center">
          Akun uji: auditor.at@komdigi.go.id / auditor.kt@komdigi.go.id
        </p>
      </form>
    </main>
  );
}
