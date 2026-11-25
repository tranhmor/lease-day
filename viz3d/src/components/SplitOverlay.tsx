import { useRef } from 'react';
import { GripVertical, Sliders, X } from 'lucide-react';
import type { Lang } from '@/types/viz';
import { getDict } from '@/i18n';

interface SplitOverlayProps {
  splitRatio: number;
  lang: Lang;
  onChangeRatio: (r: number) => void;
}

export function SplitHeaderBar({
  lang,
  onSwitchToDiff,
  onExit,
}: {
  lang: Lang;
  onSwitchToDiff: () => void;
  onExit: () => void;
}) {
  const t = getDict(lang);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 6,
        flexWrap: 'wrap',
        pointerEvents: 'none',
        flexShrink: 0,
      }}
    >
      <div
        className="hud-panel"
        style={{
          padding: '4px 10px',
          borderColor: 'var(--s)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--s)',
        }}
      >
        {t.split.leftLabel}
      </div>

      <div style={{ display: 'flex', gap: 5, pointerEvents: 'auto' }}>
        <button type="button" className="btn-hud amber-active" onClick={onSwitchToDiff}>
          <Sliders size={11} /> {t.split.toDiff}
        </button>
        <button type="button" className="btn-hud" onClick={onExit}>
          <X size={11} /> {t.split.exit}
        </button>
      </div>

      <div
        className="hud-panel"
        style={{
          padding: '4px 10px',
          borderColor: 'var(--p)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--p)',
        }}
      >
        {t.split.rightLabel}
      </div>
    </div>
  );
}

export function SplitOverlay({ splitRatio, lang, onChangeRatio }: SplitOverlayProps) {
  const t = getDict(lang);
  const draggingRef = useRef(false);

  const pct = `${(splitRatio * 100).toFixed(2)}%`;

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 18 }}>
      {/* Vertical Curtain Divider */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: pct,
          width: 2,
          background: 'var(--announce)',
          boxShadow: '0 0 14px color-mix(in srgb, var(--announce) 85%, transparent)',
          transform: 'translateX(-1px)',
        }}
      />

      {/* Draggable Center Grip Handle */}
      <div
        title={t.split.dragTip}
        style={{
          position: 'absolute',
          top: '50%',
          left: pct,
          transform: 'translate(-50%, -50%)',
          width: 28,
          height: 50,
          borderRadius: 14,
          background: 'var(--panel-strong)',
          border: '1.5px solid var(--announce)',
          boxShadow: '0 0 18px color-mix(in srgb, var(--announce) 50%, transparent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--announce)',
          cursor: 'ew-resize',
          pointerEvents: 'auto',
        }}
        onPointerDown={(e) => {
          draggingRef.current = true;
          (e.currentTarget as Element).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!draggingRef.current) return;
          const r = Math.max(0.14, Math.min(0.86, e.clientX / window.innerWidth));
          onChangeRatio(r);
        }}
        onPointerUp={() => {
          draggingRef.current = false;
        }}
      >
        <GripVertical size={15} />
      </div>
    </div>
  );
}
