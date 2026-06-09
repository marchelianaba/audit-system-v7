'use client';

/**
 * StageGrid — 7 tahapan workflow INTEGRAL mirror SIMWAS v2.
 *
 * Workflow (per keputusan user 8 Juni 2026):
 *   0. Survey Pendahuluan (only skill audit-*)
 *   1. KP (Kartu Penugasan)        — PT, template wiki
 *   2. PKP                          — KT, detail dari KP
 *   3. KKP                          — AT workspace (Konteks+Upload+AI+HITL+Approval)
 *   4. LRS KK                       — auto derived dari HITL approval AT
 *   5. Konsep Laporan               — KT workspace (Generate LHP+approve+edit)
 *   6. LRS LHP                      — PT/PM review LHP
 *   7. Laporan Hasil                — finalisasi (PJ/Inspektur)
 *
 * Bukti Cek AI dihapus per catatan user — audit trail terjamin via HITL log otomatis.
 */
import Link from 'next/link';

export type StageStatus = 'locked' | 'pending' | 'in_progress' | 'done';

export type StageInfo = {
  num: number | string;
  label: string;
  hint: string;
  status: StageStatus;
  href?: string;
};

const STATUS_BG: Record<StageStatus, string> = {
  locked: 'bg-gray-50 border-gray-200 text-gray-400',
  pending: 'bg-white border-gray-200 text-gray-700 hover:border-primary hover:shadow-integral cursor-pointer',
  in_progress: 'bg-amber-50 border-amber-300 text-amber-900',
  done: 'bg-green-50 border-green-300 text-green-900',
};

const STATUS_ICON: Record<StageStatus, string> = {
  locked: '🔒',
  pending: '○',
  in_progress: '⟳',
  done: '✓',
};

export function StageGrid({
  stages,
  showSurvey,
}: {
  stages: StageInfo[];
  showSurvey?: boolean;
}) {
  const visible = stages.filter((s) => s.num !== 0 || showSurvey);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {visible.map((s) => {
        const card = (
          <div
            className={`p-3 rounded-lg border-2 transition ${STATUS_BG[s.status]}`}
          >
            <div className="flex items-start gap-2">
              <div className={`w-9 h-9 rounded-md flex items-center justify-center font-bold text-sm flex-shrink-0 ${
                s.status === 'done' ? 'bg-green-600 text-white' :
                s.status === 'in_progress' ? 'bg-amber-500 text-white' :
                s.status === 'locked' ? 'bg-gray-200 text-gray-500' :
                'bg-primary-100 text-primary-dark'
              }`}>
                {s.num}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-sm truncate">{s.label}</div>
                <div className="text-xs opacity-80 truncate">{s.hint}</div>
              </div>
              <span className="text-base opacity-50">{STATUS_ICON[s.status]}</span>
            </div>
          </div>
        );
        return s.href && s.status !== 'locked' ? (
          <Link key={s.num} href={s.href}>{card}</Link>
        ) : (
          <div key={s.num}>{card}</div>
        );
      })}
    </div>
  );
}
