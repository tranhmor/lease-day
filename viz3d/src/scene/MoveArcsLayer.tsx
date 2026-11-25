import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { IncomeGroup, RoomStatic, SimEvent } from '@/types/viz';

interface MoveArcsLayerProps {
  month: number;
  events: SimEvent[];
  rooms: RoomStatic[];
  visible: boolean;
  highlighted?: boolean;
}

const INCOME_COLORS: Record<IncomeGroup, string> = {
  low: '#2DD4BF',
  mid: '#A78BFA',
  high: '#F472B6',
};

const SEGMENTS = 28;
const ARC_DURATION = 1.35; // ~1.2-1.4s flight lifetime (§5.1)

/**
 * L8: Parabolic move-in arcs colored by income group (low/mid/high — distinct from N/S/P scenario colors).
 * Uses a single dynamic merged LineSegments geometry for minimal draw calls.
 */
export function MoveArcsLayer({ month, events, rooms, visible, highlighted = false }: MoveArcsLayerProps) {
  const birthRef = useRef<number>(performance.now() / 1000);
  const lineRef = useRef<THREE.LineSegments>(null);

  const monthMoves = useMemo(() => {
    const out: Array<{ from: [number, number]; to: [number, number]; group: IncomeGroup; height: number; delay: number }> = [];
    const filtered = events.filter((e) => e.m === month && e.type === 'move_in' && e.to_room !== null);
    filtered.forEach((e, idx) => {
      const dst = rooms[e.to_room!];
      if (!dst) return;
      let fromXZ: [number, number];
      if (e.from_room !== null && rooms[e.from_room]) {
        fromXZ = rooms[e.from_room].layout_xy;
      } else {
        // Newcomer arriving from outer Beijing ring near destination angle
        const ang = Math.atan2(dst.layout_xy[1], dst.layout_xy[0]) + (idx % 3 - 1) * 0.22;
        fromXZ = [Math.cos(ang) * 26, Math.sin(ang) * 26];
      }
      const dist = Math.hypot(dst.layout_xy[0] - fromXZ[0], dst.layout_xy[1] - fromXZ[1]);
      out.push({
        from: fromXZ,
        to: dst.layout_xy,
        group: e.income_group,
        height: Math.min(8.5, Math.max(2.2, dist * 0.28)),
        delay: (idx % 6) * 0.08,
      });
    });
    return out;
  }, [month, events, rooms]);

  useEffect(() => {
    birthRef.current = performance.now() / 1000;
  }, [month, events]);

  const { geometry, posArr, colArr } = useMemo(() => {
    const maxSegs = Math.max(1, monthMoves.length) * SEGMENTS;
    const pArr = new Float32Array(maxSegs * 6);
    const cArr = new Float32Array(maxSegs * 6);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pArr, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(cArr, 3));
    return { geometry: geo, posArr: pArr, colArr: cArr };
  }, [monthMoves]);

  const tmpCol = useMemo(() => new THREE.Color(), []);

  useFrame(() => {
    if (!visible || !lineRef.current || monthMoves.length === 0) return;
    const age = performance.now() / 1000 - birthRef.current;

    let ptr = 0;
    for (const arc of monthMoves) {
      const localT = (age - arc.delay) / ARC_DURATION;
      // Keep gentle glowing trail visible if paused or during playback; loop softly after 1.6s when viewing static month
      const progress = localT <= 1.25 ? Math.max(0, Math.min(1.25, localT)) : 0.85;
      const head = Math.min(1, progress);
      const tail = Math.max(0, progress - 0.55);
      const fade = localT > 1.25 ? (highlighted ? 0.8 : 0.45) : 1.0 - Math.max(0, (progress - 0.95) / 0.35) * 0.5;

      tmpCol.set(INCOME_COLORS[arc.group]).multiplyScalar(highlighted ? 1.6 : 1.25);

      for (let s = 0; s < SEGMENTS; s++) {
        const t0 = s / SEGMENTS;
        const t1 = (s + 1) / SEGMENTS;
        const inSpan = t1 >= tail && t0 <= head;

        if (!inSpan) {
          posArr[ptr] = posArr[ptr + 1] = posArr[ptr + 2] = 0;
          posArr[ptr + 3] = posArr[ptr + 4] = posArr[ptr + 5] = 0;
          colArr[ptr] = colArr[ptr + 1] = colArr[ptr + 2] = 0;
          colArr[ptr + 3] = colArr[ptr + 4] = colArr[ptr + 5] = 0;
          ptr += 6;
          continue;
        }

        const evalPt = (t: number): [number, number, number] => {
          const x = arc.from[0] + (arc.to[0] - arc.from[0]) * t;
          const z = arc.from[1] + (arc.to[1] - arc.from[1]) * t;
          const y = 0.25 + 4 * arc.height * t * (1 - t);
          return [x, y, z];
        };

        const [x0, y0, z0] = evalPt(t0);
        const [x1, y1, z1] = evalPt(t1);
        const segBright = fade * (0.3 + 0.7 * ((t1 - tail) / Math.max(0.05, head - tail)));

        posArr[ptr] = x0;
        posArr[ptr + 1] = y0;
        posArr[ptr + 2] = z0;
        posArr[ptr + 3] = x1;
        posArr[ptr + 4] = y1;
        posArr[ptr + 5] = z1;

        colArr[ptr] = tmpCol.r * segBright;
        colArr[ptr + 1] = tmpCol.g * segBright;
        colArr[ptr + 2] = tmpCol.b * segBright;
        colArr[ptr + 3] = tmpCol.r * segBright;
        colArr[ptr + 4] = tmpCol.g * segBright;
        colArr[ptr + 5] = tmpCol.b * segBright;
        ptr += 6;
      }
    }

    (geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
    (geometry.getAttribute('color') as THREE.BufferAttribute).needsUpdate = true;
  });

  if (!visible || monthMoves.length === 0) return null;

  return (
    <lineSegments ref={lineRef} name="L8_move_arcs" geometry={geometry} frustumCulled={false}>
      <lineBasicMaterial
        vertexColors
        transparent
        opacity={0.9}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        toneMapped={false}
      />
    </lineSegments>
  );
}
