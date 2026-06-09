'use client';

/**
 * Sidebar — INTEGRAL AI Workspace
 *
 * Mirror style SIMWAS v2 (lihat docs/rencana-integrasi-simwas-v2.html):
 * - 240px width default, collapsible jadi 64px via tombol « di pojok atas
 * - Logo brand di atas + heading "MENUS"
 * - Items: Home, Dashboard, Penugasan > Daftar, CACM > Kriteria, Knowledge > Pattern/Template
 * - Active state: bg ungu solid, text putih
 * - Sub-menu indented dgn dot bullet
 */
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

type MenuItem = {
  href: string;
  label: string;
  icon: string;            // emoji untuk prototype — bisa diganti SVG nanti
  children?: { href: string; label: string }[];
};

const MENU_ITEMS: MenuItem[] = [
  { href: '/home', label: 'Home', icon: '🏠' },
  { href: '/dashboard', label: 'Dashboard', icon: '📊' },
  {
    href: '/penugasan',
    label: 'Penugasan',
    icon: '🗂',
    children: [{ href: '/penugasan', label: 'Daftar Penugasan' }],
  },
  {
    href: '/cacm',
    label: 'CACM',
    icon: '🎯',
    children: [
      { href: '/cacm', label: 'Run CACM' },
      { href: '/knowledge#kriteria-cacm', label: 'Kriteria CACM' },
    ],
  },
  {
    href: '/knowledge',
    label: 'Knowledge',
    icon: '📚',
    children: [
      { href: '/knowledge#pattern', label: 'Pattern Temuan' },
      { href: '/knowledge#template-kp', label: 'Template KP/PKP' },
      { href: '/knowledge#template-dokumen', label: 'Template Dokumen' },
      { href: '/knowledge#writeback', label: 'Tulis-balik Vault' },
    ],
  },
];

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const pathname = usePathname();
  // Track expanded sub-menu (multiple bisa terbuka)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Auto-expand parent dari halaman aktif saat mount
  useEffect(() => {
    const next: Record<string, boolean> = {};
    for (const item of MENU_ITEMS) {
      if (item.children && pathname.startsWith(item.href)) {
        next[item.href] = true;
      }
    }
    setExpanded(next);
  }, [pathname]);

  const isActive = (href: string) => {
    if (href === '/home') return pathname === '/' || pathname === '/home';
    return pathname === href || pathname.startsWith(href + '/');
  };

  return (
    <aside
      className={`fixed left-0 top-0 h-full bg-white border-r border-gray-200 transition-all duration-200 z-30 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Brand + Collapse toggle */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-gray-100">
        {!collapsed && (
          <Link href="/home" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg integral-gradient flex items-center justify-center text-white font-bold text-sm">
              ∫
            </div>
            <div className="leading-tight">
              <div className="font-bold text-primary-dark text-sm">INTEGRAL</div>
              <div className="text-[10px] text-gray-500 -mt-0.5">AI Workspace</div>
            </div>
          </Link>
        )}
        {collapsed && (
          <div className="w-8 h-8 mx-auto rounded-lg integral-gradient flex items-center justify-center text-white font-bold text-sm">
            ∫
          </div>
        )}
        <button
          onClick={onToggle}
          className="text-gray-400 hover:text-primary text-lg leading-none"
          title={collapsed ? 'Buka sidebar' : 'Tutup sidebar'}
        >
          {collapsed ? '»' : '«'}
        </button>
      </div>

      {/* Menu heading */}
      {!collapsed && (
        <div className="px-4 pt-4 pb-2 text-xs uppercase text-gray-400 tracking-wider">
          Menus
        </div>
      )}

      {/* Menu items */}
      <nav className="px-2 space-y-0.5">
        {MENU_ITEMS.map((item) => {
          const active = isActive(item.href);
          const isExpanded = expanded[item.href] ?? false;
          const hasChildren = item.children && item.children.length > 0;
          return (
            <div key={item.href}>
              <Link
                href={item.href}
                onClick={(e) => {
                  if (hasChildren && !collapsed) {
                    // Toggle expand kalau di-klik parent + bukan link langsung
                    setExpanded((p) => ({ ...p, [item.href]: !p[item.href] }));
                  }
                }}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition ${
                  active
                    ? 'bg-primary text-white font-medium shadow-integral'
                    : 'text-gray-700 hover:bg-primary-50'
                } ${collapsed ? 'justify-center' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <span className="text-base">{item.icon}</span>
                {!collapsed && (
                  <>
                    <span className="flex-1">{item.label}</span>
                    {hasChildren && (
                      <span className={`text-xs opacity-60 transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                        ▾
                      </span>
                    )}
                  </>
                )}
              </Link>
              {/* Sub-menu items */}
              {hasChildren && !collapsed && isExpanded && (
                <div className="ml-3 mt-1 mb-1 space-y-0.5 border-l border-gray-200 pl-3">
                  {item.children!.map((c) => {
                    const childActive = pathname === c.href || pathname.startsWith(c.href.split('#')[0] + '/');
                    return (
                      <Link
                        key={c.href}
                        href={c.href}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition ${
                          childActive
                            ? 'text-primary font-medium'
                            : 'text-gray-600 hover:text-primary'
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
                        <span>{c.label}</span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
