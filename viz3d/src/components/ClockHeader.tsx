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

  return (
    <div
      style={{
        pointerEvents: 'none',
        padding: '6px 10px 8px 4px',
        background: 'radial-gradient(ellipse at 20% 40%, rgba(11,17,28,0.82) 0%, rgba(11,17,28,0) 78%)',
        borderRadius: 6,
      }}
    >
      <div style={{ fontSize: 10.5, letterSpacing: '0.2em', color: 'var(--cool)', fontWeight: 600 }}>
        {t.cityTag}{' '}
        <span style={{ color: 'var(--sub)', letterSpacing: '0.05em', fontWeight: 400 }}>
          · {t.subtitle}
        </span>
      </div>
      <div
        className="mono"
        style={{
          fontSize: compact ? 48 : 'clamp(50px, 4.4vw, 74px)',
          fontWeight: 200,
          lineHeight: 1.02,
          letterSpacing: '-0.03em',
          marginTop: 2,
          textShadow: '0 4px 24px rgba(11, 17, 28, 0.92)',
        }}
      >
        M{String(month).padStart(2, '0')}
        <small style={{ fontSize: compact ? 18 : 22, color: 'var(--sub)', marginLeft: 5, fontWeight: 300 }}>
          /{meta.months}
        </small>
      </div>
      <div
        style={{
          fontSize: 13.5,
          fontWeight: 500,
          marginTop: 2,
          color: month >= ann && scenario === 'P' ? 'var(--announce)' : 'var(--text)',
        }}
      >
        <span style={{ color: 'var(--sub)', marginRight: 6 }}>—</span>
        {t.phases[phaseKey]}
      </div>
      {!compact && (
        <div
          style={{
            fontSize: 11.5,
            color: '#9EB0CC',
            marginTop: 5,
            lineHeight: 1.48,
            textShadow: '0 1px 8px rgba(11,17,28,0.95)',
          }}
        >
          {t.stories[storyKey]}
        </div>
      )}
    </div>
  );
}
