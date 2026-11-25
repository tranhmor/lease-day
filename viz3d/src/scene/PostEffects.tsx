import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';

interface PostEffectsProps {
  enabled: boolean;
}

/**
 * Selective HDR Bloom (luminanceThreshold > 1.0 only blooms emissive metro, East Express, pulses & hot pillars)
 * plus subtle vignette. Completely skipped in Quality Tier 1/2 (§5.4 & §8.3).
 */
export function PostEffects({ enabled }: PostEffectsProps) {
  if (!enabled) return null;

  return (
    <EffectComposer multisampling={0}>
      <Bloom
        intensity={0.46}
        luminanceThreshold={1.08}
        luminanceSmoothing={0.26}
        mipmapBlur
      />
      <Vignette eskil={false} offset={0.28} darkness={0.36} />
    </EffectComposer>
  );
}
