import { useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useScenePalette } from '@/theme';
import { useFrame, ThreeEvent } from '@react-three/fiber';
import type { RoomMonthState, RoomStatic } from '@/types/viz';
import { rentDeltaToColor } from '@/data/geo';

interface RoomPillarsLayerProps {
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

const HALO_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    #ifdef USE_INSTANCING
      vec4 mvPos = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
    #else
      vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
    #endif
    gl_Position = projectionMatrix * mvPos;
  }
`;

const HALO_FRAG = /* glsl */ `
  uniform float uAlpha;
  varying vec2 vUv;
  #ifdef USE_INSTANCING_COLOR
    varying vec3 vInstanceColor;
  #endif
  void main() {
    vec2 p = vUv * 2.0 - 1.0;
    float r = length(p);
    if (r > 1.0) discard;
    float glow = exp(-r * r * 5.0);
    vec3 col = vec3(0.45, 0.75, 1.0);
    #ifdef USE_INSTANCING_COLOR
      col = vInstanceColor;
    #endif
    gl_FragColor = vec4(col, glow * uAlpha);
  }
`;



/**
 * 100% Honest Real-Data Room Layer (ZERO decorative fake dots, ZERO chunky cylinders).
 * Exactly 240 luminous ground starlight nodes corresponding 1:1 to the 240 simulated rooms.
 * - Size & halo = kind-normalized rent
 * - Color = diverging rent delta vs M1 (#5FB4FF -> #E8F3FF -> #FFB02E -> #FF5A3C)
 * - Hollow hairline ring = vacant room; outer rim = whole apartment
 */
export function RoomPillarsLayer({
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
}: RoomPillarsLayerProps) {
  const [hoveredRoom, setHoveredRoom] = useState<number | null>(null);

  const coreRef = useRef<THREE.InstancedMesh>(null);
  const haloRef = useRef<THREE.InstancedMesh>(null);
  const ringRef = useRef<THREE.InstancedMesh>(null);

  const curScales = useRef<Float32Array>(new Float32Array(240).fill(0.16));
  const curColors = useRef<THREE.Color[]>(Array.from({ length: 240 }, () => new THREE.Color('#DCEBFF')));

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpColor = useMemo(() => new THREE.Color(), []);

  const { discGeo, haloPlaneGeo, outlineRingGeo } = useMemo(() => {
    const disc = new THREE.CircleGeometry(1, 20);
    disc.rotateX(-Math.PI / 2);
    const halo = new THREE.PlaneGeometry(2, 2);
    halo.rotateX(-Math.PI / 2);
    const ring = new THREE.RingGeometry(0.82, 1.0, 24);
    ring.rotateX(-Math.PI / 2);
    return { discGeo: disc, haloPlaneGeo: halo, outlineRingGeo: ring };
  }, []);

  const haloMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: HALO_VERT,
        fragmentShader: HALO_FRAG,
        uniforms: { uAlpha: { value: 0.78 } },
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    []
  );

  const pal = useScenePalette();
  const VACANT_COL = useMemo(() => new THREE.Color(pal.room.vacant), [pal]);
  const DIM_COL = useMemo(() => new THREE.Color(pal.room.dim), [pal]);
  const NEUTRAL_COL = useMemo(() => new THREE.Color(pal.rent.neutralLerp), [pal]);
  const ALERT_COL = useMemo(() => new THREE.Color(pal.room.alert), [pal]);
  haloMaterial.blending = pal.glowBlending;
  haloMaterial.uniforms.uAlpha.value = pal.isLight ? 0.38 : 0.78;

  useFrame((_, delta) => {
    if (!visible) return;
    const B = pal.boost;
    const damp = 1 - Math.exp(-delta * 6.5);
    const coreMesh = coreRef.current;
    const haloMesh = haloRef.current;
    const ringMesh = ringRef.current;
    if (!coreMesh || !haloMesh || !ringMesh) return;

    for (let i = 0; i < rooms.length; i++) {
      const room = rooms[i];
      const st = states[i];
      const isTreated = room.zone === 'Z05' || room.zone === 'Z11';
      const isDimmed = (isolateTreated && !isTreated) || (highlightZone !== null && room.zone !== highlightZone);
      const isSelected = selectedRoomId === room.id;
      const isHovered = hoveredRoom === room.id;

      let targetRadius = 0.14;
      let isVac = !st || !st.occupied;

      if (diffMode && diffStatesS && diffStatesS[i]) {
        const sRent = diffStatesS[i].rent || room.start_rent;
        const diffPts = room.start_rent > 0 ? ((st.rent - sRent) / room.start_rent) * 100 : 0;
        targetRadius = 0.13 + Math.min(0.28, Math.abs(diffPts) * 0.058);
        rentDeltaToColor(diffPts * 1.15, tmpColor);
        if (Math.abs(diffPts) > 1.0) tmpColor.multiplyScalar(B(1.45));
        isVac = false;
      } else if (isVac) {
        targetRadius = highlightVacant ? 0.22 : 0.12;
        tmpColor.copy(highlightVacant ? ALERT_COL : VACANT_COL);
      } else {
        const [lo, hi] = room.kind_rent_range;
        const norm = Math.max(0.05, Math.min(1.15, (st.rent - lo) / Math.max(hi - lo, 100)));
        const deltaPts = room.start_rent > 0 ? ((st.rent / room.start_rent) - 1) * 100 : 0;
        targetRadius = 0.115 + norm * 0.12 + (isTreated ? 0.035 : 0);

        rentDeltaToColor(deltaPts, tmpColor);
        if (Math.abs(deltaPts) < 1.1) {
          tmpColor.lerp(NEUTRAL_COL, 0.45);
        }
        if (deltaPts > 1.5 && !isDimmed) {
          tmpColor.multiplyScalar(B(1.25 + Math.min(0.45, (deltaPts - 1.5) * 0.12)));
        } else if (isTreated && !isDimmed) {
          tmpColor.multiplyScalar(B(1.18));
        }
      }

      if (isDimmed) {
        targetRadius *= 0.65;
        tmpColor.lerp(DIM_COL, 0.8);
      }
      if (isSelected || isHovered) {
        targetRadius *= 1.48;
        if (pal.isLight) tmpColor.multiplyScalar(0.8);
        else tmpColor.multiplyScalar(1.55);
      }

      curScales.current[i] += (targetRadius - curScales.current[i]) * damp;
      curColors.current[i].lerp(tmpColor, damp);

      const [rx, rz] = room.layout_xy;
      const rVal = curScales.current[i];

      // 1. Crisp core dot
      dummy.position.set(rx, 0.09, rz);
      const coreScale = isVac && !highlightVacant ? rVal * 0.4 : rVal;
      dummy.scale.set(coreScale, 1, coreScale);
      dummy.updateMatrix();
      coreMesh.setMatrixAt(i, dummy.matrix);
      coreMesh.setColorAt(i, curColors.current[i]);

      // 2. Soft radiant bloom aura (also generous click hitbox)
      dummy.position.set(rx, 0.072, rz);
      const haloScale = isVac ? rVal * 1.4 : rVal * (isSelected ? 4.4 : isTreated ? 3.4 : 2.5);
      dummy.scale.set(haloScale, 1, haloScale);
      dummy.updateMatrix();
      haloMesh.setMatrixAt(i, dummy.matrix);
      haloMesh.setColorAt(i, isVac ? VACANT_COL : curColors.current[i]);

      // 3. Hairline outer reticle (vacant hollow ring, whole-apt rim, or selection reticle)
      const showRing = isSelected || isHovered || isVac || room.kind === '整租';
      dummy.position.set(rx, 0.096, rz);
      const ringScale = showRing ? (isSelected ? rVal * 2.4 : rVal * 1.48) : 0.001;
      dummy.scale.set(ringScale, 1, ringScale);
      dummy.updateMatrix();
      ringMesh.setMatrixAt(i, dummy.matrix);
      if (isSelected) {
        tmpColor.set(pal.room.selected).multiplyScalar(B(1.8));
      } else if (isVac) {
        if (pal.isLight) tmpColor.set(highlightVacant ? pal.room.alert : isDimmed ? pal.room.dim : pal.room.vacantRing);
        else tmpColor.set(highlightVacant ? pal.room.alert : pal.room.vacantRing).multiplyScalar(isDimmed ? 0.2 : 0.95);
      } else {
        if (pal.isLight) tmpColor.copy(curColors.current[i]).lerp(DIM_COL, isDimmed ? 0.8 : 0);
        else tmpColor.copy(curColors.current[i]).multiplyScalar(isDimmed ? 0.15 : 0.6);
      }
      ringMesh.setColorAt(i, tmpColor);
    }

    coreMesh.instanceMatrix.needsUpdate = true;
    if (coreMesh.instanceColor) coreMesh.instanceColor.needsUpdate = true;
    haloMesh.instanceMatrix.needsUpdate = true;
    if (haloMesh.instanceColor) haloMesh.instanceColor.needsUpdate = true;
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
    <group name="L5_room_nodes_240">
      <instancedMesh
        ref={haloRef}
        args={[haloPlaneGeo, haloMaterial, rooms.length]}
        onClick={handlePointer('click')}
        onPointerOver={handlePointer('over')}
        onPointerOut={handlePointer('out')}
      />
      <instancedMesh
        ref={coreRef}
        args={[discGeo, undefined, rooms.length]}
        onClick={handlePointer('click')}
        onPointerOver={handlePointer('over')}
        onPointerOut={handlePointer('out')}
      >
        <meshBasicMaterial toneMapped={false} transparent opacity={0.96} depthWrite={false} />
      </instancedMesh>
      <instancedMesh ref={ringRef} args={[outlineRingGeo, undefined, rooms.length]}>
        <meshBasicMaterial transparent opacity={0.85} side={THREE.DoubleSide} toneMapped={false} depthWrite={false} />
      </instancedMesh>
    </group>
  );
}
