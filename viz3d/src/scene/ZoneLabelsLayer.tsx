import { Html } from '@react-three/drei';
import type { Lang, ZoneInfo } from '@/types/viz';

interface ZoneLabelsLayerProps {
  zones: ZoneInfo[];
  zoneStats: Record<string, { rentDeltaPts: number; rentIndex: number }>;
  lang: Lang;
  visible: boolean;
  isolateTreated?: boolean;
  onSelectZone?: (zoneId: string) => void;
}

/**
 * L10: Minimalist floating typography matching reference ("科技园 63.3万↓") — zero heavy boxes or thick pins!
 */
export function ZoneLabelsLayer({
  zones,
  zoneStats,
  lang,
  visible,
  isolateTreated = false,
  onSelectZone,
}: ZoneLabelsLayerProps) {
  if (!visible) return null;

  return (
    <group name="L10_zone_labels">
      {zones.map((z) => {
        if (!z.treated && !z.major && z.id !== 'Z01') return null;
        if (isolateTreated && !z.treated && z.id !== 'Z00') return null;

        const st = zoneStats[z.id];
        const delta = st ? st.rentDeltaPts : 0;
        const sign = delta >= 0 ? '+' : '';
                const label = lang === 'zh' ? z.name : z.name_en;
        const isCBD = z.id === 'Z00';

        return (
          <Html
            key={z.id}
            position={[z.x, 0.45, z.z - 0.65]}
            center
            distanceFactor={undefined}
            zIndexRange={[4, 0]}
          >
            <div
              onClick={(e) => {
                e.stopPropagation();
                onSelectZone?.(z.id);
              }}
              style={{
                pointerEvents: 'auto',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                transform: 'translateY(-100%)',
                opacity: z.treated || isCBD ? 0.96 : 0.72,
              }}
            >
              <span
                style={{
                  fontSize: z.treated ? 14 : isCBD ? 13 : 12,
                  fontWeight: z.treated ? 600 : 400,
                  color: z.treated ? 'var(--text-strong)' : 'var(--text-soft)',
                  textShadow: '0 0 3px var(--bg), 0 0 6px var(--bg), 0 0 10px var(--bg)',
                  fontFamily: z.treated ? 'var(--font-serif)' : 'var(--font-sans)',
                }}
              >
                {label}
              </span>
              {(z.treated || isCBD || Math.abs(delta) >= 0.8) && (
                <span
                  className="num"
                  style={{
                    fontSize: 11,
                    color: z.treated && delta > 0.05 ? 'var(--accent)' : 'var(--sub)',
                    textShadow: '0 0 3px var(--bg), 0 0 6px var(--bg), 0 0 10px var(--bg)',
                    marginTop: 1,
                  }}
                >
                  {sign}
                  {delta.toFixed(1)}
                </span>
              )}
            </div>
          </Html>
        );
      })}
    </group>
  );
}
