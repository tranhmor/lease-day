import { useEffect, useRef, useState } from 'react';
import type { Lang, MonthlyRecord } from '@/types/viz';
import { getDict } from '@/i18n';

interface VitalsPanelProps {
  current: MonthlyRecord | undefined;
  prev: MonthlyRecord | undefined;
  llmCalls: number;
  isIllustrative: boolean;
  lang: Lang;
  onHoverMetric: (metric: string | null) => void;
}

/** Smooth 400ms rolling number hook (§4.3) */
function useTweenNumber(target: number, durationMs = 380): number {
  const [val, setVal] = useState(target);
  const prevRef = useRef(target);

  useEffect(() => {
    const startVal = prevRef.current;
    if (Math.abs(target - startVal) < 1e-4) {
      setVal(target);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3);
      const cur = startVal + (target - startVal) * eased;
      setVal(cur);
      if (p < 1) {
        raf = requestAnimationFrame(step);
      } else {
        prevRef.current = target;
      }
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      prevRef.current = target;
    };
  }, [target, durationMs]);

  return val;
}

export function VitalsPanel({ current, prev, llmCalls, isIllustrative, lang, onHoverMetric }: VitalsPanelProps) {
  const t = getDict(lang);

  const rentIdx = useTweenNumber(current?.rent_index_treated ?? 100);
  const vacPct = useTweenNumber((current?.vacancy_treated ?? 0) * 100);
  const commute = useTweenNumber(current?.commute_treated ?? 60);
  const moveIns = useTweenNumber(current?.treated_move_ins ?? 0);
  const calls = useTweenNumber(llmCalls);

  const rentDelta = current && prev ? current.rent_index_treated - prev.rent_index_treated : 0;

  const rows: Array<{
    key: string;
    label: string;
    value: string;
    unit?: string;
    delta?: number;
  }> = [
    { key: 'rent', label: t.vitals.rentIndex, value: rentIdx.toFixed(1), delta: rentDelta },
    { key: 'vacancy', label: t.vitals.vacancy, value: vacPct.toFixed(1), unit: '%' },
    { key: 'commute', label: t.vitals.commute, value: commute.toFixed(1), unit: t.vitals.unitMin },
    { key: 'moveIns', label: t.vitals.moveIns, value: Math.round(moveIns).toString(), unit: t.vitals.unitHouse },
    { key: 'llmCalls', label: t.vitals.llmCalls, value: Math.round(calls).toString(), unit: t.vitals.unitCalls },
  ];

  return (
    <div
      className="hud-panel accent-cool"
      style={{
        width: '100%',
        padding: '11px 14px',
        flexShrink: 0,
      }}
    >
      <div className="panel-header">
        <span>{t.vitals.title}</span>
        <small style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span>{t.vitals.scope}</span>
          {isIllustrative && (
            <>
              <span className="sep" />
              <span style={{ color: 'var(--announce)' }}>{lang === 'zh' ? '示意' : 'Illust.'}</span>
            </>
          )}
        </small>
      </div>

      {rows.map((r) => (
        <div
          key={r.key}
          onMouseEnter={() => onHoverMetric(r.key)}
          onMouseLeave={() => onHoverMetric(null)}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            padding: '6px 4px',
            borderBottom: '1px dashed var(--line-dashed)',
            fontSize: 12,
            color: 'var(--sub)',
            cursor: 'default',
            borderRadius: 3,
            transition: 'background 0.15s',
          }}
        >
          <span>{r.label}</span>
          <span style={{ display: 'inline-flex', alignItems: 'baseline' }}>
            <b className="num" style={{ fontSize: 21, fontWeight: 500, color: 'var(--text)', lineHeight: 1.1 }}>
              {r.value}
            </b>
            {r.unit && (
              <small style={{ fontSize: 10.5, color: 'var(--sub)', marginLeft: 3, fontWeight: 400 }}>{r.unit}</small>
            )}
            {r.delta !== undefined && Math.abs(r.delta) >= 0.01 && (
              <span
                className="num"
                style={{
                  fontSize: 10.5,
                  marginLeft: 6,
                  color: r.delta > 0 ? 'var(--up)' : 'var(--down)',
                }}
              >
                {r.delta > 0 ? '▲' : '▼'}
                {Math.abs(r.delta).toFixed(2)}
              </span>
            )}
          </span>
        </div>
      ))}
      <div style={{ fontSize: 10, color: 'var(--sub)', marginTop: 6, opacity: 0.78 }}>{t.vitals.hoverTip}</div>
    </div>
  );
}
