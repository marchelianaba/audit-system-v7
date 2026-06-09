'use client';

/**
 * AppShell — wrapper untuk semua authenticated pages.
 *
 * Layout: Sidebar (kiri) + TopBar (atas) + Main content + Footer.
 * Sidebar collapsible state disimpan di localStorage supaya stabil antar nav.
 */
import { useEffect, useState } from 'react';
import { Toaster } from 'sonner';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem('integral_sidebar_collapsed');
    if (saved === '1') setCollapsed(true);
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    if (mounted) {
      localStorage.setItem('integral_sidebar_collapsed', next ? '1' : '0');
    }
  };

  return (
    <div className="min-h-screen bg-surface">
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className={`transition-all duration-200 ${collapsed ? 'ml-16' : 'ml-60'}`}>
        <TopBar />
        <main className="px-6 py-6">{children}</main>
        <footer className="px-6 py-4 border-t border-gray-100 mt-12 text-xs text-gray-500 flex justify-between">
          <span>Copyright © 2026 INTEGRAL AI Workspace. Inspektorat II — Kementerian Komunikasi dan Digital RI.</span>
          <span>Powered by Audit AI v7 + Claude Agent SDK</span>
        </footer>
      </div>
      <Toaster position="top-right" richColors closeButton />
    </div>
  );
}
