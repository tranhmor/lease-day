import type React from 'react';
import { BarChart3, Camera, CircleDot, Columns2, Compass, HelpCircle, Moon, Mountain, Network, Presentation, Sliders, Sun } from 'lucide-react';
import { toggleTheme, useTheme } from '@/theme';
import type { AppMode, Lang, QualityTier, RoomShape, Scenario, ViewMode, VisualStyle } from '@/types/viz';
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
  roomShape: RoomShape;
  onRoomShapeChange: (s: RoomShape) => void;
  onToggleLang: () => void;
  onCycleQuality: () => void;
  onOpenLegend: () => void;
  onOpenExport: () => void;
}

const SC_COLORS: Record<Scenario, string> = {
  N: 'var(--n)',
  S: 'var(--s)',
  P: 'var(--p)',
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
  roomShape,
  onRoomShapeChange,
  onToggleLang,
  onCycleQuality,
  onOpenLegend,
  onOpenExport,
}: ScenarioTabsProps) {
  const t = getDict(lang);
  const theme = useTheme();

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
      {/* N | S | P */}
      <div
        className="hud-panel"
        style={{
          display: 'flex',
          padding: 0,
          overflow: 'hidden',
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
                background: on ? 'color-mix(in srgb, var(--cool) 10%, transparent)' : 'transparent',
                color: on ? 'var(--text)' : 'var(--sub)',
                padding: '10px 4px',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: on ? 600 : 400,
                fontFamily: 'var(--font-sans)',
                transition: 'all 0.2s',
              }}
            >
              <span>{sc}</span>
              <small style={{ fontSize: 10.5, marginLeft: 4, opacity: 0.78 }}>{t.scenarios[sc].short}</small>
            </button>
          );
        })}
      </div>

      {/* Row 1: visual style (V) */}
      <div style={grid2}>
        <button
          type="button"
          className={`btn-hud ${visualStyle === 'constellation' ? 'amber-active' : ''}`}
          style={cell}
          onClick={() => onVisualStyleChange('constellation')}
          title="V"
        >
          <Network size={12} />
          {t.styles.constellation}
        </button>
        <button
          type="button"
          className={`btn-hud ${visualStyle === 'terrain' ? 'amber-active' : ''}`}
          style={cell}
          onClick={() => onVisualStyleChange('terrain')}
          title="V"
        >
          <Mountain size={12} />
          {t.styles.terrain}
        </button>
      </div>

      {/* Row 2: comparison views (D) */}
      <div style={grid2}>
        <button
          type="button"
          className={`btn-hud ${viewMode === 'split' ? 'amber-active' : ''}`}
          style={cell}
          onClick={() => onViewModeChange(viewMode === 'split' ? 'single' : 'split')}
          title="D"
        >
          <Columns2 size={12} />
          {t.modes.split}
        </button>
        <button
          type="button"
          className={`btn-hud ${viewMode === 'diff' ? 'amber-active' : ''}`}
          style={cell}
          onClick={() => onViewModeChange(viewMode === 'diff' ? 'single' : 'diff')}
        >
          <Sliders size={12} />
          {t.modes.diff}
        </button>
      </div>

      {/* Row 3: mode + room glyph | utilities */}
      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
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
          className={`btn-hud ${roomShape === 'bar' ? 'active' : ''}`}
          onClick={() => onRoomShapeChange(roomShape === 'disc' ? 'bar' : 'disc')}
          title={`${t.shapes.hint} (B)`}
        >
          {roomShape === 'bar' ? <BarChart3 size={12} /> : <CircleDot size={12} />}
          {roomShape === 'bar' ? t.shapes.bar : t.shapes.disc}
        </button>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="btn-hud"
          style={icon}
          onClick={toggleTheme}
          title={`${theme === 'dark' ? t.theme.toLight : t.theme.toDark} (T)`}
        >
          {theme === 'dark' ? <Sun size={12} /> : <Moon size={12} />}
        </button>
        <button type="button" className="btn-hud" style={icon} onClick={onToggleLang} title="中文 / English">
          {lang === 'zh' ? 'EN' : '中'}
        </button>
        <button
          type="button"
          className={`btn-hud ${qualityTier > 0 ? 'amber-active' : ''}`}
          style={icon}
          onClick={onCycleQuality}
          title={qualityTier === 0 ? t.export.quality0 : qualityTier === 1 ? t.export.quality1 : t.export.quality2}
        >
          {qualityTier === 0 ? '3D' : qualityTier === 1 ? 'T1' : '2D'}
        </button>
        <button type="button" className="btn-hud" style={icon} onClick={onOpenExport} title={t.export.png4k}>
          <Camera size={12} />
        </button>
        <button type="button" className="btn-hud" style={icon} onClick={onOpenLegend} title={t.legend.title}>
          <HelpCircle size={12} />
        </button>
      </div>
    </div>
  );
}

const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 };
const cell: React.CSSProperties = { justifyContent: 'center', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' };
const icon: React.CSSProperties = { padding: '5px 0', width: 28, justifyContent: 'center', fontSize: 11 };
