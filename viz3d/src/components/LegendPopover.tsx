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
      className="hud-panel accent-cool"
      style={{
        position: 'absolute',
        right: 20,
        top: 174,
        width: 368,
        padding: '14px 16px',
        zIndex: 55,
        backgroundColor: 'var(--panel-strong)',
        boxShadow: 'var(--shadow-strong), var(--glass-rim)',
        fontSize: 11.5,
        lineHeight: 1.6,
      }}
    >
      <div className="panel-header">
        <span>{t.legend.title}</span>
        <button type="button" className="btn-hud" style={{ padding: 3 }} onClick={onClose}>
          <X size={13} />
        </button>
      </div>

      {/* Diverging Rent Change Ramp */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: 'var(--sub)', fontSize: 10.5, marginBottom: 5 }}>{t.legend.rentScale}</div>
        <div
          style={{
            height: 8,
            borderRadius: 4,
            background: 'linear-gradient(90deg, var(--rent-neg) 0%, var(--rent-zero) 50%, var(--announce) 75%, var(--rent-max) 100%)',
          }}
        />
        <div className="num" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--sub)', marginTop: 4 }}>
          <span>−4</span>
          <span>0</span>
          <span>+2</span>
          <span>+4</span>
        </div>
      </div>

      {/* Fixed Scenario & Move-in Colors */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 11, flexWrap: 'wrap' }}>
        <span className="num" style={{ color: 'var(--p)', fontWeight: 600 }}>■ P</span>
        <span className="num" style={{ color: 'var(--s)', fontWeight: 600 }}>■ S</span>
        <span className="num" style={{ color: 'var(--n)', fontWeight: 600 }}>■ N</span>
        <span style={{ color: 'var(--announce)', fontWeight: 500 }}>■ {lang === 'zh' ? '东向快线 / 公告' : 'East Express'}</span>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 12, fontSize: 11, flexWrap: 'wrap' }}>
        <span style={{ color: 'var(--sub)' }}>{lang === 'zh' ? '搬家弧线' : 'Move Arcs'}</span>
        <span style={{ color: 'var(--inc-low)' }}>● {t.moverProfile.low}</span>
        <span style={{ color: 'var(--inc-mid)' }}>● {t.moverProfile.mid}</span>
        <span style={{ color: 'var(--inc-high)' }}>● {t.moverProfile.high}</span>
      </div>

      <div style={{ color: 'var(--text)', marginBottom: 10, fontSize: 11.5 }}>{t.legend.shapes}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, borderTop: '1px solid var(--line-soft)', paddingTop: 9 }}>
        <div style={{ color: 'var(--announce)', fontSize: 11, borderLeft: '2px solid var(--announce)', paddingLeft: 8 }}>
          {t.legend.oversample}
        </div>
        <div style={{ color: 'var(--sub)', fontSize: 11, borderLeft: '2px solid var(--line)', paddingLeft: 8 }}>
          {t.legend.schematic}
        </div>
        <div style={{ color: 'var(--sub)', fontSize: 11, borderLeft: '2px solid var(--line)', paddingLeft: 8 }}>
          {t.legend.hypothetical}
        </div>
      </div>
    </div>
  );
}
