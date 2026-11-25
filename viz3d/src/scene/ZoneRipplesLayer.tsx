import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import type { ZoneInfo } from '@/types/viz';

interface ZoneRipplesLayerProps {
  zones: ZoneInfo[];
  psGap: number;
  announced: boolean;
  opened: boolean;
  showIsochrone: boolean;
  isolateTreated?: boolean;
}

const HUB_RING_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const HUB_RING_FRAG = /* glsl */ `
  uniform float uTime;
  uniform float uIntensity;
  uniform vec3 uColor;
  uniform float uPulseSpeed;
  varying vec2 vUv;

  void main() {
    vec2 p = vUv * 2.0 - 1.0;
    float r = length(p);
    if (r > 1.0) discard;

    // Razor-thin architectural concentric rings (like the Shenzhen reference hubs!)
    float ang = atan(p.y, p.x);
    float dashMask = step(0.15, fract(ang * 14.0 / 6.28318));

    float ring1 = smoothstep(0.016, 0.0, abs(r - 0.34));
    float ring2 = smoothstep(0.014, 0.0, abs(r - 0.62)) * (0.45 + 0.55 * dashMask);
    float ring3 = smoothstep(0.012, 0.0, abs(r - 0.90)) * 0.65;

    // Gentle expanding scan pulse wave
    float pulseR = fract(uTime * uPulseSpeed);
    float wave = smoothstep(0.025, 0.0, abs(r - pulseR)) * (1.0 - pulseR) * 0.9;

    float alpha = (ring1 * 0.55 + ring2 * 0.42 + ring3 * 0.30 + wave * 0.65) * uIntensity;
    if (alpha < 0.01) discard;

    gl_FragColor = vec4(uColor * (1.2 + wave * 0.7), alpha);
  }
`;

/**
 * L6: Signature razor-thin concentric radar rings around major urban hubs (cool ice-blue)
 * and dynamic golden pulsing concentric rings around treated zones (Guoyuan Z05 & Wuyi Garden Z11).
 */
export function ZoneRipplesLayer({
  zones,
  psGap,
  announced,
  opened,
  showIsochrone,
  isolateTreated = false,
}: ZoneRipplesLayerProps) {
  const hubZones = useMemo(
    () => zones.filter((z) => z.treated || z.id === 'Z00' || z.id === 'Z02' || z.id === 'Z04' || z.id === 'Z03' || z.id === 'Z07'),
    [zones]
  );
  const treated = useMemo(() => zones.filter((z) => z.treated), [zones]);

  const matRefs = useRef<Array<THREE.ShaderMaterial | null>>([]);
  const isoGroupRef = useRef<THREE.Group>(null);
  const isoScaleRef = useRef(1.0);

  const uniformsList = useMemo(
    () =>
      hubZones.map((z) => ({
        uTime: { value: 0 },
        uIntensity: { value: z.treated ? 0.55 : 0.45 },
        uColor: { value: new THREE.Color(z.treated ? '#FFB02E' : '#85C7FF') },
        uPulseSpeed: { value: z.treated ? 0.28 : 0.16 },
      })),
    [hubZones]
  );

  useFrame((_, delta) => {
    for (let i = 0; i < hubZones.length; i++) {
      const m = matRefs.current[i];
      if (!m) continue;
      const z = hubZones[i];
      m.uniforms.uTime.value += delta;
      let targetInt = 0.42;
      if (z.treated) {
        targetInt = announced || opened ? Math.min(1.0, 0.55 + Math.abs(psGap) * 0.2 + (opened ? 0.2 : 0)) : 0.38;
        m.uniforms.uColor.value.lerp(new THREE.Color(announced || opened ? '#FFB02E' : '#85C7FF'), Math.min(1, delta * 3));
      } else {
        targetInt = isolateTreated ? 0.12 : z.id === 'Z00' ? 0.62 : 0.38;
      }
      m.uniforms.uIntensity.value = THREE.MathUtils.lerp(m.uniforms.uIntensity.value, targetInt, Math.min(1, delta * 3));
    }

    const targetIso = opened ? 0.74 : 1.0;
    isoScaleRef.current = THREE.MathUtils.lerp(isoScaleRef.current, targetIso, Math.min(1, delta * 2.5));
    if (isoGroupRef.current) {
      isoGroupRef.current.children.forEach((child) => {
        child.scale.set(isoScaleRef.current, 1, isoScaleRef.current);
      });
    }
  });

  return (
    <group name="L6_zone_ripples">
      {hubZones.map((z, idx) => {
        const baseR = z.id === 'Z00' ? 3.8 : z.treated ? 3.4 + Math.min(1.4, Math.abs(psGap) * 0.4) : 2.6;
        return (
          <mesh key={z.id} position={[z.x, 0.04, z.z]} rotation={[-Math.PI / 2, 0, 0]} scale={[baseR, baseR, 1]}>
            <planeGeometry args={[2, 2]} />
            <shaderMaterial
              ref={(el) => {
                matRefs.current[idx] = el;
              }}
              vertexShader={HUB_RING_VERT}
              fragmentShader={HUB_RING_FRAG}
              uniforms={uniformsList[idx]}
              transparent
              blending={THREE.AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        );
      })}

      {/* Commute Isochrone rings (crisp green dashed circles that shrink at M25) */}
      {showIsochrone && (
        <group ref={isoGroupRef}>
          {treated.map((z) => (
            <group key={`iso_${z.id}`} position={[z.x, 0.052, z.z]}>
              {[1.7, 3.0, 4.3].map((r, ri) => (
                <mesh key={ri} rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[r - 0.025, r + 0.025, 64]} />
                  <meshBasicMaterial
                    color="#6BD3A0"
                    transparent
                    opacity={0.45 - ri * 0.1}
                    side={THREE.DoubleSide}
                    depthWrite={false}
                  />
                </mesh>
              ))}
            </group>
          ))}
        </group>
      )}
    </group>
  );
}
