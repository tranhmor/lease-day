import { useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame, ThreeEvent } from '@react-three/fiber';
import type { RoomMonthState, RoomStatic } from '@/types/viz';
import { rentDeltaToColor } from '@/data/geo';
import { useScenePalette } from '@/theme';

interface RoomBarsLayerProps {
  rooms: RoomStatic[];
  states: RoomMonthState[];
  diffStatesS?: RoomMonthState[] | null;
  diffMode?: boolean;
  visible: boolean;
  isolateTreated?: boolean;
  highlightZone?: string | null;
  selectedRoomId?: number | null;
  highlightVacant?: boolean;
  onSelectRoom?: (roomId: number) => void;
  onHoverRoom?: (roomId: number | null) => void;
}


/**
 * 240 room bars (alternative to discs), one per simulated room (positions inside a zone are schematic).
 * - Height = kind-normalized rent (diff mode: |P - S| in index points)
 * - Colour = rent change vs M1 on a diverging ramp (diff mode: sign of P - S)
 * - Vacant room = flat dark stub with a hairline ring
 */
export function RoomBarsLayer({
  rooms,
  states,
  diffStatesS = null,
  diffMode = false,
  visible,
  isolateTreated = false,
  highlightZone = null,
  selectedRoomId = null,
  highlightVacant = false,
  onSelectRoom,
  onHoverRoom,
}: RoomBarsLayerProps) {
  const [hoveredRoom, setHoveredRoom] = useState<number | null>(null);

  const coreRef = useRef<THREE.InstancedMesh>(null);
  const ringRef = useRef<THREE.InstancedMesh>(null);

  const curScales = useRef<Float32Array>(new Float32Array(240).fill(0.3));
  const curColors = useRef<THREE.Color[]>(Array.from({ length: 240 }, () => new THREE.Color('#8A8F98')));

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpColor = useMemo(() => new THREE.Color(), []);

  const { pillarGeo, outlineRingGeo } = useMemo(() => {
    const pillar = new THREE.BoxGeometry(1, 1, 1);
    pillar.translate(0, 0.5, 0);
    const ring = new THREE.RingGeometry(0.9, 1.0, 24);
    ring.rotateX(-Math.PI / 2);
    return { pillarGeo: pillar, outlineRingGeo: ring };
  }, []);

  const pal = useScenePalette();
  const { VACANT_COL, VACANT_RING_COL, DIM_COL, NEUTRAL_COL, ACCENT_COL, SEL_COL } = useMemo(
    () => ({
      VACANT_COL: new THREE.Color(pal.room.vacant),
      VACANT_RING_COL: new THREE.Color(pal.room.vacantRing),
      DIM_COL: new THREE.Color(pal.room.dim),
      NEUTRAL_COL: new THREE.Color(pal.rent.zero),
      ACCENT_COL: new THREE.Color(pal.room.alert),
      SEL_COL: new THREE.Color(pal.room.selected),
    }),
    [pal]
  );

  useFrame((_, delta) => {
    if (!visible) return;
    const damp = 1 - Math.exp(-delta * 6.5);
    const coreMesh = coreRef.current;
    const ringMesh = ringRef.current;
    if (!coreMesh || !ringMesh) return;

    for (let i = 0; i < rooms.length; i++) {
      const room = rooms[i];
      const st = states[i];
      const isTreated = room.zone === 'Z05' || room.zone === 'Z11';
      const isDimmed = (isolateTreated && !isTreated) || (highlightZone !== null && room.zone !== highlightZone);
      const isSelected = selectedRoomId === room.id;
      const isHovered = hoveredRoom === room.id;

      let targetH = 0.4;
      let isVac = !st || !st.occupied;

      if (diffMode && diffStatesS && diffStatesS[i]) {
        const sRent = diffStatesS[i].rent || room.start_rent;
        const diffPts = room.start_rent > 0 ? ((st.rent - sRent) / room.start_rent) * 100 : 0;
        targetH = 0.06 + Math.min(2.4, Math.abs(diffPts) * 0.45);
        if (Math.abs(diffPts) < 0.25) tmpColor.copy(NEUTRAL_COL);
        else rentDeltaToColor(diffPts > 0 ? 3 : -3, tmpColor);
        isVac = false;
      } else if (isVac) {
        targetH = 0.04;
        tmpColor.copy(highlightVacant ? ACCENT_COL : VACANT_COL);
      } else {
        const [lo, hi] = room.kind_rent_range;
        const norm = Math.max(0.05, Math.min(1.15, (st.rent - lo) / Math.max(hi - lo, 100)));
        const deltaPts = room.start_rent > 0 ? ((st.rent / room.start_rent) - 1) * 100 : 0;
        targetH = 0.25 + norm * 1.6;
        rentDeltaToColor(deltaPts, tmpColor);
      }

      if (isDimmed) {
        tmpColor.lerp(DIM_COL, 0.75);
      }
      if (isSelected || isHovered) {
        tmpColor.lerp(SEL_COL, 0.5);
      }

      curScales.current[i] += (targetH - curScales.current[i]) * damp;
      curColors.current[i].lerp(tmpColor, damp);

      const [rx, rz] = room.layout_xy;
      const h = curScales.current[i];
      const w = room.kind === '整租' ? 0.2 : 0.15;

      dummy.position.set(rx, 0, rz);
      dummy.scale.set(w, h, w);
      dummy.updateMatrix();
      coreMesh.setMatrixAt(i, dummy.matrix);
      coreMesh.setColorAt(i, curColors.current[i]);

      const showRing = isSelected || isHovered || isVac;
      dummy.position.set(rx, 0.02, rz);
      const ringScale = showRing ? (isSelected ? 0.34 : 0.16) : 0.001;
      dummy.scale.set(ringScale, 1, ringScale);
      dummy.updateMatrix();
      ringMesh.setMatrixAt(i, dummy.matrix);
      if (isSelected || isHovered) {
        tmpColor.copy(SEL_COL);
      } else {
        tmpColor.copy(highlightVacant ? ACCENT_COL : VACANT_RING_COL);
        if (isDimmed) tmpColor.lerp(DIM_COL, 0.6);
      }
      ringMesh.setColorAt(i, tmpColor);
    }

    coreMesh.instanceMatrix.needsUpdate = true;
    if (coreMesh.instanceColor) coreMesh.instanceColor.needsUpdate = true;
    ringMesh.instanceMatrix.needsUpdate = true;
    if (ringMesh.instanceColor) ringMesh.instanceColor.needsUpdate = true;
  });

  const handlePointer = (type: 'click' | 'over' | 'out') => (e: ThreeEvent<PointerEvent | MouseEvent>) => {
    e.stopPropagation();
    if (type === 'out') {
      setHoveredRoom(null);
      onHoverRoom?.(null);
      document.body.style.cursor = 'auto';
      return;
    }
    const instId = e.instanceId;
    if (instId === undefined || !rooms[instId]) return;
    const roomId = rooms[instId].id;
    if (type === 'over') {
      setHoveredRoom(roomId);
      onHoverRoom?.(roomId);
      document.body.style.cursor = 'pointer';
    } else if (type === 'click') {
      onSelectRoom?.(roomId);
    }
  };

  if (!visible) return null;

  return (
    <group name="L5_room_pillars_240">
      <instancedMesh
        ref={coreRef}
        args={[pillarGeo, undefined, rooms.length]}
        onClick={handlePointer('click')}
        onPointerOver={handlePointer('over')}
        onPointerOut={handlePointer('out')}
      >
        <meshLambertMaterial />
      </instancedMesh>
      <instancedMesh ref={ringRef} args={[outlineRingGeo, undefined, rooms.length]}>
        <meshBasicMaterial transparent opacity={0.9} side={THREE.DoubleSide} depthWrite={false} />
      </instancedMesh>
    </group>
  );
}
