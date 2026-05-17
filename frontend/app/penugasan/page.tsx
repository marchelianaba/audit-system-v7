'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, getSession, clearToken, Penugasan, Skill } from '@/lib/api';

export default function DashboardPage() {
  const router = useRouter();
  const [penugasan, setPenugasan] = useState<Penugasan[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [obyek, setObyek] = useState('');
  const [skill, setSkill] = useState<Skill>('reviu-rka-kl');
  const [nomorSt, setNomorSt] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const session = getSession();

  useEffect(() => {
    if (!session) {
      router.push('/login');
      return;
    }
    api
      .listPenugasan()
      .then(setPenugasan)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [router]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
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

  if (!session) return null;

  return (
    <main className="min-h-screen">
      <header className="bg-primary text-white px-6 py-3 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-white text-primary font-bold flex items-center justify-center text-sm">
            v7
          </div>
          <div>
            <div className="font-semibold text-sm">Audit AI v7</div>
            <div className="text-xs opacity-80">Inspektorat II Komdigi</div>
          </div>
        </div>
        <div className="text-right text-xs">
          <div>{session.user.nama_lengkap}</div>
          <div className="opacity-80">
            <span className="px-2 py-0.5 rounded bg-white/15 ml-2">{session.role_aktif}</span>
            <button onClick={handleLogout} className="ml-3 underline">
              Keluar
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6">
        <div className="flex justify-between items-center mb-5">
          <h1 className="text-2xl font-bold text-primary-dark">Penugasan Saya</h1>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 rounded bg-primary text-white text-sm font-semibold hover:bg-primary-dark"
          >
            {showForm ? '× Batal' : '+ Penugasan Baru'}
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        {showForm && (
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
                <option value="reviu-rka-kl">Reviu RKA-K/L</option>
                <option value="reviu-pengadaan">Reviu Pengadaan</option>
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
            Belum ada penugasan. Klik <strong>+ Penugasan Baru</strong>.
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
                      <span className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-700">
                        {p.status}
                      </span>
                    </td>
                    <td className="p-3">
                      <Link
                        href={`/penugasan/${p.id}`}
                        className="text-primary hover:underline"
                      >
                        Buka →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
