import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { DecisionRecord, RoomStatic } from '@/types/viz';

interface DecisionPulsesLayerProps {
  month: number;
  decisions: DecisionRecord[];
  rooms: RoomStatic[];
  visible: boolean;
  highlighted?: boolean;
}

const PULSE_DURATION = 1.4; // 1.4s pulse fade (§4.3)

/**
 * L9: Expanding glowing pulse rings over rooms with LLM decisions this month.
 * Normal decisions = cool (#5FB4FF); decisions mentioning East Express = announce (#FFB02E).
 */
export function DecisionPulsesLayer({ month, decisions, rooms, visible, highlighted = false }: DecisionPulsesLayerProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const startSecRef = useRef(performance.now() / 1000);

  const pulses = useMemo(() => {
    const out: Array<{ x: number; z: number; mentions: boolean; delay: number }> = [];
    const seen = new Set<number>();
    for (const d of decisions) {
      if (d.m !== month || d.agent_type !== 'landlord' || d.room_id === null) continue;
      if (seen.has(d.room_id)) continue;
      const room = rooms[d.room_id];
      if (!room) continue;
      seen.add(d.room_id);
      out.push({
        x: room.layout_xy[0],
        z: room.layout_xy[1],
        mentions: d.mentions_line,
        delay: (out.length % 8) * 0.11,
      });
    }
    return out;
  }, [month, decisions, rooms]);

  useEffect(() => {
    startSecRef.current = performance.now() / 1000;
  }, [month, decisions]);

  const ringGeo = useMemo(() => {
    const g = new THREE.RingGeometry(0.75, 1.0, 24);
    g.rotateX(-Math.PI / 2);
    return g;
  }, []);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpCol = useMemo(() => new THREE.Color(), []);

  useFrame(() => {
    const mesh = meshRef.current;
    if (!visible || !mesh || pulses.length === 0) return;
    const elapsed = performance.now() / 1000 - startSecRef.current;

    for (let i = 0; i < pulses.length; i++) {
      const p = pulses[i];
      // Repeating soft pulse cycle every 2.2s so pulses stay alive even when paused
      const cycle = ((elapsed - p.delay) % 2.2 + 2.2) % 2.2;
      const t = Math.min(1, cycle / PULSE_DURATION);
      const alive = cycle < PULSE_DURATION;
      const radius = 0.25 + t * (p.mentions ? 1.75 : 1.15);
      const fade = alive ? Math.pow(1 - t, 1.5) : 0;

      dummy.position.set(p.x, 0.12 + t * 0.15, p.z);
      dummy.scale.set(alive ? radius : 0.001, 1, alive ? radius : 0.001);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      tmpCol
        .set(p.mentions ? '#FFB02E' : '#5FB4FF')
        .multiplyScalar(fade * (p.mentions ? 2.2 : 1.4) * (highlighted ? 1.4 : 1.0));
      mesh.setColorAt(i, tmpCol);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  if (!visible || pulses.length === 0) return null;

  return (
    <instancedMesh ref={meshRef} name="L9_decision_pulses" args={[ringGeo, undefined, pulses.length]} frustumCulled={false}>
      <meshBasicMaterial
        transparent
        opacity={0.92}
        blending={THREE.AdditiveBlending}
        side={THREE.DoubleSide}
        depthWrite={false}
        toneMapped={false}
      />
    </instancedMesh>
  );
}
