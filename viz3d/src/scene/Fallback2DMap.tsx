import { useMemo } from 'react';
import type { Lang, LayerToggles, Scenario, VizDataset } from '@/types/viz';
import { computeZoneStats, readMonthRoomStates } from '@/data/loader';
import { LocalProjector, rentDeltaToHex } from '@/data/geo';

interface Fallback2DMapProps {
  dataset: VizDataset;
  scenario: Scenario;
  seed: number;
  month: number;
  layers: LayerToggles;
  lang: Lang;
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  onSelectZone: (zoneId: string) => void;
}

/**
 * Quality Tier 2 (§8.3): Zero-WebGL 2D top-down SVG fallback matching concept-v1.html.
 */
export function Fallback2DMap({
  dataset,
  scenario,
  seed,
  month,
  layers,
  lang,
  selectedRoomId,
  onSelectRoom,
  onSelectZone,
}: Fallback2DMapProps) {
  const proj = useMemo(() => new LocalProjector(dataset.meta.projection), [dataset.meta.projection]);
  const run = dataset.runs[`${scenario}_${seed}`] ?? dataset.runs[`P_${dataset.meta.default_seed}`];
  const states = useMemo(
    () => readMonthRoomStates(run.roomStatesBuffer, month, dataset.rooms.length),
    [run, month, dataset.rooms.length]
  );
  const zoneStats = useMemo(() => computeZoneStats(dataset.rooms, states), [dataset.rooms, states]);

  // Convert local km XZ to SVG viewBox (-28..26, -34..24)
  const metroPaths = useMemo(() => {
    const out: string[] = [];
    for (const f of dataset.metro.features) {
      if (f.properties?.feature_kind !== 'line' || f.geometry?.type !== 'LineString') continue;
      const pts = (f.geometry.coordinates as [number, number][]).map(([lon, lat]) => proj.lonLatToXZ(lon, lat));
      if (pts.length >= 2) {
        out.push('M' + pts.map(([x, z]) => `${x.toFixed(2)},${z.toFixed(2)}`).join('L'));
      }
    }
    return out;
  }, [dataset.metro, proj]);

  const newlinePath = useMemo(() => {
    for (const f of dataset.newline.features) {
      if (f.properties?.feature_kind === 'line' && f.geometry?.type === 'LineString') {
        const pts = (f.geometry.coordinates as [number, number][]).map(([lon, lat]) => proj.lonLatToXZ(lon, lat));
        return 'M' + pts.map(([x, z]) => `${x.toFixed(2)},${z.toFixed(2)}`).join('L');
      }
    }
    return '';
  }, [dataset.newline, proj]);

  const announced = scenario === 'P' && month >= dataset.meta.event_months.announce;
  const opened = scenario !== 'N' && month >= dataset.meta.event_months.open;

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg
        viewBox="-26 -28 52 52"
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', maxWidth: '100%', maxHeight: '100%' }}
      >
        {/* Concentric CBD distance rings */}
        {[5, 10, 15, 20, 25].map((r) => (
          <circle key={r} cx={0} cy={0} r={r} fill="none" stroke="#5FB4FF" strokeOpacity={0.08} strokeWidth={0.12} />
        ))}

        {/* Metro lines */}
        {layers.metro &&
          metroPaths.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="#5FB4FF" strokeOpacity={0.35} strokeWidth={0.18} />
          ))}

        {/* East Express Line */}
        {layers.newline && (announced || opened) && newlinePath && (
          <path
            d={newlinePath}
            fill="none"
            stroke="#FFB02E"
            strokeWidth={opened ? 0.36 : 0.28}
            strokeDasharray={opened ? undefined : '0.6 0.5'}
          />
        )}

        {/* Treated zone halos */}
        {dataset.zones
          .filter((z) => z.treated)
          .map((z) => (
            <circle
              key={`h_${z.id}`}
              cx={z.x}
              cy={z.z}
              r={3.2}
              fill="#FFB02E"
              fillOpacity={announced || opened ? 0.14 : 0.04}
              stroke="#FFB02E"
              strokeOpacity={0.35}
              strokeWidth={0.1}
            />
          ))}

        {/* 240 Room Dots */}
        {layers.rooms &&
          dataset.rooms.map((r, i) => {
            const st = states[i];
            const delta = r.start_rent > 0 ? ((st.rent / r.start_rent) - 1) * 100 : 0;
            const fill = st.occupied ? rentDeltaToHex(delta) : '#23324D';
            const isSel = selectedRoomId === r.id;
            return (
              <circle
                key={r.id}
                cx={r.layout_xy[0]}
                cy={r.layout_xy[1]}
                r={isSel ? 0.38 : r.zone === 'Z05' || r.zone === 'Z11' ? 0.24 : 0.18}
                fill={fill}
                stroke={isSel ? '#FFB02E' : '#0B111C'}
                strokeWidth={isSel ? 0.12 : 0.04}
                style={{ cursor: 'pointer' }}
                onClick={() => onSelectRoom(r.id)}
              />
            );
          })}

        {/* Zone Labels */}
        {dataset.zones
          .filter((z) => z.treated || z.major)
          .map((z) => {
            const st = zoneStats[z.id];
            const delta = st ? st.rentDeltaPts : 0;
            return (
              <g key={`l_${z.id}`} style={{ cursor: 'pointer' }} onClick={() => onSelectZone(z.id)}>
                <text
                  x={z.x}
                  y={z.z - z.radius - 0.5}
                  textAnchor="middle"
                  fill={z.treated ? '#FFB02E' : '#CFD9EA'}
                  fontSize={z.treated ? 1.15 : 0.85}
                  fontWeight={z.treated ? 700 : 500}
                >
                  {lang === 'zh' ? z.name : z.name_en}
                </text>
                {z.treated && (
                  <text
                    x={z.x}
                    y={z.z - z.radius + 0.65}
                    textAnchor="middle"
                    fill="#FFD588"
                    fontSize={0.78}
                    fontFamily="monospace"
                  >
                    {delta >= 0 ? '+' : ''}
                    {delta.toFixed(1)}
                  </text>
                )}
              </g>
            );
          })}
      </svg>
    </div>
  );
}
