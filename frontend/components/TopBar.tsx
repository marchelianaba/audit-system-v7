'use client';

/**
 * TopBar — INTEGRAL AI Workspace
 *
 * Mirror style SIMWAS v2:
 * - Judul: "Sistem Informasi Manajemen Pengawasan" + "Kementerian Komunikasi Dan Digital RI"
 * - Right: theme toggle (placeholder), notification bell (badge merah), avatar online indicator
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { getSession, clearToken, Session } from '@/lib/api';

const ROLE_LABEL: Record<string, string> = {
  AT: 'Anggota Tim',
  KT: 'Ketua Tim',
  PT: 'Pengendali Teknis',
  PM: 'Pengendali Mutu',
};

const ROLE_COLOR: Record<string, string> = {
  AT: 'bg-at',
  KT: 'bg-kt',
  PT: 'bg-pt',
  PM: 'bg-pm',
};

export function TopBar() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setSession(getSession());
  }, []);

  const onLogout = () => {
    clearToken();
    router.push('/login');
  };

  return (
    <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-6 sticky top-0 z-20">
      <div>
        <h1 className="text-sm font-bold text-ink">Sistem Informasi Manajemen Pengawasan</h1>
        <p className="text-xs text-gray-500 -mt-0.5">Kementerian Komunikasi Dan Digital RI</p>
      </div>

      <div className="flex items-center gap-3">
        {/* Theme toggle placeholder */}
        <button
          className="w-9 h-9 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-500"
          title="Theme (light)"
        >
          ☀
        </button>

        {/* Notification bell — placeholder dgn badge */}
        <button
          className="w-9 h-9 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-500 relative"
          title="Notifikasi"
        >
          🔔
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>

        {/* Avatar + role */}
        <div className="relative">
          <button
            onClick={() => setShowMenu((s) => !s)}
            className="flex items-center gap-2 hover:bg-gray-50 rounded-lg p-1 pr-3"
          >
            <div className="relative">
              <div className={`w-9 h-9 rounded-full ${session ? ROLE_COLOR[session.role_aktif] || 'bg-gray-400' : 'bg-gray-400'} flex items-center justify-center text-white font-semibold text-sm`}>
                {mounted && session ? session.user.nama_lengkap.charAt(0).toUpperCase() : '?'}
              </div>
              {/* Online indicator */}
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 rounded-full border-2 border-white"></span>
            </div>
            {mounted && session && (
              <div className="text-left leading-tight">
                <div className="text-xs font-semibold text-ink">{session.user.nama_lengkap}</div>
                <div className="text-[10px] text-gray-500">{ROLE_LABEL[session.role_aktif] || session.role_aktif}</div>
              </div>
            )}
          </button>

          {/* Dropdown */}
          {showMenu && mounted && session && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-card overflow-hidden">
              <div className="p-3 border-b border-gray-100">
                <div className="text-sm font-medium text-ink">{session.user.nama_lengkap}</div>
                <div className="text-xs text-gray-500">{session.user.email}</div>
                <div className="mt-1 inline-block px-2 py-0.5 rounded-full bg-primary-50 text-primary text-[10px] font-semibold">
                  {ROLE_LABEL[session.role_aktif] || session.role_aktif}
                </div>
              </div>
              <button
                onClick={onLogout}
                className="w-full text-left px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                Keluar
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
