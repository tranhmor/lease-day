import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useScenePalette } from '@/theme';
import { useFrame } from '@react-three/fiber';
import type { GeoJSONCollection, ProjectionMeta } from '@/types/viz';
import { LocalProjector } from '@/data/geo';

interface MetroLayerProps {
  metro: GeoJSONCollection;
  projection: ProjectionMeta;
  visible: boolean;
  highlighted?: boolean;
  dimmed?: boolean;
}

const COMET_VERT = /* glsl */ `
  attribute vec3 aEnd;
  attribute float aPhase;
  attribute float aSpeed;
  uniform float uTime;
  varying float vAlpha;

  void main() {
    float t = fract(aPhase + uTime * aSpeed);
    vec3 pos = mix(position, aEnd, t);
    vAlpha = smoothstep(0.0, 0.15, t) * smoothstep(1.0, 0.85, t);
    vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPos;
    gl_PointSize = 4.2 * (26.0 / max(1.0, -mvPos.z));
  }
`;

const COMET_FRAG = /* glsl */ `
  uniform float uOpacity;
  uniform vec3 uColor;
  uniform float uBoost;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float core = exp(-d * d * 22.0);
    gl_FragColor = vec4(uColor * uBoost, core * vAlpha * uOpacity);
  }
`;

/**
 * L3: Refined razor-thin luminous Beijing subway veins + smoothly gliding train-light comets (3 draw calls total).
 */
export function MetroLayer({ metro, projection, visible, highlighted = false, dimmed = false }: MetroLayerProps) {
  const cometMatRef = useRef<THREE.ShaderMaterial>(null);

  const { coreLineGeo, glowRibbonGeo, cometGeo } = useMemo(() => {
    const proj = new LocalProjector(projection);
    const lineSegPos: number[] = [];
    const ribbonPos: number[] = [];
    const ribbonIdx: number[] = [];
    const cometStarts: number[] = [];
    const cometEnds: number[] = [];
    const cometPhases: number[] = [];
    const cometSpeeds: number[] = [];

    let vOff = 0;
    const Y_CORE = 0.055;
    const Y_GLOW = 0.048;
    const HALF_W = 0.042; // ultra-delicate luminous vein

    let seed = 9001;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };

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

        ribbonPos.push(p[0] - px, Y_GLOW, p[1] - pz);
        ribbonPos.push(p[0] + px, Y_GLOW, p[1] + pz);

        if (i < pts.length - 1) {
          const n = pts[i + 1];
          lineSegPos.push(p[0], Y_CORE, p[1], n[0], Y_CORE, n[1]);
          const a = vOff + i * 2;
          ribbonIdx.push(a, a + 1, a + 3, a, a + 3, a + 2);

          // Spawn smooth gliding light comets along segments
          if (rand() < 0.42) {
            cometStarts.push(p[0], Y_CORE + 0.015, p[1]);
            cometEnds.push(n[0], Y_CORE + 0.015, n[1]);
            cometPhases.push(rand());
            cometSpeeds.push(0.28 + rand() * 0.32);
          }
        }
      }
      vOff += pts.length * 2;
    }

    const cGeo = new THREE.BufferGeometry();
    cGeo.setAttribute('position', new THREE.Float32BufferAttribute(lineSegPos, 3));

    const rGeo = new THREE.BufferGeometry();
    rGeo.setAttribute('position', new THREE.Float32BufferAttribute(ribbonPos, 3));
    rGeo.setIndex(ribbonIdx);

    const cmGeo = new THREE.BufferGeometry();
    cmGeo.setAttribute('position', new THREE.Float32BufferAttribute(cometStarts, 3));
    cmGeo.setAttribute('aEnd', new THREE.Float32BufferAttribute(cometEnds, 3));
    cmGeo.setAttribute('aPhase', new THREE.Float32BufferAttribute(cometPhases, 1));
    cmGeo.setAttribute('aSpeed', new THREE.Float32BufferAttribute(cometSpeeds, 1));

    return { coreLineGeo: cGeo, glowRibbonGeo: rGeo, cometGeo: cmGeo };
  }, [metro, projection]);

  const cometUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uOpacity: { value: 0.85 },
      uColor: { value: new THREE.Vector3(0.86, 0.95, 1.0) },
      uBoost: { value: 1.85 },
    }),
    []
  );
  const pal = useScenePalette();
  cometUniforms.uColor.value.set(...pal.metro.comet);
  cometUniforms.uBoost.value = pal.isLight ? 1 : 1.85;

  useFrame((_, delta) => {
    if (cometMatRef.current) {
      cometMatRef.current.uniforms.uTime.value += delta;
      cometMatRef.current.uniforms.uOpacity.value = dimmed ? 0.2 : highlighted ? 1.0 : 0.82;
    }
  });

  if (!visible) return null;

  const boost = pal.isLight ? (dimmed ? 0.9 : 1) : highlighted ? 1.6 : dimmed ? 0.4 : 1.15;

  return (
    <group name="L3_metro">
      {/* Subtle luminous ribbon glow */}
      <mesh geometry={glowRibbonGeo}>
        <meshBasicMaterial
          color={new THREE.Color(pal.metro.ribbon).multiplyScalar(boost)}
          toneMapped={false}
          transparent
          opacity={dimmed ? 0.14 : highlighted ? 0.55 : 0.28}
          blending={pal.glowBlending}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
      {/* Razor-thin bright ice-white metro filament */}
      <lineSegments geometry={coreLineGeo}>
        <lineBasicMaterial
          color={new THREE.Color(pal.metro.core).multiplyScalar(boost)}
          toneMapped={false}
          transparent
          opacity={dimmed ? 0.24 : highlighted ? 0.96 : 0.72}
          depthWrite={false}
        />
      </lineSegments>
      {/* Gliding train-light comets */}
      <points geometry={cometGeo} frustumCulled={false}>
        <shaderMaterial
          ref={cometMatRef}
          vertexShader={COMET_VERT}
          fragmentShader={COMET_FRAG}
          uniforms={cometUniforms}
          transparent
          blending={pal.glowBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </points>
    </group>
  );
}
