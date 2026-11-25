import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useScenePalette } from '@/theme';
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
  uniform vec3 uOuter;
  uniform vec3 uCore;
  uniform vec3 uCbd;
  uniform vec3 uEast;
  uniform vec3 uWave;
  varying vec2 vWorldXZ;

  void main() {
    // Soft deep slate-blue aerial base matching Shenzhen night-map reference
    vec2 centerShift = vWorldXZ - vec2(4.0, 0.5);
    float r = length(centerShift);
    float coreGlow = exp(-r * r / 480.0);

    vec3 col = mix(uOuter, uCore, coreGlow * 0.85);

    // Very subtle atmospheric radial glow over CBD
    float rCBD = length(vWorldXZ);
    col += uCbd * exp(-rCBD * rCBD / 38.0) * 0.26;

    // Gentle warm golden aura over Eastern corridor (Z05 & Z11) once announced/opened
    float rEast = length(vWorldXZ - vec2(16.2, 1.4));
    col += uEast * exp(-rEast * rEast / 34.0) * (uAnnounced * 0.11 + uOpened * 0.14);

    // Crisp single expanding shockwave ring when announcement fires at M13
    if (uShockAge > 0.0 && uShockAge < 4.2) {
      float waveR = uShockAge * 7.8;
      float band = smoothstep(0.65, 0.0, abs(rCBD - waveR)) * (1.0 - uShockAge / 4.2);
      float eastBias = smoothstep(-0.2, 0.8, normalize(vWorldXZ + vec2(0.001)).x) * 0.65 + 0.35;
      col += uWave * band * eastBias * 0.72;
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
      uOuter: { value: new THREE.Vector3() },
      uCore: { value: new THREE.Vector3() },
      uCbd: { value: new THREE.Vector3() },
      uEast: { value: new THREE.Vector3() },
      uWave: { value: new THREE.Vector3() },
    }),
    []
  );
  const pal = useScenePalette();
  uniforms.uOuter.value.set(...pal.ground.outer);
  uniforms.uCore.value.set(...pal.ground.core);
  uniforms.uCbd.value.set(...pal.ground.cbd);
  uniforms.uEast.value.set(...pal.ground.east);
  uniforms.uWave.value.set(...pal.ground.wave);

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
