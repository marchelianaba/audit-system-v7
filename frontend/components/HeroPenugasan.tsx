'use client';

/**
 * HeroPenugasan — header detail penugasan ala SIMWAS v2.
 *
 * Layout: 2 kolom
 *   Left (col-span-1, fixed width-ish): Info penugasan (logo unit, nomor ST,
 *     tanggal mulai/selesai, participants, days, jenis pengawasan, judul, progress)
 *   Right (col-span-2): StageGrid 7 tahapan
 */
import { StageGrid, StageInfo, StageStatus } from './StageGrid';
import { Penugasan } from '@/lib/api';

const SKILL_LABEL: Record<string, string> = {
  'reviu-rka-kl': 'Reviu RKA-K/L',
  'reviu-pengadaan': 'Reviu Pengadaan',
  'reviu-umum': 'Reviu Umum',
  'audit-pengadaan': 'Audit Pengadaan',
  'audit-kinerja': 'Audit Kinerja',
  'audit-umum': 'Audit Umum',
  'evaluasi-sakip': 'Evaluasi SAKIP',
  'evaluasi-spip': 'Evaluasi SPIP',
  'evaluasi-reformasi-birokrasi': 'Evaluasi Reformasi Birokrasi',
  'evaluasi-manajemen-risiko': 'Evaluasi Manajemen Risiko',
  'evaluasi-umum': 'Evaluasi Umum',
  'kepatuhan-saipi': 'Kepatuhan SAIPI (QA)',
  'konsultansi-umum': 'Konsultansi Umum',
  'konsultasi-pengadaan': 'Pendampingan Pengadaan',
  'pemantauan-pengadaan': 'Pemantauan Pengadaan',
  'pemantauan-tindak-lanjut': 'Pemantauan Tindak Lanjut',
  'pemantauan-umum': 'Pemantauan Umum',
};

const SKILL_GROUP: Record<string, 'audit' | 'reviu' | 'evaluasi' | 'pemantauan' | 'konsultasi'> = {
  'audit-pengadaan': 'audit',
  'audit-kinerja': 'audit',
  'audit-umum': 'audit',
  'reviu-rka-kl': 'reviu',
  'reviu-pengadaan': 'reviu',
  'reviu-umum': 'reviu',
  'evaluasi-sakip': 'evaluasi',
  'evaluasi-spip': 'evaluasi',
  'evaluasi-reformasi-birokrasi': 'evaluasi',
  'evaluasi-manajemen-risiko': 'evaluasi',
  'evaluasi-umum': 'evaluasi',
  'kepatuhan-saipi': 'evaluasi',
  'pemantauan-pengadaan': 'pemantauan',
  'pemantauan-tindak-lanjut': 'pemantauan',
  'pemantauan-umum': 'pemantauan',
  'konsultansi-umum': 'konsultasi',
  'konsultasi-pengadaan': 'konsultasi',
};

// Map status penugasan v7 → status tahapan workflow INTEGRAL.
// Heuristic: bila penugasan ada di status KKP_*, tahapan 3 in_progress; LHP_* tahapan 5 dst.
function deriveStageStatus(penugasan: Penugasan, stageNum: number): StageStatus {
  const status = penugasan.status as string;
  // Tahapan progression sederhana berbasis status:
  //   DRAFT → semua kecuali KP locked (KP pending)
  //   INGESTING / KKP_IN_PROGRESS → KP done, PKP done, KKP in_progress
  //   KKP_QC → KKP in_progress (QC)
  //   KKP_DONE → KKP done, LRS KK done, Konsep pending
  //   LHP_IN_PROGRESS / LHP_QC → Konsep in_progress
  //   LHP_DONE → semua done
  const statusOrder = [
    'DRAFT', 'INGESTING',
    'KKP_IN_PROGRESS', 'KKP_QC', 'KKP_DONE',
    'LHP_IN_PROGRESS', 'LHP_QC', 'LHP_DONE',
  ];
  const idx = statusOrder.indexOf(status);

  // Stage 0 (Survey) — bila skill audit-*, status = pending kalau belum upload
  if (stageNum === 0) {
    return SKILL_GROUP[penugasan.skill] === 'audit' ? 'pending' : 'locked';
  }

  // Stage 1 KP — selalu pending sampai DRAFT, done setelah upload KP
  if (stageNum === 1) return idx >= 0 ? 'done' : 'pending';

  // Stage 2 PKP — sama
  if (stageNum === 2) return idx >= 1 ? 'done' : 'pending';

  // Stage 3 KKP
  if (stageNum === 3) {
    if (status === 'KKP_DONE' || status === 'LHP_IN_PROGRESS' || status === 'LHP_QC' || status === 'LHP_DONE') return 'done';
    if (status === 'KKP_IN_PROGRESS' || status === 'KKP_QC' || status === 'INGESTING') return 'in_progress';
    return 'pending';
  }

  // Stage 4 LRS KK
  if (stageNum === 4) {
    if (status === 'KKP_DONE' || status === 'LHP_IN_PROGRESS' || status === 'LHP_QC' || status === 'LHP_DONE') return 'done';
    return idx >= 4 ? 'in_progress' : 'pending';
  }

  // Stage 5 Konsep Laporan
  if (stageNum === 5) {
    if (status === 'LHP_DONE') return 'done';
    if (status === 'LHP_IN_PROGRESS' || status === 'LHP_QC') return 'in_progress';
    return idx >= 4 ? 'pending' : 'locked';
  }

  // Stage 6 LRS LHP — locked sampai LHP_DONE
  if (stageNum === 6) {
    return status === 'LHP_DONE' ? 'in_progress' : 'locked';
  }

  // Stage 7 Laporan Hasil
  if (stageNum === 7) {
    return status === 'LHP_DONE' ? 'pending' : 'locked';
  }

  return 'pending';
}

