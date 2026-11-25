import type { Lang, Scenario, VizMeta } from '@/types/viz';
import { getDict } from '@/i18n';

interface ClockHeaderProps {
  month: number;
  scenario: Scenario;
  meta: VizMeta;
  lang: Lang;
  compact?: boolean;
}

export function ClockHeader({ month, scenario, meta, lang, compact = false }: ClockHeaderProps) {
  const t = getDict(lang);
  const ann = meta.event_months.announce;
  const open = meta.event_months.open;

  let phaseKey: keyof typeof t.phases = 'warmup';
  let storyKey: keyof typeof t.stories = 'warmup';

  if (month < ann) {
    phaseKey = 'warmup';
    storyKey = 'warmup';
  } else if (month < open) {
    phaseKey = scenario === 'P' ? 'announce_P' : scenario === 'S' ? 'announce_S' : 'announce_N';
    storyKey = scenario === 'P' ? 'announce_P' : scenario === 'S' ? 'announce_S' : 'announce_N';
  } else {
    phaseKey = month === meta.months ? 'conclude' : scenario === 'P' ? 'open_P' : scenario === 'S' ? 'open_S' : 'open_N';
    storyKey = scenario === 'P' ? 'open_P' : scenario === 'S' ? 'open_S' : 'open_N';
  }

  const accentPhase = month >= ann && scenario === 'P';

  return (
    <div
      className="hud-panel"
      style={{
        pointerEvents: 'none',
        padding: '14px 16px 14px',
      }}
    >
      <div className="kicker" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>{t.subtitle}</span>
        <span>{lang === 'zh' ? '北京' : 'Beijing'}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 6 }}>
        <span
          className="serif num"
          style={{
            fontSize: compact ? 44 : 'clamp(46px, 3.8vw, 64px)',
            fontWeight: 400,
            lineHeight: 1,
            letterSpacing: '-0.01em',
          }}
        >
          {lang === 'zh' ? `第 ${month} 月` : `Month ${month}`}
        </span>
        <span className="num" style={{ fontSize: 13, color: 'var(--sub)' }}>
          / {meta.months}
        </span>
      </div>
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          marginTop: 10,
          color: accentPhase ? 'var(--accent)' : 'var(--text)',
        }}
      >
        {t.phases[phaseKey]}
      </div>
      {!compact && (
        <div
          className="serif"
          style={{
            fontSize: 13.5,
            color: 'var(--text-soft)',
            marginTop: 4,
            lineHeight: 1.6,
          }}
        >
          {t.stories[storyKey]}
        </div>
      )}
    </div>
  );
}
