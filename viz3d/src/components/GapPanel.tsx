import { useMemo } from 'react';
import type { Lang, MonthlyCIData } from '@/types/viz';
import { getDict } from '@/i18n';

interface GapPanelProps {
  monthlyCI: MonthlyCIData;
  month: number;
  announceMonth: number;
  openMonth: number;
  lang: Lang;
  onClickSplit: () => void;
}

export function GapPanel({ monthlyCI, month, announceMonth, openMonth, lang, onClickSplit }: GapPanelProps) {
  const t = getDict(lang);
  const series = monthlyCI.paired_diffs?.P_minus_S?.rent_index_treated ?? [];
  const cur = series[month - 1] ?? [0, 0];
  const [meanVal, halfCi] = cur;

  const { linePath, ciPath, yZero, cx, cy, minV, maxV } = useMemo(() => {
    const W = 154;
    const H = 70;
    let lo = -1.2;
    let hi = 2.6;
    for (const [m, h] of series) {
      lo = Math.min(lo, m - h - 0.3);
      hi = Math.max(hi, m + h + 0.3);
    }
    const x = (i: number) => 4 + ((W - 8) * i) / Math.max(1, series.length - 1);
    const y = (v: number) => H - 6 - ((v - lo) / Math.max(0.5, hi - lo)) * (H - 12);

    let lPath = '';
    const upperPts: string[] = [];
    const lowerPts: string[] = [];
    series.forEach(([m, h], i) => {
      const px = x(i);
      lPath += (i === 0 ? 'M' : 'L') + `${px.toFixed(1)},${y(m).toFixed(1)}`;
      upperPts.push(`${px.toFixed(1)},${y(m + h).toFixed(1)}`);
      lowerPts.unshift(`${px.toFixed(1)},${y(m - h).toFixed(1)}`);
    });
    const cPath = upperPts.length ? `M${upperPts.join('L')}L${lowerPts.join('L')}Z` : '';

    return {
      linePath: lPath,
      ciPath: cPath,
      yZero: y(0),
      cx: x(Math.max(0, month - 1)),
      cy: y(meanVal),
      minV: lo,
      maxV: hi,
    };
  }, [series, month, meanVal]);

  const note =
    month < announceMonth ? t.gap.preAnnounce : month < openMonth ? t.gap.announceWindow : t.gap.postOpen;

  return (
    <div
      className="hud-panel"
      onClick={onClickSplit}
      title={t.gap.clickToSplit}
      style={{
        width: '100%',
        padding: '14px 16px 12px',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'border-color 0.2s',
      }}
    >
      <div className="panel-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 3 }}>
        <span>{t.gap.title}</span>
        <small>{t.gap.subtitle}</small>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <div
            className="serif num"
            style={{
              fontSize: 38,
              fontWeight: 400,
              lineHeight: 1.05,
              color: meanVal > 0.05 ? 'var(--accent)' : 'var(--text)',
            }}
          >
            {meanVal >= 0 ? '+' : ''}
            {meanVal.toFixed(2)}
            <small className="num" style={{ fontSize: 12, color: 'var(--sub)', marginLeft: 4 }}>{t.gap.unitPt}</small>
          </div>
          {halfCi > 0 && (
            <div className="num" style={{ fontSize: 11, color: 'var(--sub)', marginTop: 4 }}>
              95% CI: ±{halfCi.toFixed(2)} ({monthlyCI.seeds.length} {lang === 'zh' ? '种子' : 'seeds'})
            </div>
          )}
          <div style={{ fontSize: 12, color: 'var(--text-soft)', marginTop: 6, lineHeight: 1.45 }}>{note}</div>
        </div>

        <svg width={154} height={70} style={{ flexShrink: 0 }}>
          {/* Zero baseline */}
          <line x1={4} x2={150} y1={yZero} y2={yZero} stroke="var(--tick)" strokeWidth={0.8} />
          {/* M13 & M25 guide lines */}
          <line
            x1={4 + (146 * (announceMonth - 1)) / 35}
            x2={4 + (146 * (announceMonth - 1)) / 35}
            y1={4}
            y2={66}
            stroke="var(--sub)"
            strokeOpacity={0.5}
            strokeDasharray="1 2"
          />
          <line
            x1={4 + (146 * (openMonth - 1)) / 35}
            x2={4 + (146 * (openMonth - 1)) / 35}
            y1={4}
            y2={66}
            stroke="var(--sub)"
            strokeOpacity={0.5}
            strokeDasharray="1 2"
          />
          {/* 95% CI Band */}
          {ciPath && <path d={ciPath} fill="var(--p)" fillOpacity={0.14} />}
          {/* Mean Curve */}
          {linePath && <path d={linePath} fill="none" stroke="var(--p)" strokeWidth={1.5} />}
          {/* Active Month Dot */}
          <circle cx={cx} cy={cy} r={3} fill="var(--p)" stroke="var(--panel-solid)" strokeWidth={1.2} />
          <text x={150} y={10} textAnchor="end" fontSize={9} fill="var(--sub)" fontFamily="-apple-system, sans-serif">
            {maxV.toFixed(1)}
          </text>
          <text x={150} y={66} textAnchor="end" fontSize={9} fill="var(--sub)" fontFamily="-apple-system, sans-serif">
            {minV.toFixed(1)}
          </text>
        </svg>
      </div>

      <div style={{ fontSize: 11, color: 'var(--sub)', marginTop: 10, textDecoration: 'underline', textUnderlineOffset: 3, textDecorationColor: 'var(--line)' }}>
        {t.gap.clickToSplit} →
      </div>
    </div>
  );
}
