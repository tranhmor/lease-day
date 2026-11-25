import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AppMode,
  CameraKeyframe,
  Lang,
  LayerToggles,
  QualityTier,
  Scenario,
  ViewMode,
  VisualStyle,
  RoomShape,
  VizDataset,
} from '@/types/viz';
import { computeZoneStats, loadVizDataset, readMonthRoomStates } from '@/data/loader';
import { CHAPTERS, DEFAULT_LAYERS } from '@/chapters/script';
import { CityScene, type SceneHandle } from '@/scene/CityScene';
import { Fallback2DMap } from '@/scene/Fallback2DMap';
import { ClockHeader } from '@/components/ClockHeader';
import { LayerChips } from '@/components/LayerChips';
import { ScenarioTabs } from '@/components/ScenarioTabs';
import { VitalsPanel } from '@/components/VitalsPanel';
import { GapPanel } from '@/components/GapPanel';
import { RankPanel } from '@/components/RankPanel';
import { ReasonFeedPanel } from '@/components/ReasonFeedPanel';
import { TimelineBar } from '@/components/TimelineBar';
import { RoomDetailCard } from '@/components/RoomDetailCard';
import { TenantDetailCard } from '@/components/TenantDetailCard';
import { SplitHeaderBar, SplitOverlay } from '@/components/SplitOverlay';
import { ChapterBar } from '@/components/ChapterBar';
import { MoverProfileOverlay, VerdictOverlay } from '@/components/VerdictOverlay';
import { ExportModal } from '@/components/ExportModal';
import { LegendPopover } from '@/components/LegendPopover';
import { IntegrityFooter } from '@/components/IntegrityFooter';
import { toggleTheme } from '@/theme';

const MONTH_BASE_MS = 1700; // §4.3: 1 month ≈ 1.7s -> 36 months ≈ 60s

function parseInitialParams() {
  const sp = new URLSearchParams(window.location.search);
  const isExport = sp.get('export') === '1';
  const hasExplicitMonth = sp.get('month') !== null;
  const month = Math.max(1, Math.min(36, Number(sp.get('month')) || 1));
  const scenRaw = (sp.get('scen') || 'P').toUpperCase();
  const scen: Scenario = scenRaw === 'N' || scenRaw === 'S' || scenRaw === 'P' ? scenRaw : 'P';
  const chapterParam = sp.get('chapter');
  const chapter = chapterParam !== null ? Math.max(0, Math.min(CHAPTERS.length - 1, Number(chapterParam) || 0)) : null;
  const lang: Lang = sp.get('lang') === 'en' ? 'en' : 'zh';
  const styleRaw = (sp.get('style') || 'constellation').toLowerCase();
  const visualStyle: VisualStyle = styleRaw === 'terrain' ? 'terrain' : 'constellation';
  const roomShape: RoomShape = sp.get('shape') === 'bar' ? 'bar' : 'disc';
  const split = sp.get('split') === '1';
  const diff = sp.get('diff') === '1';
  const hideHud = sp.get('hud') === '0';
  const exportW = Number(sp.get('w')) || 3840;
  const exportH = Number(sp.get('h')) || 2160;
  return { isExport, hasExplicitMonth, month, scen, chapter, lang, visualStyle, roomShape, split, diff, hideHud, exportW, exportH };
}

