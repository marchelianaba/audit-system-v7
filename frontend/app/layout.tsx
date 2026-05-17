import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Audit AI v7 — Inspektorat II Komdigi',
  description: 'Prototype web Audit AI v7',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
