import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { DecisionRecord, LandlordMeta, RoomStatic } from '@/types/viz';

interface LandlordConstellationLayerProps {
  landlords: LandlordMeta[];
  rooms: RoomStatic[];
  decisions: DecisionRecord[];
  month: number;
  announced: boolean;
  opened: boolean;
  visible: boolean;
  isolateTreated?: boolean;
}

/**
 * Visual Style 1 (Combo C): 40 Real LLM Landlord Brains Constellation.
 * - Each of the 40 real landlords floats at the centroid of their managed rooms (y = 0.62).
 * - Gossamer luminous filaments connect each landlord brain down to their 4-8 exact rooms.
 * - Active pricing decisions flare the landlord node & its room links (amber if citing East Express!).
 */
export function LandlordConstellationLayer({
  landlords,
  rooms,
  decisions,
  month,
  announced,
  opened,
  visible,
  isolateTreated = false,
}: LandlordConstellationLayerProps) {
  const nodesRef = useRef<THREE.InstancedMesh>(null);
  const ringsRef = useRef<THREE.InstancedMesh>(null);

  // Compute exact geometric centroid of each landlord's managed rooms once
  const { landlordNodes, roomEdges } = useMemo(() => {
    const byLl = new Map<number, RoomStatic[]>();
    for (const r of rooms) {
      const list = byLl.get(r.landlord_id) ?? [];
      list.push(r);
      byLl.set(r.landlord_id, list);
    }

    const nodes: Array<{
      id: number;
      x: number;
      y: number;
      z: number;
      treated: boolean;
      patient: boolean;
      agency: boolean;
    }> = [];
    const edges: Array<{
      llId: number;
      roomId: number;
      treated: boolean;
      ax: number;
      ay: number;
      az: number;
      bx: number;
      by: number;
      bz: number;
    }> = [];

    for (const ll of landlords) {
      const owned = byLl.get(ll.landlord_id) ?? [];
      if (owned.length === 0) continue;
      let sx = 0;
      let sz = 0;
      for (const r of owned) {
        sx += r.layout_xy[0];
        sz += r.layout_xy[1];
      }
      const cx = sx / owned.length;
      const cz = sz / owned.length;
      const cy = ll.treated ? 0.85 : 0.62;
      nodes.push({
        id: ll.landlord_id,
        x: cx,
        y: cy,
        z: cz,
        treated: ll.treated,
        patient: ll.risk === '愿意等',
        agency: ll.kind === '托管机构',
      });

      for (const r of owned) {
        edges.push({
          llId: ll.landlord_id,
          roomId: r.id,
          treated: ll.treated,
          ax: cx,
          ay: cy,
          az: cz,
          bx: r.layout_xy[0],
          by: 0.1,
          bz: r.layout_xy[1],
        });
      }
    }
    return { landlordNodes: nodes, roomEdges: edges };
  }, [landlords, rooms]);

  // Identify landlords & rooms active in current month's pricing decisions
  const { activeLandlords, mentionLandlords, activeRoomLinks, mentionRoomLinks } = useMemo(() => {
    const aLl = new Set<number>();
    const mLl = new Set<number>();
    const aRm = new Set<number>();
    const mRm = new Set<number>();
    for (const d of decisions) {
      if (d.m !== month || d.agent_type !== 'landlord') continue;
      aLl.add(d.agent_id);
      if (d.room_id !== null) aRm.add(d.room_id);
      if (d.mentions_line) {
        mLl.add(d.agent_id);
        if (d.room_id !== null) mRm.add(d.room_id);
      }
    }
    return { activeLandlords: aLl, mentionLandlords: mLl, activeRoomLinks: aRm, mentionRoomLinks: mRm };
  }, [decisions, month]);

  // Build vertex-colored constellation filament BufferGeometry
  const edgeGeometry = useMemo(() => {
    const pos = new Float32Array(roomEdges.length * 6);
    const col = new Float32Array(roomEdges.length * 6);
    const cTmp = new THREE.Color();

    for (let i = 0; i < roomEdges.length; i++) {
      const e = roomEdges[i];
      const base = i * 6;
      pos[base] = e.ax;
      pos[base + 1] = e.ay;
      pos[base + 2] = e.az;
      pos[base + 3] = e.bx;
      pos[base + 4] = e.by;
      pos[base + 5] = e.bz;

      const isDim = isolateTreated && !e.treated;
      const isMention = mentionRoomLinks.has(e.roomId);
      const isActive = activeRoomLinks.has(e.roomId);

      if (isMention) {
        cTmp.set('#E4572E').multiplyScalar(0.8);
      } else if (e.treated && (announced || opened)) {
        cTmp.set('#E4572E').multiplyScalar(isActive ? 0.6 : 0.3);
      } else if (isActive && !isDim) {
        cTmp.set('#8A8F98').multiplyScalar(0.5);
      } else {
        cTmp.set('#4A4F57').multiplyScalar(isDim ? 0.08 : 0.22);
      }

      // Slightly brighter at landlord brain apex, softer at room anchor
      col[base] = cTmp.r;
      col[base + 1] = cTmp.g;
      col[base + 2] = cTmp.b;
      col[base + 3] = cTmp.r * 0.55;
      col[base + 4] = cTmp.g * 0.55;
      col[base + 5] = cTmp.b * 0.55;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    return geo;
  }, [roomEdges, activeRoomLinks, mentionRoomLinks, announced, opened, isolateTreated]);

  const { octGeo, haloRingGeo } = useMemo(() => {
    const oct = new THREE.OctahedronGeometry(0.14, 0);
    const ring = new THREE.RingGeometry(0.24, 0.29, 20);
    ring.rotateX(-Math.PI / 2);
    return { octGeo: oct, haloRingGeo: ring };
  }, []);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpCol = useMemo(() => new THREE.Color(), []);

  useFrame((state) => {
    if (!visible) return;
    const t = state.clock.getElapsedTime();
    const nMesh = nodesRef.current;
    const rMesh = ringsRef.current;
    if (!nMesh || !rMesh) return;

    for (let i = 0; i < landlordNodes.length; i++) {
      const ll = landlordNodes[i];
      const isDim = isolateTreated && !ll.treated;
      const isMention = mentionLandlords.has(ll.id);
      const isActive = activeLandlords.has(ll.id);

      const pulse = isMention ? 1.35 + 0.25 * Math.sin(t * 4.5 + i) : isActive ? 1.15 : 0.85;
      const scale = (ll.treated ? 1.15 : 0.88) * pulse * (isDim ? 0.55 : 1.0);

      dummy.position.set(ll.x, ll.y, ll.z);
      dummy.rotation.set(0, t * 0.5 + i, 0);
      dummy.scale.set(scale, scale, scale);
      dummy.updateMatrix();
      nMesh.setMatrixAt(i, dummy.matrix);

      if (isMention) {
        tmpCol.set('#E4572E');
      } else if (ll.treated && (announced || opened)) {
        tmpCol.set('#E4572E').multiplyScalar(0.85);
      } else if (isActive && !isDim) {
        tmpCol.set('#E8E4DC');
      } else {
        tmpCol.set('#8A8F98').multiplyScalar(isDim ? 0.25 : 0.85);
      }
      nMesh.setColorAt(i, tmpCol);

      // Horizontal halo ring around patient ("愿意等") or active-mention landlords
      const showR = (ll.patient || isMention || ll.treated) && !isDim;
      dummy.position.set(ll.x, ll.y, ll.z);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(showR ? scale * 1.15 : 0.001, 1, showR ? scale * 1.15 : 0.001);
      dummy.updateMatrix();
      rMesh.setMatrixAt(i, dummy.matrix);
      rMesh.setColorAt(i, tmpCol);
    }

    nMesh.instanceMatrix.needsUpdate = true;
    if (nMesh.instanceColor) nMesh.instanceColor.needsUpdate = true;
    rMesh.instanceMatrix.needsUpdate = true;
    if (rMesh.instanceColor) rMesh.instanceColor.needsUpdate = true;
  });

  if (!visible || landlordNodes.length === 0) return null;

  return (
    <group name="Style1_landlord_constellation">
      <lineSegments geometry={edgeGeometry}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.78}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
      <instancedMesh ref={nodesRef} args={[octGeo, undefined, landlordNodes.length]}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.95} />
      </instancedMesh>
      <instancedMesh ref={ringsRef} args={[haloRingGeo, undefined, landlordNodes.length]}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.65} side={THREE.DoubleSide} depthWrite={false} />
      </instancedMesh>
    </group>
  );
}
