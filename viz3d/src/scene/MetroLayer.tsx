import { useMemo } from 'react';
import * as THREE from 'three';
import type { GeoJSONCollection, ProjectionMeta } from '@/types/viz';
import { LocalProjector } from '@/data/geo';

interface MetroLayerProps {
  metro: GeoJSONCollection;
  projection: ProjectionMeta;
  visible: boolean;
  highlighted?: boolean;
  dimmed?: boolean;
}

/**
 * L3: existing Beijing metro lines as thin flat ribbons (1 draw call).
 */
export function MetroLayer({ metro, projection, visible, highlighted = false, dimmed = false }: MetroLayerProps) {
  const ribbonGeo = useMemo(() => {
    const proj = new LocalProjector(projection);
    const ribbonPos: number[] = [];
    const ribbonIdx: number[] = [];
    const Y = 0.05;
    const HALF_W = 0.03;
    let vOff = 0;

    for (const f of metro.features) {
      if (f.properties?.feature_kind !== 'line' || f.geometry?.type !== 'LineString') continue;
      const coords = f.geometry.coordinates as [number, number][];
      if (coords.length < 2) continue;
      const pts = coords.map(([lon, lat]) => proj.lonLatToXZ(lon, lat));

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        const prev = pts[Math.max(0, i - 1)];
        const next = pts[Math.min(pts.length - 1, i + 1)];
        let tx = next[0] - prev[0];
        let tz = next[1] - prev[1];
        const len = Math.hypot(tx, tz) || 1;
        tx /= len;
        tz /= len;
        const px = -tz * HALF_W;
        const pz = tx * HALF_W;
        ribbonPos.push(p[0] - px, Y, p[1] - pz, p[0] + px, Y, p[1] + pz);
        if (i < pts.length - 1) {
          const a = vOff + i * 2;
          ribbonIdx.push(a, a + 1, a + 3, a, a + 3, a + 2);
        }
      }
      vOff += pts.length * 2;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(ribbonPos, 3));
    geo.setIndex(ribbonIdx);
    return geo;
  }, [metro, projection]);

  if (!visible) return null;

  return (
    <group name="L3_metro">
      <mesh geometry={ribbonGeo}>
        <meshBasicMaterial
          color={highlighted ? '#A7ADB5' : '#5E636B'}
          transparent
          opacity={dimmed ? 0.3 : highlighted ? 0.9 : 0.7}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}
