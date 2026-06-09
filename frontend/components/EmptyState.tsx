'use client';

/**
 * EmptyState — komponen reusable untuk halaman tanpa data.
 *
 * Mirror style SIMWAS v2 (rocket emoji + helpful text + CTA).
 */
import { ReactNode } from 'react';

export function EmptyState({
  icon = '🚀',
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="text-6xl mb-4">{icon}</div>
      <h3 className="text-lg font-bold text-ink mb-1">{title}</h3>
      {description && <p className="text-sm text-gray-500 max-w-md mb-6">{description}</p>}
      {action}
    </div>
  );
}
