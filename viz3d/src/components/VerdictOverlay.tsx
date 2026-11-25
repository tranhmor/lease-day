import { useMemo } from 'react';
import type { Lang, MonthlyRecord, VerdictsData } from '@/types/viz';
import { getDict } from '@/i18n';

interface MoverProfileOverlayProps {
  monthlyP: MonthlyRecord[];
  monthlyS: MonthlyRecord[];
  lang: Lang;
}

/** Chapter 6: H2 Early Mover Profile Panel (M13-M24 treated-zone move-ins by income group) */
export function MoverProfileOverlay({ monthlyP, monthlyS, lang }: MoverProfileOverlayProps) {
  const t = getDict(lang);

  const stats = useMemo(() => {
    const summarize = (rows: MonthlyRecord[]) => {
      const win = rows.filter((r) => r.month >= 13 && r.month <= 24);
      const groups = { low: 0, mid: 0, high: 0 };
      const incs: number[] = [];
      const cash: number[] = [];
      for (const r of win) {
        groups.low += r.treated_move_in_groups?.low ?? 0;
        groups.mid += r.treated_move_in_groups?.mid ?? 0;
        groups.high += r.treated_move_in_groups?.high ?? 0;
        incs.push(...(r.treated_move_in_incomes ?? []));
        cash.push(...(r.treated_move_in_cash ?? []));
      }
      const total = groups.low + groups.mid + groups.high;
      const meanInc = incs.length ? incs.reduce((a, b) => a + b, 0) / incs.length : 0;
      const meanCash = cash.length ? cash.reduce((a, b) => a + b, 0) / cash.length : 0;
      return { groups, total, meanInc, meanCash };
    };
    return { P: summarize(monthlyP), S: summarize(monthlyS) };
  }, [monthlyP, monthlyS]);

  const bar = (sc: 'P' | 'S') => {
    const d = stats[sc];
    const tot = Math.max(1, d.total);
    return (
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
          <span style={{ color: sc === 'P' ? 'var(--p)' : 'var(--s)', fontWeight: 600 }}>
            {sc} ({d.total} {t.moverProfile.totalMoves})
          </span>
          <span className="mono" style={{ color: 'var(--sub)' }}>
            {t.moverProfile.meanIncome}: ¥{Math.round(d.meanInc).toLocaleString()} · {t.moverProfile.meanCash}: ¥
            {Math.round(d.meanCash).toLocaleString()}
          </span>
        </div>
        <div style={{ display: 'flex', height: 10, borderRadius: 3, overflow: 'hidden', background: 'var(--track)' }}>
          <div style={{ width: `${(d.groups.low / tot) * 100}%`, background: 'var(--inc-low)' }} title={`low: ${d.groups.low}`} />
          <div style={{ width: `${(d.groups.mid / tot) * 100}%`, background: 'var(--inc-mid)' }} title={`mid: ${d.groups.mid}`} />
          <div style={{ width: `${(d.groups.high / tot) * 100}%`, background: 'var(--inc-high)' }} title={`high: ${d.groups.high}`} />
        </div>
      </div>
    );
  };

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        maxWidth: 480,
        margin: '0 auto',
        padding: '10px 14px',
        flexShrink: 0,
      }}
    >
      <div className="panel-header" style={{ marginBottom: 8 }}>
        <span>{t.moverProfile.title}</span>
        <div style={{ display: 'flex', gap: 8, fontSize: 10 }}>
          <span style={{ color: 'var(--inc-low)' }}>■ {t.moverProfile.low}</span>
          <span style={{ color: 'var(--inc-mid)' }}>■ {t.moverProfile.mid}</span>
          <span style={{ color: 'var(--inc-high)' }}>■ {t.moverProfile.high}</span>
        </div>
      </div>
      {bar('P')}
      {bar('S')}
    </div>
  );
}

interface VerdictOverlayProps {
  verdicts: VerdictsData;
  lang: Lang;
}

function badgeColor(v?: string): { bg: string; border: string; text: string } {
  if (!v) return { bg: 'color-mix(in srgb, var(--sub) 16%, transparent)', border: 'var(--tick)', text: 'var(--sub-2)' };
  const u = v.toUpperCase();
  if (u.startsWith('SUPPORTED') || u === 'PASS' || u === 'OK' || u.startsWith('NOT OVER')) {
    return { bg: 'color-mix(in srgb, var(--down) 16%, transparent)', border: 'var(--down)', text: 'var(--down)' };
  }
  if (u.startsWith('DIRECTIONAL') || u.startsWith('CAVEAT')) {
    return { bg: 'color-mix(in srgb, var(--announce) 16%, transparent)', border: 'var(--announce)', text: 'var(--announce)' };
  }
  return { bg: 'color-mix(in srgb, var(--p) 16%, transparent)', border: 'var(--p)', text: 'var(--up)' };
}

/**
 * Chapter 7: Pre-Registered Verdict Cards (H1, H2, H3, Bias B, Quality Gate).
 * Strictly cites aggregate/verdicts.json from analyze_v07.py; never recomputes significance (§9.7).
 */
