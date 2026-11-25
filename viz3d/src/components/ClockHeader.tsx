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
      style={{
        pointerEvents: 'none',
        padding: '6px 12px 10px 4px',
        background: 'radial-gradient(ellipse at 20% 40%, var(--clock-veil) 0%, var(--clock-veil-0) 78%)',
        borderRadius: 6,
      }}
    >
      {/* Clean hairline-separated kicker row (zero middots!) */}
      <div className="meta-row" style={{ gap: 8, fontSize: 11, lineHeight: 1.2 }}>
        <span style={{ letterSpacing: '0.2em', color: 'var(--cool)', fontWeight: 600 }}>{t.cityTag}</span>
        <span className="sep" />
        <span className="serif" style={{ color: 'var(--text-soft)', fontWeight: 600, fontSize: 12 }}>
          {t.projectTag}
        </span>
        <span className="sep" />
        <span className="num" style={{ color: 'var(--sub)', fontSize: 10.5 }}>
          {t.scaleTag}
        </span>
      </div>

      {/* Sleek ultra-light hero clock */}
      <div
        className="num-clock"
        style={{
          fontSize: compact ? 50 : 'clamp(56px, 4.8vw, 78px)',
          fontWeight: 200,
          lineHeight: 1.0,
          letterSpacing: '-0.025em',
          marginTop: 6,
          color: 'var(--text)',
          textShadow: 'var(--clock-shadow)',
        }}
      >
        M{String(month).padStart(2, '0')}
        <small style={{ fontSize: compact ? 18 : 21, color: 'var(--faint)', marginLeft: 4, fontWeight: 200 }}>
          /{meta.months}
        </small>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 13.5,
          fontWeight: 600,
          letterSpacing: '0.02em',
          marginTop: 7,
          color: accentPhase ? 'var(--announce)' : 'var(--text)',
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: 14,
            height: 1.5,
            background: accentPhase ? 'var(--announce)' : 'var(--cool)',
            opacity: 0.85,
          }}
        />
        {t.phases[phaseKey]}
      </div>

      {!compact && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--story)',
            marginTop: 7,
            lineHeight: 1.6,
            maxWidth: 316,
            textShadow: 'var(--clock-shadow)',
          }}
        >
          {t.stories[storyKey]}
        </div>
      )}
    </div>
  );
}