export function HeroPenugasan({ penugasan }: { penugasan: Penugasan }) {
  const skillGroup = SKILL_GROUP[penugasan.skill];
  const showSurvey = skillGroup === 'audit';
  const skillLabel = SKILL_LABEL[penugasan.skill] || penugasan.skill;

  // Progress % berbasis tahapan done
  const totalStages = showSurvey ? 8 : 7;
  const stages: StageInfo[] = [
    { num: 0, label: 'Survey Pendahuluan', hint: 'Hanya audit-*', status: deriveStageStatus(penugasan, 0) },
    { num: 1, label: 'Kartu Penugasan', hint: 'PT · template wiki', status: deriveStageStatus(penugasan, 1) },
    { num: 2, label: 'PKP', hint: 'KT · detail dari KP', status: deriveStageStatus(penugasan, 2) },
    { num: 3, label: 'KKP', hint: 'AT · AI + HITL', status: deriveStageStatus(penugasan, 3) },
    { num: 4, label: 'LRS KK', hint: 'auto dari approval', status: deriveStageStatus(penugasan, 4) },
    { num: 5, label: 'Konsep Laporan', hint: 'KT · LHP draft', status: deriveStageStatus(penugasan, 5) },
    { num: 6, label: 'LRS LHP', hint: 'PT/PM review', status: deriveStageStatus(penugasan, 6) },
    { num: 7, label: 'Laporan Hasil', hint: 'Inspektur', status: deriveStageStatus(penugasan, 7) },
  ];

  const doneCount = stages.filter((s, i) => (i > 0 || showSurvey) && s.status === 'done').length;
  const progress = Math.round((doneCount / totalStages) * 100);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Left panel — info penugasan */}
      <div className="md:col-span-1 integral-card p-4">
        <div className="flex items-center gap-3 mb-3 pb-3 border-b border-gray-100">
          <div className="w-10 h-10 rounded-lg bg-primary-100 text-primary-dark flex items-center justify-center text-lg">🏛</div>
          <div>
            <div className="font-semibold text-sm">Inspektorat II</div>
            <div className="text-xs text-gray-500 font-mono">{penugasan.nomor_st || '[Nomor ST belum diisi]'}</div>
          </div>
        </div>
        <div className="space-y-2 text-xs">
          <div>
            <div className="text-gray-400 uppercase text-[10px] mb-0.5">Tanggal ST</div>
            <div>{penugasan.tanggal_st || <span className="text-gray-400">—</span>}</div>
          </div>
          <div>
            <div className="text-gray-400 uppercase text-[10px] mb-0.5">Jenis Pengawasan</div>
            <div className="font-medium text-primary-dark">{skillLabel}</div>
          </div>
          <div>
            <div className="text-gray-400 uppercase text-[10px] mb-0.5">Obyek</div>
            <div>{penugasan.obyek}</div>
          </div>
          <div>
            <div className="text-gray-400 uppercase text-[10px] mb-0.5">Status</div>
            <div className="inline-block px-2 py-0.5 rounded-full bg-primary-50 text-primary text-[11px] font-semibold">
              {penugasan.status}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4 pt-3 border-t border-gray-100">
          <div className="flex justify-between text-xs mb-1.5">
            <span className="text-gray-500">Progres Tahapan</span>
            <span className="font-semibold text-primary">{doneCount}/{totalStages} • {progress}%</span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full integral-gradient rounded-full transition-all" style={{ width: `${progress}%` }}></div>
          </div>
        </div>
      </div>

      {/* Right panel — 7/8 tahapan grid */}
      <div className="md:col-span-2 integral-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-primary-dark">Tahapan Pengawasan ala INTEGRAL</h3>
          <span className="text-[10px] text-gray-400 uppercase tracking-wider">
            workflow {totalStages}-tahap
          </span>
        </div>
        <StageGrid stages={stages} showSurvey={showSurvey} />
      </div>
    </div>
  );
}
