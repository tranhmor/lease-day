import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

interface GroundLayerProps {
  shockwaveTime: number;
  announced: boolean;
  opened: boolean;
}

const VERT = /* glsl */ `
  varying vec2 vWorldXZ;
  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vWorldXZ = wp.xz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const FRAG = /* glsl */ `
  uniform float uTime;
  uniform float uShockAge;
  uniform float uAnnounced;
  uniform float uOpened;
  varying vec2 vWorldXZ;

  void main() {
    vec3 col = vec3(0.071, 0.078, 0.094);
    float rCBD = length(vWorldXZ);
    col += vec3(0.02) * exp(-rCBD * rCBD / 600.0);

    // Single thin ring when the announcement fires at M13
    if (uShockAge > 0.0 && uShockAge < 3.5) {
      float waveR = uShockAge * 8.0;
      float band = smoothstep(0.12, 0.0, abs(rCBD - waveR)) * (1.0 - uShockAge / 3.5);
      col = mix(col, vec3(0.89, 0.34, 0.18), band * 0.6);
    }

    gl_FragColor = vec4(col, 1.0);
  }
`;

/**
 * L0: Clean aerial dark-slate urban ground plane (no chunky sci-fi grid).
 */
export function GroundLayer({ shockwaveTime, announced, opened }: GroundLayerProps) {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uShockAge: { value: -1 },
      uAnnounced: { value: 0 },
      uOpened: { value: 0 },
    }),
    []
  );

  useFrame((_, delta) => {
    const mat = matRef.current;
    if (!mat) return;
    mat.uniforms.uTime.value += delta;
    const nowSec = performance.now() / 1000;
    mat.uniforms.uShockAge.value = shockwaveTime > 0 ? nowSec - shockwaveTime : -1;
    mat.uniforms.uAnnounced.value = THREE.MathUtils.lerp(mat.uniforms.uAnnounced.value, announced ? 1 : 0, Math.min(1, delta * 3));
    mat.uniforms.uOpened.value = THREE.MathUtils.lerp(mat.uniforms.uOpened.value, opened ? 1 : 0, Math.min(1, delta * 3));
  });

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]}>
      <planeGeometry args={[220, 220, 1, 1]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={VERT}
        fragmentShader={FRAG}
        uniforms={uniforms}
        depthWrite={true}
      />
    </mesh>
  );
}
