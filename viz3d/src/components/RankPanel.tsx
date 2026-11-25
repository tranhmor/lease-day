import type { Lang, ZoneInfo } from '@/types/viz';
import { getDict } from '@/i18n';

interface RankPanelProps {
  zones: ZoneInfo[];
  zoneStats: Record<string, { rentDeltaPts: number; rentIndex: number }>;
  selectedZone: string | null;
  lang: Lang;
  onSelectZone: (zoneId: string | null) => void;
}

export function RankPanel({ zones, zoneStats, selectedZone, lang, onSelectZone }: RankPanelProps) {
  const t = getDict(lang);

  const ranked = zones
    .map((z) => ({
      zone: z,
      delta: zoneStats[z.id]?.rentDeltaPts ?? 0,
      index: zoneStats[z.id]?.rentIndex ?? 100,
    }))
    .sort((a, b) => b.delta - a.delta)
    .slice(0, 6);

  const maxAbs = Math.max(1.5, ...ranked.map((r) => Math.abs(r.delta)));

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        padding: '14px 16px 12px',
        flexShrink: 0,
      }}
    >
      <div className="panel-header" style={{ marginBottom: 8 }}>
        <span>{t.rank.title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {selectedZone && (
            <button
              type="button"
              className="btn-hud"
              style={{ padding: '1px 6px', fontSize: 10 }}
              onClick={() => onSelectZone(null)}
            >
              {t.rank.clearFilter}
            </button>
          )}
          <small>{t.rank.subtitle}</small>
        </div>
      </div>

      {ranked.map(({ zone, delta, index }, idx) => {
        const isSel = selectedZone === zone.id;
        const pct = Math.max(6, Math.min(100, (Math.max(0, delta) / maxAbs) * 100));
        return (
          <div
            key={zone.id}
            onClick={() => onSelectZone(isSel ? null : zone.id)}
            style={{
              display: 'grid',
              gridTemplateColumns: '14px 1fr 48px 40px',
              alignItems: 'center',
              gap: 8,
              fontSize: 12.5,
              padding: '5px 0',
              cursor: 'pointer',
              background: isSel ? 'var(--inset)' : 'transparent',
              transition: 'background 0.15s',
            }}
          >
            <span className="num" style={{ fontSize: 11, color: 'var(--faint)' }}>
              {idx + 1}
            </span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ color: 'var(--text)', fontWeight: zone.treated ? 600 : 400 }}>
                  {lang === 'zh' ? zone.name : zone.name_en}
                </span>
                {zone.treated && (
                  <span style={{ fontSize: 10.5, color: 'var(--accent)' }}>
                    {t.rank.treatedTag}
                  </span>
                )}
              </div>
              <div
                style={{
                  height: 2,
                  marginTop: 5,
                  width: `${pct}%`,
                  background: zone.treated ? 'var(--accent)' : 'var(--tick)',
                  transition: 'width 0.35s ease',
                }}
              />
            </div>
            <span className="num" style={{ textAlign: 'right', fontSize: 12, color: 'var(--sub)' }}>
              {index.toFixed(1)}
            </span>
            <span
              className="num"
              style={{
                textAlign: 'right',
                fontSize: 12,
                fontWeight: 500,
                color: 'var(--text)',
              }}
            >
              {delta >= 0 ? '+' : ''}
              {delta.toFixed(1)}
            </span>
          </div>
        );
      })}
      <div style={{ fontSize: 11, color: 'var(--faint)', marginTop: 6 }}>{t.rank.clickTip}</div>
    </div>
  );
}
