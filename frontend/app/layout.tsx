import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'INTEGRAL AI Workspace — Inspektorat II Komdigi',
  description:
    'Workspace AI untuk Reviu RKA-K/L, Reviu/Audit/Pemantauan Pengadaan, Audit Kinerja, Evaluasi SAKIP/SPIP/RB/MR, Konsultansi & Pendampingan — terintegrasi dengan SIMWAS v2 INTEGRAL.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