export function App() {
  const init = useMemo(() => parseInitialParams(), []);
  const [dataset, setDataset] = useState<VizDataset | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [lang, setLang] = useState<Lang>(init.lang);
  const [mode, setMode] = useState<AppMode>(init.isExport ? 'export' : init.chapter !== null ? 'presentation' : 'explore');
  const [chapterIndex, setChapterIndex] = useState<number>(init.chapter ?? 1);
  const [scenario, setScenario] = useState<Scenario>(init.scen);
  const [month, setMonth] = useState<number>(init.month);
  const [playing, setPlaying] = useState<boolean>(!init.isExport && init.chapter === null && !init.hasExplicitMonth);
  const [speed, setSpeed] = useState<number>(1);
  const [viewMode, setViewMode] = useState<ViewMode>(init.split ? 'split' : init.diff ? 'diff' : 'single');
  const [visualStyle, setVisualStyle] = useState<VisualStyle>(init.visualStyle);
  const [roomShape, setRoomShape] = useState<RoomShape>(init.roomShape);
  const [splitRatio, setSplitRatio] = useState<number>(0.5);
  const [layers, setLayers] = useState<LayerToggles>(DEFAULT_LAYERS);
  const [qualityTier, setQualityTier] = useState<QualityTier>(0);
  const [autoDegradedNotice, setAutoDegradedNotice] = useState(false);

  const [cameraTarget, setCameraTarget] = useState<CameraKeyframe>(CHAPTERS[init.chapter ?? 1].camera);
  const [hideUI, setHideUI] = useState<boolean>(init.hideHud);
  const [expandFeed, setExpandFeed] = useState<boolean>(false);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null);
  const [hoveredVital, setHoveredVital] = useState<string | null>(null);
  const [shockwaveTime, setShockwaveTime] = useState<number>(0);
  const [showLegend, setShowLegend] = useState(false);
  const [showExport, setShowExport] = useState(false);

  const sceneHandleRef = useRef<SceneHandle | null>(null);
  const prevMonthRef = useRef<number>(month);

  // Load viz_data bundle once
  useEffect(() => {
    loadVizDataset('./viz_data')
      .then((ds) => setDataset(ds))
      .catch((err) => setLoadError(String(err)));
  }, []);

  // Apply export mode body class (hides cursor)
  useEffect(() => {
    document.body.classList.toggle('export-mode', mode === 'export');
    return () => document.body.classList.remove('export-mode');
  }, [mode]);

  // Apply a chapter preset
  const applyChapter = useCallback((idx: number) => {
    const ch = CHAPTERS[idx];
    if (!ch) return;
    setChapterIndex(idx);
    setScenario(ch.defaultScenario);
    setMonth(ch.monthStart);
    setPlaying(ch.autoPlay);
    setViewMode(ch.viewMode);
    setCameraTarget({ ...ch.camera });
    setLayers((prev) => ({ ...prev, ...ch.layers }));
    setExpandFeed(Boolean(ch.panels.expandFeed));
    setSelectedRoomId(null);
    setSelectedTenantId(null);
    setSelectedZone(null);
    if (ch.panels.triggerShockwave) {
      setShockwaveTime(performance.now() / 1000);
    }
  }, []);

  // Apply chapter preset on initial mount if URL requested a specific chapter
  useEffect(() => {
    if (init.chapter !== null) {
      const ch = CHAPTERS[init.chapter];
      if (ch) {
        setCameraTarget({ ...ch.camera });
        setLayers((prev) => ({ ...prev, ...ch.layers }));
        setExpandFeed(Boolean(ch.panels.expandFeed));
        if (!init.isExport) {
          setMonth(ch.monthStart);
          setViewMode(ch.viewMode);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Trigger announcement shockwave whenever crossing into M13 in P scenario
  useEffect(() => {
    const ann = dataset?.meta.event_months.announce ?? 13;
    if (scenario === 'P' && month === ann && prevMonthRef.current < ann) {
      setShockwaveTime(performance.now() / 1000);
    }
    prevMonthRef.current = month;
  }, [month, scenario, dataset]);

  // Playback timer (default 1.7s per month; honors chapter bounds in presentation mode)
  useEffect(() => {
    if (!playing || !dataset) return;
    const ch = mode === 'presentation' ? CHAPTERS[chapterIndex] : null;
    const intervalMs = MONTH_BASE_MS / speed;
    const timer = window.setInterval(() => {
      setMonth((m) => {
        if (ch) {
          if (m >= ch.monthEnd) {
            setPlaying(false);
            return ch.monthEnd;
          }
          return m + 1;
        }
        return m >= dataset.meta.months ? 1 : m + 1;
      });
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [playing, speed, mode, chapterIndex, dataset]);

  // Keyboard shortcuts (§7.2): Space, Arrows, 1/2/3, D, F, H, Esc
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        if (mode === 'presentation') {
          applyChapter(Math.min(CHAPTERS.length - 1, chapterIndex + 1));
        } else {
          setPlaying(false);
          setMonth((m) => Math.min(36, m + 1));
        }
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        if (mode === 'presentation') {
          applyChapter(Math.max(0, chapterIndex - 1));
        } else {
          setPlaying(false);
          setMonth((m) => Math.max(1, m - 1));
        }
      } else if (e.key === '1') {
        setViewMode('single');
        setScenario('N');
      } else if (e.key === '2') {
        setViewMode('single');
        setScenario('S');
      } else if (e.key === '3') {
        setViewMode('single');
        setScenario('P');
      } else if (e.key === 'd' || e.key === 'D') {
        setViewMode((vm) => (vm === 'split' ? 'single' : 'split'));
      } else if (e.key === 'v' || e.key === 'V') {
        setVisualStyle((s) => (s === 'constellation' ? 'terrain' : 'constellation'));
      } else if (e.key === 'b' || e.key === 'B') {
        setRoomShape((s) => (s === 'disc' ? 'bar' : 'disc'));
      } else if (e.key === 't' || e.key === 'T') {
        toggleTheme();
      } else if (e.key === 'h' || e.key === 'H') {
        setHideUI((h) => !h);
      } else if (e.key === 'f' || e.key === 'F') {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen?.().catch(() => {});
        } else {
          document.exitFullscreen?.().catch(() => {});
        }
      } else if (e.key === 'Escape') {
        if (selectedTenantId !== null) setSelectedTenantId(null);
        else if (selectedRoomId !== null) setSelectedRoomId(null);
        else if (mode === 'presentation') setMode('explore');
        else if (hideUI) setHideUI(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode, chapterIndex, applyChapter, selectedRoomId, selectedTenantId, hideUI]);

  // Expose programmatic export helper on window for headless 4K Playwright/browser batch capture!
  useEffect(() => {
    (window as any).__leaseDayExportPNG = (w = init.exportW, h = init.exportH) => {
      if (!dataset || !sceneHandleRef.current) return null;
      const wm = [
        ...(dataset.meta.is_illustrative ? ['示意数据，非实验结果 / ILLUSTRATIVE DATA'] : []),
        `Lease Day v${dataset.meta.version} · M${String(month).padStart(2, '0')}/36 · ${
          viewMode === 'split' ? 'Split S | P' : `Scenario ${scenario}`
        } · Seed #${dataset.meta.default_seed} · ${dataset.meta.source_label}`,
      ];
      return sceneHandleRef.current.exportPNG(w, h, wm);
    };
  }, [dataset, month, scenario, viewMode, init.exportW, init.exportH]);

  const seed = dataset?.meta.default_seed ?? 0;
  const runActive = dataset ? dataset.runs[`${scenario}_${seed}`] ?? Object.values(dataset.runs)[0] : null;
  const runP = dataset ? dataset.runs[`P_${seed}`] ?? runActive : null;
  const runS = dataset ? dataset.runs[`S_${seed}`] ?? runActive : null;

  const statesActive = useMemo(() => {
    if (!dataset || !runActive) return [];
    return readMonthRoomStates(runActive.roomStatesBuffer, month, dataset.rooms.length);
  }, [dataset, runActive, month]);

  const zoneStats = useMemo(() => {
    if (!dataset || !statesActive.length) return {};
    return computeZoneStats(dataset.rooms, statesActive);
  }, [dataset, statesActive]);

  const flyToZone = useCallback(
    (zoneId: string | null) => {
      setSelectedZone(zoneId);
      if (!dataset) return;
      if (!zoneId) {
        setCameraTarget({ ...CHAPTERS[1].camera });
        return;
      }
      const z = dataset.zoneById[zoneId];
      if (!z) return;
      setCameraTarget({
        position: [z.x - 1.5, 11.5, z.z + 14.5],
        target: [z.x, 0.4, z.z],
        fov: 34,
      });
    },
    [dataset]
  );

  const handleSelectRoom = useCallback(
    (roomId: number) => {
      setSelectedTenantId(null);
      setSelectedRoomId(roomId);
      if (!dataset) return;
      const r = dataset.rooms[roomId];
      if (!r) return;
      setCameraTarget({
        position: [r.layout_xy[0] - 1.2, 9.2, r.layout_xy[1] + 11.8],
        target: [r.layout_xy[0], 0.8, r.layout_xy[1]],
        fov: 33,
      });
    },
    [dataset]
  );

  if (loadError) {
    return (
      <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, padding: 32 }}>
        <div style={{ fontSize: 18, color: 'var(--p)' }}>Failed to load viz_data/</div>
        <pre className="mono" style={{ fontSize: 12, color: 'var(--sub)' }}>{loadError}</pre>
      </div>
    );
  }

  if (!dataset || !runActive || !runP || !runS) {
    return (
      <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
        <div className="serif" style={{ fontSize: 20 }}>到期日 · Lease Day</div>
        <div style={{ fontSize: 12, color: 'var(--sub)' }}>Loading 3D urban stage & simulation telemetry…</div>
      </div>
    );
  }

  const activeChapter = mode === 'presentation' ? CHAPTERS[chapterIndex] : null;
  const showHUD = !hideUI && (!activeChapter || activeChapter.panels.showHUD);
  const isolateTreated = Boolean(activeChapter?.panels.isolateTreated);
  const curMonthly = runActive.monthly[month - 1];
  const prevMonthly = runActive.monthly[Math.max(0, month - 2)];
  const llmCalls = runActive.decisions.llm_calls_by_month[String(month)] ?? 0;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      {/* 3D WebGL City Scene OR Quality Tier 2 2D Fallback */}
      {qualityTier === 2 ? (
        <Fallback2DMap
          dataset={dataset}
          scenario={scenario}
          seed={seed}
          month={month}
          layers={layers}
          lang={lang}
          selectedRoomId={selectedRoomId}
          onSelectRoom={handleSelectRoom}
          onSelectZone={flyToZone}
        />
      ) : (
        <CityScene
          dataset={dataset}
          scenario={scenario}
          seed={seed}
          month={month}
          viewMode={viewMode}
          visualStyle={visualStyle}
          roomShape={roomShape}
          splitRatio={splitRatio}
          layers={layers}
          lang={lang}
          qualityTier={qualityTier}
          cameraTarget={cameraTarget}
          interactiveOrbit={mode !== 'presentation' || chapterIndex !== 0}
          isolateTreated={isolateTreated}
          highlightZone={selectedZone}
          selectedRoomId={selectedRoomId}
          hoveredVital={hoveredVital}
          shockwaveTime={shockwaveTime}
          showLabels={showHUD || mode === 'export'}
          onSelectRoom={handleSelectRoom}
          onSelectZone={flyToZone}
          onAutoDegrade={(tier) => {
            setQualityTier(tier);
            setAutoDegradedNotice(true);
          }}
          sceneHandleRef={sceneHandleRef}
        />
      )}

      {/* Split-Screen Draggable Curtain Divider (§7.3) */}
      {viewMode === 'split' && !hideUI && (
        <SplitOverlay splitRatio={splitRatio} lang={lang} onChangeRatio={setSplitRatio} />
      )}

      {/* Chapter 0 Fullscreen Intro Title */}
      {!hideUI && mode === 'presentation' && chapterIndex === 0 && (
        <ChapterBar
          mode={mode}
          chapterIndex={0}
          lang={lang}
          onSelectChapter={applyChapter}
          onExitPresentation={() => {
            setMode('explore');
            setExpandFeed(false);
            setCameraTarget({ ...CHAPTERS[1].camera });
          }}
        />
      )}

      {/* Responsive 3-Column Cockpit HUD (zero overlaps across laptop 1024px to 4K!) */}
      {showHUD && (
        <div
          style={{
            position: 'absolute',
            inset: '16px 20px 38px 20px',
            display: 'flex',
            gap: 16,
            pointerEvents: 'none',
            zIndex: 22,
          }}
        >
          {/* LEFT COLUMN: Clock -> Vitals -> P - S Gap */}
          <div
            style={{
              width: 'clamp(260px, 20vw, 330px)',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: 10,
              minHeight: 0,
            }}
          >
            <ClockHeader month={month} scenario={scenario} meta={dataset.meta} lang={lang} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <VitalsPanel
                current={curMonthly}
                prev={prevMonthly}
                llmCalls={llmCalls}
                isIllustrative={dataset.meta.is_illustrative}
                lang={lang}
                onHoverMetric={setHoveredVital}
              />
              <GapPanel
                monthlyCI={dataset.monthlyCI}
                month={month}
                announceMonth={dataset.meta.event_months.announce}
                openMonth={dataset.meta.event_months.open}
                lang={lang}
                onClickSplit={() => setViewMode((vm) => (vm === 'split' ? 'single' : 'split'))}
              />
            </div>
          </div>

          {/* CENTER COLUMN: Layer Chips + Active Overlay/Modal (top) -> Clear 3D Stage -> Chapter Bar + Timeline (bottom) */}
          <div
            style={{
              flex: 1,
              minWidth: 0,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: 8,
              minHeight: 0,
            }}
          >
            {/* Top Center Stack */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, flexShrink: 1, overflow: 'hidden' }}>
              <LayerChips
                layers={layers}
                lang={lang}
                onToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
              />

              {viewMode === 'split' && (
                <SplitHeaderBar
                  lang={lang}
                  onSwitchToDiff={() => setViewMode('diff')}
                  onExit={() => setViewMode('single')}
                />
              )}

              {/* Active Center Panel/Modal — constrained to remaining space so it NEVER touches bottom bar! */}
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                {selectedRoomId !== null && selectedTenantId === null && (
                  <RoomDetailCard
                    dataset={dataset}
                    roomId={selectedRoomId}
                    scenario={scenario}
                    seed={seed}
                    month={month}
                    lang={lang}
                    onClose={() => setSelectedRoomId(null)}
                    onOpenTenant={(tid) => setSelectedTenantId(tid)}
                  />
                )}
                {selectedTenantId !== null && (
                  <TenantDetailCard
                    dataset={dataset}
                    tenantId={selectedTenantId}
                    scenario={scenario}
                    seed={seed}
                    lang={lang}
                    onBackToRoom={() => setSelectedTenantId(null)}
                    onClose={() => {
                      setSelectedTenantId(null);
                      setSelectedRoomId(null);
                    }}
                    onSelectRoom={(rid) => {
                      setSelectedTenantId(null);
                      handleSelectRoom(rid);
                    }}
                  />
                )}
                {selectedRoomId === null && selectedTenantId === null && activeChapter?.panels.showMoverProfile && (
                  <MoverProfileOverlay monthlyP={runP.monthly} monthlyS={runS.monthly} lang={lang} />
                )}
                {selectedRoomId === null && selectedTenantId === null && activeChapter?.panels.showVerdicts && (
                  <VerdictOverlay verdicts={dataset.verdicts} lang={lang} />
                )}
              </div>
            </div>

            {/* Bottom Center Stack: Chapter Bar -> Timeline */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0 }}>
              {mode === 'presentation' && chapterIndex > 0 && (
                <ChapterBar
                  mode={mode}
                  chapterIndex={chapterIndex}
                  lang={lang}
                  onSelectChapter={applyChapter}
                  onExitPresentation={() => {
                    setMode('explore');
                    setExpandFeed(false);
                    setCameraTarget({ ...CHAPTERS[1].camera });
                  }}
                />
              )}
              <TimelineBar
                monthlyCI={dataset.monthlyCI}
                month={month}
                scenario={scenario}
                playing={playing}
                speed={speed}
                announceMonth={dataset.meta.event_months.announce}
                openMonth={dataset.meta.event_months.open}
                lang={lang}
                onTogglePlay={() => setPlaying((p) => !p)}
                onCycleSpeed={() => setSpeed((s) => (s === 1 ? 2 : s === 2 ? 0.5 : 1))}
                onSeekMonth={(m) => {
                  setPlaying(false);
                  setMonth(m);
                }}
              />
            </div>
          </div>

          {/* RIGHT COLUMN: Scenario Tabs -> Top 6 Rank -> Landlord Reason Feed */}
          <div
            style={{
              width: expandFeed ? 'clamp(320px, 38vw, 680px)' : 'clamp(290px, 23vw, 380px)',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              minHeight: 0,
              transition: 'width 0.3s ease',
            }}
          >
            <ScenarioTabs
              scenario={scenario}
              mode={mode}
              viewMode={viewMode}
              visualStyle={visualStyle}
              lang={lang}
              qualityTier={qualityTier}
              highlightTabs={Boolean(activeChapter?.panels.highlightTabs)}
              onScenarioChange={(sc) => setScenario(sc)}
              onToggleMode={() => {
                if (mode === 'presentation') {
                  setMode('explore');
                  setExpandFeed(false);
                } else {
                  setMode('presentation');
                  applyChapter(chapterIndex);
                }
              }}
              onViewModeChange={(vm) => setViewMode(vm)}
              onVisualStyleChange={(st) => setVisualStyle(st)}
              roomShape={roomShape}
              onRoomShapeChange={setRoomShape}
              onToggleLang={() => setLang((l) => (l === 'zh' ? 'en' : 'zh'))}
              onCycleQuality={() => {
                setAutoDegradedNotice(false);
                setQualityTier((q) => ((q + 1) % 3) as QualityTier);
              }}
              onOpenLegend={() => {
                setShowExport(false);
                setShowLegend((v) => !v);
              }}
              onOpenExport={() => {
                setShowLegend(false);
                setShowExport((v) => !v);
              }}
            />

            {!expandFeed && (
              <RankPanel
                zones={dataset.zones}
                zoneStats={zoneStats}
                selectedZone={selectedZone}
                lang={lang}
                onSelectZone={flyToZone}
              />
            )}

            <ReasonFeedPanel
              decisionsPayload={runActive.decisions}
              month={month}
              mentionKeywords={dataset.meta.mention_keywords}
              zoneById={dataset.zoneById}
              filterZone={selectedZone}
              expanded={expandFeed}
              lang={lang}
              onToggleExpand={() => setExpandFeed((v) => !v)}
              onSelectDecisionRoom={(rid) => handleSelectRoom(rid)}
            />
          </div>
        </div>
      )}

      {/* Legend & Export Popovers */}
      {showLegend && !hideUI && <LegendPopover lang={lang} onClose={() => setShowLegend(false)} />}
      {showExport && !hideUI && (
        <ExportModal
          meta={dataset.meta}
          month={month}
          scenario={scenario}
          viewMode={viewMode}
          lang={lang}
          sceneHandleRef={sceneHandleRef}
          onClose={() => setShowExport(false)}
        />
      )}

      {/* Persistent Academic Integrity Watermark Footer (§9) */}
      <IntegrityFooter
        meta={dataset.meta}
        monthlyCI={dataset.monthlyCI}
        lang={lang}
        autoDegradedNotice={autoDegradedNotice}
        onRestoreQuality={() => {
          setQualityTier(0);
          setAutoDegradedNotice(false);
        }}
      />
    </div>
  );
}
export default App;
