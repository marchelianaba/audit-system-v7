import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="max-w-xl text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-white text-2xl font-bold mb-6">
          v7
        </div>
        <h1 className="text-3xl font-bold text-primary-dark mb-2">Audit AI v7</h1>
        <p className="text-gray-600 mb-8">
          Prototype web Inspektorat II Kementerian Komunikasi dan Digital.
          Reviu RKA-K/L &amp; Reviu Pengadaan berbasis Claude Agent SDK.
        </p>
        <Link
          href="/login"
          className="inline-block px-6 py-3 rounded-lg bg-primary text-white font-semibold hover:bg-primary-dark transition"
        >
          Masuk
        </Link>
      </div>
    </main>
  );
}
