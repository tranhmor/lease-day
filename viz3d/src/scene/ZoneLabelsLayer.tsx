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
        const arrow = delta > 0.05 ? '↑' : delta < -0.05 ? '↓' : '';
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
                  fontSize: z.treated ? 13 : isCBD ? 12.5 : 11,
                  fontWeight: z.treated || isCBD ? 600 : 500,
                  color: z.treated ? '#FFD27D' : '#E3EEFF',
                  textShadow: '0 1px 6px rgba(10,16,28,0.95), 0 0 12px rgba(10,16,28,0.85)',
                  letterSpacing: '0.04em',
                }}
              >
                {label}
              </span>
              {(z.treated || isCBD || Math.abs(delta) >= 0.8) && (
                <span
                  className="mono"
                  style={{
                    fontSize: 10,
                    color: delta > 0.05 ? '#FF9D7E' : delta < -0.05 ? '#7FE0B0' : '#A9BDD8',
                    textShadow: '0 1px 5px rgba(10,16,28,0.98)',
                    marginTop: 1,
                  }}
                >
                  {sign}
                  {delta.toFixed(1)} {arrow}
                </span>
              )}
            </div>
          </Html>
        );
      })}
    </group>
  );
}
