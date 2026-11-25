import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { GeoJSONCollection, ProjectionMeta } from '@/types/viz';
import { LocalProjector } from '@/data/geo';

interface EastExpressLayerProps {
  newline: GeoJSONCollection;
  projection: ProjectionMeta;
  visible: boolean;
  announced: boolean;
  opened: boolean;
}

const LINE_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const LINE_FRAG = /* glsl */ `
  uniform float uTime;
  uniform float uProgress;
  uniform float uOpen;
  uniform float uOpacity;
  varying vec2 vUv;

  void main() {
    if (vUv.x > uProgress) discard;

    // Fine holographic dashed ticks when announced (M13-M24)
    float dash = step(0.36, fract(vUv.x * 34.0 - uTime * 0.55));
    float holoAlpha = dash * 0.88;

    // Solid luminous filament + sleek racing white-gold comets when opened (M25-M36)
    float p1 = exp(-pow(fract(vUv.x * 2.2 - uTime * 0.48) - 0.5, 2.0) * 140.0);
    float p2 = exp(-pow(fract(vUv.x * 2.2 + uTime * 0.36) - 0.5, 2.0) * 160.0);
    float openGlow = 1.15 + (p1 + p2 * 0.7) * 1.65;

    float alpha = mix(holoAlpha, 0.96, uOpen) * uOpacity;
    if (alpha < 0.03) discard;

    float head = smoothstep(0.05, 0.0, abs(vUv.x - uProgress)) * (1.0 - step(0.995, uProgress));
    vec3 amber = vec3(1.0, 0.69, 0.18);
    vec3 cream = vec3(1.0, 0.95, 0.80);
    vec3 col = mix(amber * 1.35, amber * openGlow + cream * (p1 * 0.85), uOpen);
    col += cream * head * 2.0;

    gl_FragColor = vec4(col, alpha);
  }
`;

/**
 * L4: Sleek precision amber corridor for hypothetical East Express Line (CBD -> Z01 -> Z05 -> Z11).
 * No chunky vertical pillars — refined glowing filament + concentric station rings on the map plane.
 */
export function EastExpressLayer({ newline, projection, visible, announced, opened }: EastExpressLayerProps) {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const progressRef = useRef(0);
  const openRef = useRef(0);
  const opacityRef = useRef(0);

  const { tubeGeo, haloGeo, stations } = useMemo(() => {
    const proj = new LocalProjector(projection);
    let curvePts: THREE.Vector3[] = [];
    const stList: Array<{ id: string; x: number; z: number; treated: boolean }> = [];

    for (const f of newline.features) {
      if (f.properties?.feature_kind === 'line' && f.geometry?.type === 'LineString') {
        curvePts = (f.geometry.coordinates as [number, number][]).map(([lon, lat]) => proj.lonLatToVec3(lon, lat, 0.11));
      } else if (f.properties?.feature_kind === 'station' && f.geometry?.type === 'Point') {
        const [lon, lat] = f.geometry.coordinates as [number, number];
        const [x, z] = proj.lonLatToXZ(lon, lat);
        stList.push({ id: f.properties.zone_id, x, z, treated: Boolean(f.properties.treated) });
      }
    }

    const curve = new THREE.CatmullRomCurve3(
      curvePts.length >= 2 ? curvePts : [new THREE.Vector3(0, 0.11, 0), new THREE.Vector3(18, 0.11, 1.5)]
    );
    const tGeo = new THREE.TubeGeometry(curve, 128, 0.048, 8, false);
    const hGeo = new THREE.TubeGeometry(curve, 96, 0.14, 8, false);
    return { tubeGeo: tGeo, haloGeo: hGeo, stations: stList };
  }, [newline, projection]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uProgress: { value: 0 },
      uOpen: { value: 0 },
      uOpacity: { value: 0 },
    }),
    []
  );

  const active = visible && (announced || opened);

  useFrame((_, delta) => {
    const mat = matRef.current;
    if (!mat) return;
    mat.uniforms.uTime.value += delta;
    if (active) {
      progressRef.current = Math.min(1, progressRef.current + delta * 0.78);
    } else {
      progressRef.current = Math.max(0, progressRef.current - delta * 2.5);
    }
    openRef.current = THREE.MathUtils.lerp(openRef.current, opened ? 1 : 0, Math.min(1, delta * 3.0));
    opacityRef.current = THREE.MathUtils.lerp(opacityRef.current, active ? 1 : 0, Math.min(1, delta * 4.0));

    mat.uniforms.uProgress.value = progressRef.current;
    mat.uniforms.uOpen.value = openRef.current;
    mat.uniforms.uOpacity.value = opacityRef.current;
  });

  return (
    <group name="L4_east_express" visible={visible}>
      <mesh geometry={tubeGeo}>
        <shaderMaterial
          ref={matRef}
          vertexShader={LINE_VERT}
          fragmentShader={LINE_FRAG}
          uniforms={uniforms}
          transparent
          toneMapped={false}
          depthWrite={false}
        />
      </mesh>
      {active && (
        <mesh geometry={haloGeo}>
          <meshBasicMaterial
            color="#FFB02E"
            transparent
            opacity={opened ? 0.2 : 0.09}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      )}
      {active &&
        stations.map((st) => (
          <group key={st.id} position={[st.x, 0.12, st.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[0.14, 20]} />
              <meshBasicMaterial color={new THREE.Color('#FFF1C7').multiplyScalar(1.6)} toneMapped={false} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.22, 0.28, 28]} />
              <meshBasicMaterial color={new THREE.Color('#FFB02E').multiplyScalar(1.4)} toneMapped={false} transparent opacity={0.9} />
            </mesh>
          </group>
        ))}
    </group>
  );
}
