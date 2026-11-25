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
          padding: '5px 12px',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text)',
          borderLeft: '2px solid var(--s)',
        }}
      >
        {t.split.leftLabel}
      </div>

      <div style={{ display: 'flex', gap: 5, pointerEvents: 'auto' }}>
        <button type="button" className="btn-hud" style={{ background: "var(--panel-solid)" }} onClick={onSwitchToDiff}>
          <Sliders size={11} /> {t.split.toDiff}
        </button>
        <button type="button" className="btn-hud" style={{ background: "var(--panel-solid)" }} onClick={onExit}>
          <X size={11} /> {t.split.exit}
        </button>
      </div>

      <div
        className="hud-panel"
        style={{
          padding: '5px 12px',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text)',
          borderRight: '2px solid var(--p)',
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
          width: 1,
          background: 'var(--text)',
          opacity: 0.7,
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
          width: 18,
          height: 40,
          borderRadius: 2,
          background: 'var(--panel-solid)',
          border: '1px solid var(--text)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text)',
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
        <GripVertical size={12} />
      </div>
    </div>
  );
}
