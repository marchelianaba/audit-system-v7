import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 bg-gradient-to-br from-primary-50 via-white to-purple-50">
      <div className="max-w-2xl text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl integral-gradient text-white text-3xl font-bold mb-6 shadow-integral">
          ∫
        </div>
        <h1 className="text-4xl font-bold text-primary-dark mb-2">INTEGRAL AI Workspace</h1>
        <p className="text-sm uppercase tracking-wider text-primary font-semibold mb-4">
          Powered by Audit AI v7 · Claude Agent SDK
        </p>
        <p className="text-gray-600 mb-8 leading-relaxed">
          Workspace cerdas untuk seluruh pengawasan Inspektorat II Kementerian Komunikasi dan Digital RI.
          Terintegrasi dengan <b>SIMWAS v2 INTEGRAL</b> — dari Survey Pendahuluan hingga Laporan Hasil,
          dengan agen AI mendampingi setiap tahapan.
        </p>
        <Link
          href="/login"
          className="inline-block px-8 py-3 rounded-lg integral-gradient text-white font-semibold hover:opacity-95 transition shadow-integral"
        >
          Masuk ke Workspace
        </Link>
        <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-gray-500">
          <div className="p-3 rounded-lg bg-white border border-gray-100">
            <div className="text-primary font-semibold text-lg">17</div>
            skill pengawasan
          </div>
          <div className="p-3 rounded-lg bg-white border border-gray-100">
            <div className="text-primary font-semibold text-lg">7</div>
            tahapan workflow
          </div>
          <div className="p-3 rounded-lg bg-white border border-gray-100">
            <div className="text-primary font-semibold text-lg">2</div>
            agen Claude
          </div>
          <div className="p-3 rounded-lg bg-white border border-gray-100">
            <div className="text-primary font-semibold text-lg">HITL</div>
            review setiap temuan
          </div>
        </div>
      </div>
    </main>
  );
}
