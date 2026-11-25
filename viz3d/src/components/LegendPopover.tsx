import { X } from 'lucide-react';
import type { Lang } from '@/types/viz';
import { getDict } from '@/i18n';

interface LegendPopoverProps {
  lang: Lang;
  onClose: () => void;
}

export function LegendPopover({ lang, onClose }: LegendPopoverProps) {
  const t = getDict(lang);

  return (
    <div
      className="hud-panel"
      style={{
        position: 'absolute',
        right: 18,
        top: 152,
        width: 364,
        padding: '14px 16px',
        zIndex: 55,
        background: 'var(--panel-strong)',
        boxShadow: 'var(--shadow-strong)',
        fontSize: 11.5,
        lineHeight: 1.55,
      }}
    >
      <div className="panel-header">
        <span>{t.legend.title}</span>
        <button type="button" className="btn-hud" style={{ padding: 3 }} onClick={onClose}>
          <X size={13} />
        </button>
      </div>

      {/* Diverging Rent Change Ramp */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ color: 'var(--sub)', fontSize: 10.5, marginBottom: 4 }}>{t.legend.rentScale}</div>
        <div
          style={{
            height: 8,
            borderRadius: 4,
            background: 'linear-gradient(90deg, var(--cool) 0%, var(--sub-2) 50%, var(--announce) 75%, var(--rent-max) 100%)',
          }}
        />
        <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sub)', marginTop: 2 }}>
          <span>−4</span>
          <span>0</span>
          <span>+2</span>
          <span>+4</span>
        </div>
      </div>

      {/* Fixed Scenario & Move-in Colors */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 11 }}>
        <span style={{ color: 'var(--p)' }}>■ P</span>
        <span style={{ color: 'var(--s)' }}>■ S</span>
        <span style={{ color: 'var(--n)' }}>■ N</span>
        <span style={{ color: 'var(--announce)' }}>■ {lang === 'zh' ? '东向快线 / 公告' : 'East Express'}</span>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 11 }}>
        <span style={{ color: 'var(--sub)' }}>{lang === 'zh' ? '搬家弧线：' : 'Move Arcs:'}</span>
        <span style={{ color: 'var(--inc-low)' }}>● {t.moverProfile.low}</span>
        <span style={{ color: 'var(--inc-mid)' }}>● {t.moverProfile.mid}</span>
        <span style={{ color: 'var(--inc-high)' }}>● {t.moverProfile.high}</span>
      </div>

      <div style={{ color: 'var(--text)', marginBottom: 6 }}>{t.legend.shapes}</div>
      <div style={{ color: 'var(--announce)', fontSize: 11, marginBottom: 5 }}>• {t.legend.oversample}</div>
      <div style={{ color: 'var(--sub)', fontSize: 11, marginBottom: 4 }}>• {t.legend.schematic}</div>
      <div style={{ color: 'var(--sub)', fontSize: 11 }}>• {t.legend.hypothetical}</div>
    </div>
  );
}