export function VerdictOverlay({ verdicts, lang }: VerdictOverlayProps) {
  const t = getDict(lang);
  const r = verdicts.results;

  const h1Style = badgeColor(r.H1?.verdict);
  const h2Style = badgeColor(r.H2?.verdict);
  const h3Style = badgeColor(r.H3?.verdict);
  const bStyle = badgeColor(r.B?.verdict);
  const qStyle = badgeColor(r.quality?.verdict);

  const fmtCI = (ci?: [number, number] | null, suffix = '') =>
    ci ? `[${ci[0] >= 0 ? '+' : ''}${ci[0]}${suffix}, ${ci[1] >= 0 ? '+' : ''}${ci[1]}${suffix}]` : 'N/A (G=1)';

  return (
    <div
      className="hud-panel amber hud-scroll"
      style={{
        width: '100%',
        maxWidth: 560,
        maxHeight: '100%',
        margin: '0 auto',
        padding: '12px 15px',
        background: 'var(--panel-strong)',
      }}
    >
      <div className="panel-header" style={{ marginBottom: 4 }}>
        <span style={{ fontSize: 15 }}>{t.verdicts.title}</span>
        <span className="mono" style={{ fontSize: 11, color: 'var(--announce)' }}>
          {verdicts.group} · {verdicts.seeds.length} {lang === 'zh' ? '种子' : 'seeds'}
        </span>
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--sub)', marginBottom: 12 }}>{t.verdicts.subtitle}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {/* H1 */}
        <div style={{ padding: '10px 12px', background: 'var(--panel-inset)', border: '1px solid var(--line)', borderRadius: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{t.verdicts.h1Title}</span>
            <span
              className="mono"
              style={{
                fontSize: 10.5,
                padding: '2px 8px',
                borderRadius: 3,
                background: h1Style.bg,
                border: `1px solid ${h1Style.border}`,
                color: h1Style.text,
              }}
            >
              {r.H1?.verdict ?? 'N/A'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--sub)', marginTop: 3 }}>{t.verdicts.h1Desc}</div>
          {r.H1 && (
            <div className="mono" style={{ fontSize: 11.5, marginTop: 6, color: 'var(--text)' }}>
              b_P = <b>{r.H1.b_P_pct !== null ? `${r.H1.b_P_pct >= 0 ? '+' : ''}${r.H1.b_P_pct}%` : '—'}</b> · 95% CI:{' '}
              {fmtCI(r.H1.ci95_pct, '%')} · n={r.H1.n_offers} · Aux M24 P−S: {r.H1.aux_P_minus_S_rent_index_M24}
            </div>
          )}
        </div>

        {/* H2 */}
        <div style={{ padding: '10px 12px', background: 'var(--panel-inset)', border: '1px solid var(--line)', borderRadius: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{t.verdicts.h2Title}</span>
            <span
              className="mono"
              style={{
                fontSize: 10.5,
                padding: '2px 8px',
                borderRadius: 3,
                background: h2Style.bg,
                border: `1px solid ${h2Style.border}`,
                color: h2Style.text,
              }}
            >
              {r.H2?.verdict ?? 'N/A'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--sub)', marginTop: 3 }}>{t.verdicts.h2Desc}</div>
          {r.H2 && (
            <div className="mono" style={{ fontSize: 11.5, marginTop: 6, color: 'var(--text)' }}>
              ΔIncome: <b>{r.H2.income.P_minus_S !== null ? `${r.H2.income.P_minus_S >= 0 ? '+' : ''}¥${r.H2.income.P_minus_S}` : '—'}</b>{' '}
              {fmtCI(r.H2.income.ci95)} · ΔCash:{' '}
              <b>{r.H2.cash.P_minus_S !== null ? `${r.H2.cash.P_minus_S >= 0 ? '+' : ''}¥${r.H2.cash.P_minus_S}` : '—'}</b>{' '}
              (n: P={r.H2.n_move_ins.P}, S={r.H2.n_move_ins.S})
            </div>
          )}
        </div>

        {/* H3 */}
        <div style={{ padding: '10px 12px', background: 'var(--panel-inset)', border: '1px solid var(--line)', borderRadius: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{t.verdicts.h3Title}</span>
            <span
              className="mono"
              style={{
                fontSize: 10.5,
                padding: '2px 8px',
                borderRadius: 3,
                background: h3Style.bg,
                border: `1px solid ${h3Style.border}`,
                color: h3Style.text,
              }}
            >
              {r.H3?.verdict ?? 'N/A'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--sub)', marginTop: 3 }}>{t.verdicts.h3Desc}</div>
          {r.H3 && (
            <div className="mono" style={{ fontSize: 11.5, marginTop: 6, color: 'var(--text)' }}>
              No-hike (tight): L={r.H3.L_no_hike_when_tight !== null ? `${(r.H3.L_no_hike_when_tight * 100).toFixed(1)}%` : '—'} vs R=
              {r.H3.R_no_hike_when_tight != null ? `${(r.H3.R_no_hike_when_tight * 100).toFixed(1)}%` : '—'} · Counter accept: L=
              {r.H3.L_counter_accept !== null ? `${(r.H3.L_counter_accept * 100).toFixed(1)}%` : '—'} vs R=
              {r.H3.R_counter_accept != null ? `${(r.H3.R_counter_accept * 100).toFixed(1)}%` : '—'}
            </div>
          )}
        </div>

        {/* Bias B & Quality Gate Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div style={{ padding: '8px 10px', background: 'var(--panel-inset-2)', border: '1px solid var(--line)', borderRadius: 4 }}>
            <div style={{ fontSize: 10.5, color: 'var(--sub)' }}>{t.verdicts.biasTitle}</div>
            <div className="mono" style={{ fontSize: 11, marginTop: 4, color: bStyle.text }}>
              {r.B?.verdict ?? 'N/A'}
            </div>
          </div>
          <div style={{ padding: '8px 10px', background: 'var(--panel-inset-2)', border: '1px solid var(--line)', borderRadius: 4 }}>
            <div style={{ fontSize: 10.5, color: 'var(--sub)' }}>{t.verdicts.qualityTitle}</div>
            <div className="mono" style={{ fontSize: 11, marginTop: 4, color: qStyle.text }}>
              {r.quality ? `${r.quality.verdict} (max ${(r.quality.max_fallback_rate * 100).toFixed(2)}%)` : 'N/A'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
