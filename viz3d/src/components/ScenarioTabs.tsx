import { Camera, Columns2, Compass, Globe, HelpCircle, Layers, Mountain, Network, Presentation, Sliders } from 'lucide-react';
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
  N: '#8A94A8',
  S: '#4EA8FF',
  P: '#FF6B57',
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

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
      {/* N | S | P Tabs */}
      <div
        className="hud-panel"
        style={{
          display: 'flex',
          padding: 0,
          overflow: 'hidden',
          boxShadow: highlightTabs ? '0 0 22px rgba(255, 176, 46, 0.45)' : undefined,
          borderColor: highlightTabs ? 'var(--announce)' : undefined,
        }}
      >
        {(['N', 'S', 'P'] as Scenario[]).map((sc) => {
          const on = scenario === sc && viewMode === 'single';
          return (
            <button
              key={sc}
              type="button"
              title={t.scenarios[sc].desc}
              onClick={() => {
                if (viewMode !== 'single') onViewModeChange('single');
                onScenarioChange(sc);
              }}
              style={{
                flex: 1,
                border: 'none',
                borderBottom: `2.5px solid ${on ? SC_COLORS[sc] : 'transparent'}`,
                background: on ? 'rgba(95, 180, 255, 0.1)' : 'transparent',
                color: on ? 'var(--text)' : 'var(--sub)',
                padding: '10px 4px',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: on ? 600 : 400,
                transition: 'all 0.2s',
              }}
            >
              <span>{sc}</span>
              <small style={{ fontSize: 10, marginLeft: 4, opacity: 0.78 }}>{t.scenarios[sc].short}</small>
            </button>
          );
        })}
      </div>

      {/* Visual Style Switcher: Constellation vs Bid-Rent Terrain (Shortcut: V) */}
      <div style={{ display: 'flex', gap: 5 }}>
        <button
          type="button"
          className={`btn-hud ${visualStyle === 'constellation' ? 'amber-active' : ''}`}
          style={{ flex: 1, justifyContent: 'center' }}
          onClick={() => onVisualStyleChange('constellation')}
          title="Shortcut: V"
        >
          <Network size={12} />
          {t.styles.constellation}
        </button>
        <button
          type="button"
          className={`btn-hud ${visualStyle === 'terrain' ? 'amber-active' : ''}`}
          style={{ flex: 1, justifyContent: 'center' }}
          onClick={() => onVisualStyleChange('terrain')}
          title="Shortcut: V"
        >
          <Mountain size={12} />
          {t.styles.terrain}
        </button>
      </div>

      {/* Compact Control Strip */}
      <div style={{ display: 'flex', gap: 5, justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <button
          type="button"
          className={`btn-hud ${mode === 'presentation' ? 'amber-active' : 'active'}`}
          onClick={onToggleMode}
          title={mode === 'presentation' ? t.modes.explore : t.modes.presentation}
        >
          {mode === 'presentation' ? <Presentation size={12} /> : <Compass size={12} />}
          {mode === 'presentation' ? t.modes.presentation : t.modes.explore}
        </button>

        <button
          type="button"
          className={`btn-hud ${viewMode === 'split' ? 'amber-active' : ''}`}
          onClick={() => onViewModeChange(viewMode === 'split' ? 'single' : 'split')}
          title="Shortcut: D"
        >
          <Columns2 size={12} />
          {t.modes.split}
        </button>

        <button
          type="button"
          className={`btn-hud ${viewMode === 'diff' ? 'amber-active' : ''}`}
          onClick={() => onViewModeChange(viewMode === 'diff' ? 'single' : 'diff')}
        >
          <Sliders size={12} />
          {t.modes.diff}
        </button>

        <div style={{ display: 'flex', gap: 4 }}>
          <button type="button" className="btn-hud" onClick={onToggleLang} title="Switch Chinese / English">
            <Globe size={12} />
            {lang === 'zh' ? 'EN' : '中文'}
          </button>
          <button
            type="button"
            className={`btn-hud ${qualityTier > 0 ? 'amber-active' : ''}`}
            onClick={onCycleQuality}
            title={qualityTier === 0 ? t.export.quality0 : qualityTier === 1 ? t.export.quality1 : t.export.quality2}
          >
            <Layers size={12} />
            {qualityTier === 0 ? '3D' : qualityTier === 1 ? 'T1' : '2D'}
          </button>
          <button type="button" className="btn-hud" onClick={onOpenExport} title={t.export.png4k}>
            <Camera size={12} />
          </button>
          <button type="button" className="btn-hud" onClick={onOpenLegend} title={t.legend.title}>
            <HelpCircle size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
