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

    float dash = step(0.45, fract(vUv.x * 40.0));
    float alpha = mix(dash * 0.9, 1.0, uOpen) * uOpacity;
    if (alpha < 0.03) discard;
    vec3 col = vec3(0.894, 0.341, 0.180);

    gl_FragColor = vec4(col, alpha);
  }
`;

/**
 * L4: hypothetical East Express Line (CBD -> Z01 -> Z05 -> Z11).
 * Dashed while only announced, solid once open.
 */
export function EastExpressLayer({ newline, projection, visible, announced, opened }: EastExpressLayerProps) {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const progressRef = useRef(0);
  const openRef = useRef(0);
  const opacityRef = useRef(0);

  const { tubeGeo, stations } = useMemo(() => {
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
    const tGeo = new THREE.TubeGeometry(curve, 128, 0.04, 8, false);
    return { tubeGeo: tGeo, stations: stList };
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
      {active &&
        stations.map((st) => (
          <group key={st.id} position={[st.x, 0.12, st.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[0.16, 24]} />
              <meshBasicMaterial color="#0E1014" />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 0]}>
              <ringGeometry args={[0.12, 0.17, 28]} />
              <meshBasicMaterial color="#E4572E" />
            </mesh>
          </group>
        ))}
    </group>
  );
}
