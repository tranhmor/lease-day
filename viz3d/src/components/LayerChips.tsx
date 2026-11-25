import type { Lang, LayerToggles } from '@/types/viz';
import { getDict } from '@/i18n';

interface LayerChipsProps {
  layers: LayerToggles;
  lang: Lang;
  onToggle: (key: keyof LayerToggles) => void;
}

const CHIP_ORDER: Array<{ key: keyof LayerToggles; amber?: boolean }> = [
  { key: 'rooms' },
  { key: 'metro' },
  { key: 'newline', amber: true },
  { key: 'pulse' },
  { key: 'commute' },
  { key: 'arcs' },
  { key: 'mindTags', amber: true },
  { key: 'isochrone' },
];

export function LayerChips({ layers, lang, onToggle }: LayerChipsProps) {
  const t = getDict(lang);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'nowrap',
        justifyContent: 'center',
        gap: 16,
        pointerEvents: 'none',
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      {CHIP_ORDER.map(({ key, amber }) => (
        <button
          key={key}
          type="button"
          className={`chip ${layers[key] ? 'on' : ''} ${amber ? 'amber' : ''}`}
          onClick={() => onToggle(key)}
        >
          <span className="dot" />
          {t.layers[key]}
        </button>
      ))}
    </div>
  );
}
