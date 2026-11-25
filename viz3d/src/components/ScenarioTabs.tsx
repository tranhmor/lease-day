import type React from 'react';
import { Camera, Compass, Globe, HelpCircle, Layers, Mountain, Network, Presentation } from 'lucide-react';
import type { AppMode, Lang, QualityTier, Scenario, ViewMode, VisualStyle } from '@/types/viz';
import { getDict } from '@/i18n';

interface ScenarioTabsProps {
  scenario: Scenario;
  mode: AppMode;
  viewMode: ViewMode;
  visualStyle: VisualStyle;
  lang: Lang;
  qualityTier: QualityTier;
  highlightTabs?: boolean;
  onScenarioChange: (sc: Scenario) => void;
  onToggleMode: () => void;
  onViewModeChange: (vm: ViewMode) => void;
  onVisualStyleChange: (st: VisualStyle) => void;
  onToggleLang: () => void;
  onCycleQuality: () => void;
  onOpenLegend: () => void;
  onOpenExport: () => void;
}

const SC_COLORS: Record<Scenario, string> = {
  N: '#6E7480',
  S: '#7C9CB8',
  P: '#E4572E',
};

export function ScenarioTabs({
  scenario,
  mode,
  viewMode,
  visualStyle,
  lang,
  qualityTier,
  highlightTabs = false,
  onScenarioChange,
  onToggleMode,
  onViewModeChange,
  onVisualStyleChange,
  onToggleLang,
  onCycleQuality,
  onOpenLegend,
  onOpenExport,
}: ScenarioTabsProps) {
  const t = getDict(lang);

  const seg = (on: boolean): React.CSSProperties => ({
    flex: 1,
    border: 'none',
    borderBottom: `2px solid ${on ? 'var(--text)' : 'transparent'}`,
    background: 'transparent',
    color: on ? 'var(--text)' : 'var(--faint)',
    padding: '6px 2px 7px',
    cursor: 'pointer',
    fontSize: 12.5,
    fontFamily: 'var(--font-sans)',
    transition: 'color 0.15s',
  });

  return (
    <div className="hud-panel" style={{ width: '100%', padding: '10px 14px 10px', flexShrink: 0 }}>
      <div style={{ display: 'flex', borderBottom: '1px solid var(--line-soft)' }}>
        {(['N', 'S', 'P'] as Scenario[]).map((sc) => {
          const on = scenario === sc && viewMode === 'single';
          return (
            <button
              key={sc}
              type="button"
              title={t.scenarios[sc].desc}
              style={{
                ...seg(on),
                borderBottomColor: on ? SC_COLORS[sc] : 'transparent',
                boxShadow: highlightTabs && !on ? 'inset 0 -1px 0 var(--faint)' : undefined,
              }}
              onClick={() => {
                if (viewMode !== 'single') onViewModeChange('single');
                onScenarioChange(sc);
              }}
            >
              <b style={{ fontWeight: 600, marginRight: 4 }}>{sc}</b>
              {t.scenarios[sc].short}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', gap: 2, marginTop: 6 }}>
        <button type="button" style={seg(viewMode === 'split')} onClick={() => onViewModeChange(viewMode === 'split' ? 'single' : 'split')} title="D">
          {t.modes.split}
        </button>
        <button type="button" style={seg(viewMode === 'diff')} onClick={() => onViewModeChange(viewMode === 'diff' ? 'single' : 'diff')}>
          {t.modes.diff}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 8, fontSize: 11.5, color: 'var(--sub)' }}>
        <button type="button" className="btn-hud" onClick={onToggleMode} style={{ border: 'none', padding: '3px 4px' }}>
          {mode === 'presentation' ? <Presentation size={12} /> : <Compass size={12} />}
          {mode === 'presentation' ? t.modes.presentation : t.modes.explore}
        </button>
        <span style={{ color: 'var(--line)' }}>|</span>
        <button
          type="button"
          className="btn-hud"
          style={{ border: 'none', padding: '3px 4px' }}
          onClick={() => onVisualStyleChange(visualStyle === 'constellation' ? 'terrain' : 'constellation')}
          title="V"
        >
          {visualStyle === 'constellation' ? <Network size={12} /> : <Mountain size={12} />}
          {visualStyle === 'constellation' ? t.styles.constellation : t.styles.terrain}
        </button>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn-hud" style={{ border: 'none', padding: '3px 5px' }} onClick={onToggleLang} title="中文 / English">
          <Globe size={12} />
          {lang === 'zh' ? 'EN' : '中'}
        </button>
        <button
          type="button"
          className="btn-hud"
          style={{ border: 'none', padding: '3px 5px', color: qualityTier > 0 ? 'var(--accent)' : undefined }}
          onClick={onCycleQuality}
          title={qualityTier === 0 ? t.export.quality0 : qualityTier === 1 ? t.export.quality1 : t.export.quality2}
        >
          <Layers size={12} />
          {qualityTier === 0 ? '3D' : qualityTier === 1 ? 'T1' : '2D'}
        </button>
        <button type="button" className="btn-hud" style={{ border: 'none', padding: '3px 5px' }} onClick={onOpenExport} title={t.export.png4k}>
          <Camera size={12} />
        </button>
        <button type="button" className="btn-hud" style={{ border: 'none', padding: '3px 5px' }} onClick={onOpenLegend} title={t.legend.title}>
          <HelpCircle size={12} />
        </button>
      </div>
    </div>
  );
}
