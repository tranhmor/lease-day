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
        padding: '10px 14px',
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
              gridTemplateColumns: '16px 1fr 56px 50px',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              padding: '5px 4px',
              borderRadius: 3,
              cursor: 'pointer',
              background: isSel ? 'color-mix(in srgb, var(--cool) 14%, transparent)' : 'transparent',
              transition: 'background 0.15s',
            }}
          >
            <span className="mono" style={{ fontSize: 10, color: 'var(--sub)' }}>
              {idx + 1}
            </span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ color: zone.treated ? 'var(--announce)' : 'var(--text)', fontWeight: zone.treated ? 600 : 400 }}>
                  {lang === 'zh' ? zone.name : zone.name_en}
                </span>
                {zone.treated && (
                  <span
                    style={{
                      fontSize: 9,
                      padding: '0 4px',
                      borderRadius: 2,
                      background: 'color-mix(in srgb, var(--announce) 16%, transparent)',
                      color: 'var(--announce)',
                      border: '1px solid color-mix(in srgb, var(--announce) 40%, transparent)',
                    }}
                  >
                    {t.rank.treatedTag}
                  </span>
                )}
              </div>
              <div
                style={{
                  height: 3,
                  borderRadius: 2,
                  marginTop: 4,
                  width: `${pct}%`,
                  background: zone.treated
                    ? 'linear-gradient(90deg, var(--p), var(--announce))'
                    : 'linear-gradient(90deg, var(--rank-from), var(--cool))',
                  transition: 'width 0.35s ease',
                }}
              />
            </div>
            <span className="mono" style={{ textAlign: 'right', fontSize: 11, color: 'var(--text)' }}>
              {index.toFixed(1)}
            </span>
            <span
              className="mono"
              style={{
                textAlign: 'right',
                fontSize: 11,
                color: delta >= 0 ? 'var(--up)' : 'var(--down)',
              }}
            >
              {delta >= 0 ? '+' : ''}
              {delta.toFixed(1)}
            </span>
          </div>
        );
      })}
      <div style={{ fontSize: 10, color: 'var(--sub)', marginTop: 4, opacity: 0.78 }}>{t.rank.clickTip}</div>
    </div>
  );
}
