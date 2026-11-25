import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { ZoneInfo } from '@/types/viz';

interface BidRentTerrainLayerProps {
  zones: ZoneInfo[];
  zoneStats: Record<string, { rentDeltaPts: number; rentIndex: number }>;
  diffZoneStatsS?: Record<string, { rentDeltaPts: number; rentIndex: number }> | null;
  diffMode?: boolean;
  visible: boolean;
  isolateTreated?: boolean;
}

const GRID_SEG = 88;
const SPAN_X = 56;
const SPAN_Z = 56;
const CENTER_X = 1.5;
const CENTER_Z = -2.0;

const TERRAIN_VERT = /* glsl */ `
  varying float vElev;
  varying vec2 vWorldXZ;
  void main() {
    vElev = position.y;
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vWorldXZ = wp.xz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const TERRAIN_FRAG = /* glsl */ `
  varying float vElev;
  varying vec2 vWorldXZ;

  void main() {
    // Convert mesh height back to rent delta index points (1.0 scene unit ≈ 1.5 pts)
    float pts = vElev * 1.45;
    float absPts = abs(pts);

    // Flat neutral zones stay nearly transparent so Beijing's OSM roads & metro shine cleanly underneath!
    float visibility = smoothstep(0.32, 1.15, absPts);
    if (visibility < 0.015) discard;

    // Razor-sharp topographic contour isolines every 0.45 index pts
    float isoCoord = pts / 0.45;
    float isoDist = abs(fract(isoCoord + 0.5) - 0.5) / max(0.001, fwidth(isoCoord));
    float contour = 1.0 - min(isoDist / 1.25, 1.0);

    // Subtle delicate slope wireframe grid
    vec2 gCoord = vWorldXZ / 1.25;
    vec2 gDist = abs(fract(gCoord - 0.5) - 0.5) / max(0.001, fwidth(gCoord));
    float wire = 1.0 - min(min(gDist.x, gDist.y) / 0.9, 1.0);

    // Diverging urban economics ramp: cool blue (negative) -> amber -> coral (surging rent peaks)
    vec3 colNeg = vec3(0.37, 0.71, 1.0);
    vec3 colMid = vec3(1.0, 0.69, 0.18);
    vec3 colHot = vec3(1.0, 0.36, 0.24);
    vec3 baseCol = pts >= 0.0
      ? mix(colMid, colHot, smoothstep(1.5, 4.5, pts))
      : colNeg;

    float fillAlpha = visibility * 0.17;
    float lineAlpha = visibility * (contour * 0.72 + wire * 0.22);
    float totalAlpha = clamp(fillAlpha + lineAlpha, 0.0, 0.88);

    vec3 finalCol = baseCol * (0.95 + contour * 0.85);
    gl_FragColor = vec4(finalCol, totalAlpha);
  }
`;

/**
 * Visual Style 2 (Combo B): Alonso Bid-Rent Topographic Contour Terrain.
 * Smooth Gaussian-RBF spatial interpolation of real 24-zone rent changes.
 * In P scenario (M13-M24) or Split S|P, Guoyuan & Wuyi Garden swell into a luminous amber contour hill!
 */
export function BidRentTerrainLayer({
  zones,
  zoneStats,
  diffZoneStatsS = null,
  diffMode = false,
  visible,
  isolateTreated = false,
}: BidRentTerrainLayerProps) {
  const geoRef = useRef<THREE.PlaneGeometry>(null);

  // Precompute Gaussian RBF weights (grid vertex -> 24 zone centroids) ONCE for instant 60fps updates!
  const { geometry, weights, targetY, currentY } = useMemo(() => {
    const geo = new THREE.PlaneGeometry(SPAN_X, SPAN_Z, GRID_SEG, GRID_SEG);
    geo.rotateX(-Math.PI / 2);
    geo.translate(CENTER_X, 0.08, CENTER_Z);

    const pos = geo.getAttribute('position') as THREE.BufferAttribute;
    const vCount = pos.count;
    const zCount = zones.length;
    const wArr = new Float32Array(vCount * zCount);

    // Kernel sigma ~ 3.4 km gives smooth continuous hills centered accurately on each zone
    const twoSigma2 = 2 * 3.4 * 3.4;

    for (let vi = 0; vi < vCount; vi++) {
      const vx = pos.getX(vi);
      const vz = pos.getZ(vi);
      let wSum = 0;
      for (let zi = 0; zi < zCount; zi++) {
        const dx = vx - zones[zi].x;
        const dz = vz - zones[zi].z;
        const d2 = dx * dx + dz * dz;
        const w = Math.exp(-d2 / twoSigma2);
        wArr[vi * zCount + zi] = w;
        wSum += w;
      }
      // Keep gentle decay to 0 at city edges (add small baseline denominator)
      const denom = wSum + 0.25;
      for (let zi = 0; zi < zCount; zi++) {
        wArr[vi * zCount + zi] /= denom;
      }
    }

    return {
      geometry: geo,
      weights: wArr,
      targetY: new Float32Array(vCount),
      currentY: new Float32Array(vCount),
    };
  }, [zones]);

  // Compute target vertex elevations whenever zoneStats changes
  useMemo(() => {
    const zCount = zones.length;
    const zVals = new Float32Array(zCount);
    for (let zi = 0; zi < zCount; zi++) {
      const z = zones[zi];
      if (isolateTreated && !z.treated) {
        zVals[zi] = 0;
        continue;
      }
      const dA = zoneStats[z.id]?.rentDeltaPts ?? 0;
      if (diffMode && diffZoneStatsS) {
        const dS = diffZoneStatsS[z.id]?.rentDeltaPts ?? 0;
        zVals[zi] = (dA - dS) * 1.15;
      } else {
        zVals[zi] = dA;
      }
    }

    const vCount = targetY.length;
    const ELEV_SCALE = 0.72; // +4 index pts -> ~2.9 unit gentle architectural contour hill
    for (let vi = 0; vi < vCount; vi++) {
      let sum = 0;
      const base = vi * zCount;
      for (let zi = 0; zi < zCount; zi++) {
        sum += weights[base + zi] * zVals[zi];
      }
      // Keep slightly lifted above ground plane (y = 0.08 + smooth height)
      targetY[vi] = Math.max(-1.6, Math.min(4.8, sum * ELEV_SCALE));
    }
  }, [zones, zoneStats, diffZoneStatsS, diffMode, isolateTreated, weights, targetY]);

  useFrame((_, delta) => {
    if (!visible) return;
    const pos = geometry.getAttribute('position') as THREE.BufferAttribute;
    const damp = 1 - Math.exp(-delta * 5.2);
    let dirty = false;

    for (let i = 0; i < currentY.length; i++) {
      const diff = targetY[i] - currentY[i];
      if (Math.abs(diff) > 0.0015) {
        currentY[i] += diff * damp;
        pos.setY(i, 0.08 + currentY[i]);
        dirty = true;
      }
    }
    if (dirty) {
      pos.needsUpdate = true;
    }
  });

  if (!visible) return null;

  return (
    <mesh name="Style2_bid_rent_terrain" geometry={geometry} ref={geoRef as any}>
      <shaderMaterial
        vertexShader={TERRAIN_VERT}
        fragmentShader={TERRAIN_FRAG}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
