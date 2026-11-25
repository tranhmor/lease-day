import { useMemo, useRef } from 'react';
import { Pause, Play } from 'lucide-react';
import type { Lang, MonthlyCIData, Scenario } from '@/types/viz';
import { getDict } from '@/i18n';

interface TimelineBarProps {
  monthlyCI: MonthlyCIData;
  month: number;
  scenario: Scenario;
  playing: boolean;
  speed: number;
  announceMonth: number;
  openMonth: number;
  lang: Lang;
  onTogglePlay: () => void;
  onCycleSpeed: () => void;
  onSeekMonth: (m: number) => void;
}

const SC_COLORS: Record<Scenario, string> = {
  N: 'var(--n)',
  S: 'var(--s)',
  P: 'var(--p)',
};

export function TimelineBar({
  monthlyCI,
  month,
  scenario,
  playing,
  speed,
  announceMonth,
  openMonth,
  lang,
  onTogglePlay,
  onCycleSpeed,
  onSeekMonth,
}: TimelineBarProps) {
  const t = getDict(lang);
  const svgRef = useRef<SVGSVGElement>(null);
  const draggingRef = useRef(false);

  const W = 680;
  const H = 86;
  const padX = 16;

  const { curves, ciBands, xOf, yOf } = useMemo(() => {
    let lo = 98.5;
    let hi = 104.5;
    for (const sc of ['N', 'S', 'P'] as Scenario[]) {
      const ser = monthlyCI.scenarios[sc]?.rent_index_treated ?? [];
      for (const [m, h] of ser) {
        lo = Math.min(lo, m - h - 0.5);
        hi = Math.max(hi, m + h + 0.5);
      }
    }

    const x = (m: number) => padX + ((W - padX * 2) * (m - 1)) / 35;
    const y = (v: number) => 60 - ((v - lo) / Math.max(1, hi - lo)) * 52;

    const cMap: Record<Scenario, string> = { N: '', S: '', P: '' };
    const bMap: Record<Scenario, string> = { N: '', S: '', P: '' };

    for (const sc of ['N', 'S', 'P'] as Scenario[]) {
      const ser = monthlyCI.scenarios[sc]?.rent_index_treated ?? [];
      let d = '';
      const up: string[] = [];
      const dn: string[] = [];
      ser.forEach(([mean, half], idx) => {
        const px = x(idx + 1);
        d += (idx === 0 ? 'M' : 'L') + `${px.toFixed(1)},${y(mean).toFixed(1)}`;
        up.push(`${px.toFixed(1)},${y(mean + half).toFixed(1)}`);
        dn.unshift(`${px.toFixed(1)},${y(mean - half).toFixed(1)}`);
      });
      cMap[sc] = d;
      bMap[sc] = up.length ? `M${up.join('L')}L${dn.join('L')}Z` : '';
    }
    return { curves: cMap, ciBands: bMap, xOf: x, yOf: y };
  }, [monthlyCI]);

  const jumpFromClientX = (clientX: number) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const frac = (clientX - rect.left - (padX / W) * rect.width) / (rect.width * ((W - padX * 2) / W));
    const m = Math.max(1, Math.min(36, Math.round(1 + frac * 35)));
    onSeekMonth(m);
  };

  const curSeries = monthlyCI.scenarios[scenario]?.rent_index_treated ?? [];
  const curVal = curSeries[month - 1]?.[0] ?? 100;

  const ticks: Array<[number, string, string]> = [
    [1, t.timeline.ticks.m1, 'var(--sub)'],
    [7, t.timeline.ticks.m7, 'var(--sub)'],
    [announceMonth, t.timeline.ticks.m13, 'var(--up)'],
    [19, t.timeline.ticks.m19, 'var(--sub)'],
    [openMonth, t.timeline.ticks.m25, 'var(--announce)'],
    [31, t.timeline.ticks.m31, 'var(--sub)'],
    [36, t.timeline.ticks.m36, 'var(--sub)'],
  ];

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        padding: '8px 14px 6px',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 11.5,
          color: 'var(--sub)',
          marginBottom: 3,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}
      >
        <button type="button" className="btn-hud active" onClick={onTogglePlay}>
          {playing ? <Pause size={11} /> : <Play size={11} />}
          {playing ? t.timeline.pause : t.timeline.play}
        </button>
        <button type="button" className="btn-hud num" onClick={onCycleSpeed}>
          {speed}×
        </button>
        <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', marginLeft: 4, overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0, flex: '0 1 auto' }}>
          {lang === 'zh' ? '受益区租金指数，三个世界' : 'Treated-zone rent index, three worlds'}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginLeft: 'auto', fontSize: 11, minWidth: 0, overflow: 'hidden', flex: '0 1 auto' }}>
          {(['P', 'S', 'N'] as Scenario[]).map((sc) => (
            <span key={sc} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: sc === scenario ? 'var(--text)' : 'var(--sub)' }}>
              <svg width={14} height={6}>
                <line x1={0} x2={14} y1={3} y2={3} stroke={SC_COLORS[sc]} strokeWidth={sc === scenario ? 2.2 : 1.3} strokeDasharray={sc === 'S' ? '4 2' : undefined} />
              </svg>
              <span className="num" style={{ color: SC_COLORS[sc] }}>{sc}</span>
              <span>{t.scenarios[sc].short}</span>
            </span>
          ))}
          <span className="sep" />
          <span style={{ color: 'var(--sub)', opacity: 0.78, fontSize: 10.5 }}>{t.timeline.ciNote}</span>
        </span>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 84, cursor: 'pointer', display: 'block' }}
        onPointerDown={(e) => {
          draggingRef.current = true;
          (e.currentTarget as Element).setPointerCapture(e.pointerId);
          jumpFromClientX(e.clientX);
        }}
        onPointerMove={(e) => {
          if (draggingRef.current) jumpFromClientX(e.clientX);
        }}
        onPointerUp={() => {
          draggingRef.current = false;
        }}
      >
        {/* Phase background shading (v1 vibrant warmth) */}
        <rect
          x={xOf(announceMonth)}
          y={4}
          width={xOf(openMonth) - xOf(announceMonth)}
          height={58}
          fill="var(--p)"
          fillOpacity={0.075}
        />
        <rect
          x={xOf(openMonth)}
          y={4}
          width={xOf(36) - xOf(openMonth)}
          height={58}
          fill="var(--announce)"
          fillOpacity={0.055}
        />

        {/* Cross-seed 95% CI ribbons + curves */}
        {(['N', 'S', 'P'] as Scenario[]).map((sc) => {
          const active = sc === scenario;
          return (
            <g key={sc}>
              {ciBands[sc] && (
                <path d={ciBands[sc]} fill={SC_COLORS[sc]} fillOpacity={active ? 0.16 : 0.055} />
              )}
              <path
                d={curves[sc]}
                fill="none"
                stroke={SC_COLORS[sc]}
                strokeWidth={active ? 2.4 : sc === 'N' ? 1.1 : 1.5}
                strokeOpacity={active ? 1 : 0.48}
                strokeDasharray={sc === 'S' ? '5 3' : undefined}
              />
            </g>
          );
        })}

        {/* Baseline & lively icon chapter ticks */}
        <line x1={xOf(1)} x2={xOf(36)} y1={63} y2={63} stroke="var(--line)" strokeWidth={0.9} />
        {ticks.map(([m, label, col]) => (
          <g key={m}>
            <line x1={xOf(m)} x2={xOf(m)} y1={60} y2={66} stroke="var(--tick)" strokeWidth={0.9} />
            <text x={xOf(m)} y={80} textAnchor="middle" fontSize={10.5} fill={col} fontFamily="var(--font-sans)">
              {label}
            </text>
          </g>
        ))}

        {/* Playhead */}
        <line x1={xOf(month)} x2={xOf(month)} y1={2} y2={64} stroke="var(--text-strong)" strokeWidth={1.2} strokeOpacity={0.82} />
        <circle cx={xOf(month)} cy={yOf(curVal)} r={4.3} fill="var(--panel-solid)" stroke={SC_COLORS[scenario]} strokeWidth={2.2} />
      </svg>
    </div>
  );
}
