'use client';

/**
 * TemplatePickerKpPkp — picker template KP atau PKP dari wiki.
 *
 * UX: dropdown skill → list template available → preview frontmatter +
 * isi body → tombol "Pakai Template Ini".
 *
 * Untuk Sprint 2 INTEGRAL — prototype-grade. Tidak include form fill
 * (akan datang di Sprint 3 berikutnya).
 */
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type TemplateItem = Awaited<ReturnType<typeof api.listTemplates>>['items'][number];

export function TemplatePickerKpPkp({
  kind,
  skill,
  onUse,
}: {
  kind: 'kp' | 'pkp';
  skill: string;
  onUse?: (template: { slug: string; body: string; meta: Record<string, any> }) => void;
}) {
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ slug: string; body: string; meta: Record<string, any> } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .listTemplates(kind, skill)
      .then((r) => {
        setItems(r.items);
        setError(null);
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [kind, skill]);

  const select = async (slug: string) => {
    setSelectedSlug(slug);
    try {
      const r = await api.getTemplate(kind, slug);
      setPreview(r);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-500 italic">Memuat template {kind.toUpperCase()}…</div>;
  }
  if (error) {
    return <div className="p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>;
  }
  if (items.length === 0) {
    return (
      <div className="p-3 rounded bg-amber-50 border border-amber-200 text-amber-800 text-sm">
        Belum ada template {kind.toUpperCase()} untuk skill <code>{skill}</code>. Bisa pakai template{' '}
        <b>default</b> sebagai dasar.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs uppercase text-gray-400 tracking-wider mb-1">
          Pilih Template {kind.toUpperCase()}
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map((it) => (
            <button
              key={it.slug}
              onClick={() => select(it.slug)}
              className={`text-left p-3 rounded-lg border-2 transition ${
                selectedSlug === it.slug
                  ? 'border-primary bg-primary-50'
                  : 'border-gray-200 hover:border-primary-300 hover:shadow-card bg-white'
              }`}
            >
              <div className="font-semibold text-sm text-primary-dark">{it.judul}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                skill: <span className="font-mono">{it.skill}</span> · {it.field_required.length} field wajib · v{it.versi || '1.0'}
              </div>
            </button>
          ))}
        </div>
      </div>

      {preview && (
        <div className="integral-card p-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-sm text-primary-dark">Preview · {preview.slug}</h4>
            {onUse && (
              <button
                onClick={() => onUse(preview)}
                className="px-3 py-1.5 rounded bg-primary text-white text-xs font-semibold hover:bg-primary-dark"
              >
                ✓ Pakai Template Ini
              </button>
            )}
          </div>

          {/* Field required */}
          <div className="mb-3">
            <div className="text-xs uppercase text-gray-400 tracking-wider mb-1.5">Field Wajib Diisi</div>
            <div className="flex flex-wrap gap-1">
              {(preview.meta.field_required || []).map((f: string) => (
                <span key={f} className="text-[10px] px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-mono">
                  {f}
                </span>
              ))}
            </div>
          </div>

          {/* Field optional */}
          {(preview.meta.field_optional || []).length > 0 && (
            <div className="mb-3">
              <div className="text-xs uppercase text-gray-400 tracking-wider mb-1.5">Field Opsional</div>
              <div className="flex flex-wrap gap-1">
                {(preview.meta.field_optional || []).map((f: string) => (
                  <span key={f} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-700 border border-gray-200 font-mono">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Body preview (truncated markdown) */}
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500 hover:text-primary">
              Lihat body markdown ({preview.body.length} char)
            </summary>
            <pre className="mt-2 p-3 bg-gray-50 rounded text-[11px] overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
              {preview.body}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
