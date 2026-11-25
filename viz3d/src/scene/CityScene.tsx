import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import gsap from 'gsap';
import type {
  CameraKeyframe,
  Lang,
  LayerToggles,
  QualityTier,
  RoomMonthState,
  Scenario,
  ViewMode,
  VisualStyle,
  VizDataset,
} from '@/types/viz';
import { computeZoneStats, readMonthRoomStates } from '@/data/loader';
import { GroundLayer } from './GroundLayer';
import { BasemapLayer } from './BasemapLayer';
import { MetroLayer } from './MetroLayer';
import { EastExpressLayer } from './EastExpressLayer';
import { RoomPillarsLayer } from './RoomPillarsLayer';
import { ZoneRipplesLayer } from './ZoneRipplesLayer';
import { CommuteParticles } from './CommuteParticles';
import { MoveArcsLayer } from './MoveArcsLayer';
import { DecisionPulsesLayer } from './DecisionPulsesLayer';
import { ZoneLabelsLayer } from './ZoneLabelsLayer';
import { LandlordConstellationLayer } from './LandlordConstellationLayer';
import { SpatialMindCallouts } from './SpatialMindCallouts';
import { BidRentTerrainLayer } from './BidRentTerrainLayer';
import { useScenePalette } from '@/theme';
import { PostEffects } from './PostEffects';

export interface SceneHandle {
  flyTo: (kf: CameraKeyframe, duration?: number) => void;
  exportPNG: (width: number, height: number, watermarkLines?: string[]) => string | null;
  getCanvas: () => HTMLCanvasElement | null;
}

interface CitySceneProps {
  dataset: VizDataset;
  scenario: Scenario;
  seed: number;
  month: number;
  viewMode: ViewMode;
  visualStyle: VisualStyle;
  splitRatio: number; // 0.1..0.9 curtain divider for split S | P
  layers: LayerToggles;
  lang: Lang;
  qualityTier: QualityTier;
  cameraTarget: CameraKeyframe;
  interactiveOrbit: boolean;
  isolateTreated: boolean;
  highlightZone: string | null;
  selectedRoomId: number | null;
  hoveredVital: string | null;
  shockwaveTime: number;
  showLabels: boolean;
  onSelectRoom: (roomId: number) => void;
  onSelectZone: (zoneId: string) => void;
  onAutoDegrade: (newTier: QualityTier) => void;
  sceneHandleRef: React.MutableRefObject<SceneHandle | null>;
}

/**
 * Monitors average FPS during the first 3 seconds after startup; triggers Quality Tier downgrade if < 30 fps (§8.3).
 */
function FPSGuard({ qualityTier, onAutoDegrade }: { qualityTier: QualityTier; onAutoDegrade: (t: QualityTier) => void }) {
  const startRef = useRef<number | null>(null);
  const framesRef = useRef(0);
  const checkedRef = useRef(false);

  useFrame(() => {
    if (checkedRef.current || qualityTier >= 2) return;
    const now = performance.now();
    if (startRef.current === null) {
      startRef.current = now;
      framesRef.current = 0;
      return;
    }
    framesRef.current += 1;
    const elapsed = (now - startRef.current) / 1000;
    if (elapsed >= 3.2) {
      checkedRef.current = true;
      const avgFps = framesRef.current / elapsed;
      if (avgFps < 28 && qualityTier < 2) {
        onAutoDegrade((qualityTier + 1) as QualityTier);
      }
    }
  });

  return null;
}

interface InnerSceneProps extends CitySceneProps {}

function InnerCityScene(props: InnerSceneProps) {
  const {
    dataset,
    scenario,
    seed,
    month,
    viewMode,
    visualStyle,
    splitRatio,
    layers,
    lang,
    qualityTier,
    cameraTarget,
    interactiveOrbit,
    isolateTreated,
    highlightZone,
    selectedRoomId,
    hoveredVital,
    shockwaveTime,
    showLabels,
    onSelectRoom,
    onSelectZone,
    onAutoDegrade,
    sceneHandleRef,
  } = props;

  const { gl, scene, camera, size } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const lastInteractRef = useRef<number>(performance.now());
  const isTweeningRef = useRef(false);

  const groupSRef = useRef<THREE.Group>(null);
  const groupPRef = useRef<THREE.Group>(null);

  // Read binary room states for active scenario (plus S & P for split/diff modes)
  const runActive = dataset.runs[`${scenario}_${seed}`] ?? dataset.runs[`P_${dataset.meta.default_seed}`];
  const runS = dataset.runs[`S_${seed}`] ?? runActive;
  const runP = dataset.runs[`P_${seed}`] ?? runActive;

  const statesActive: RoomMonthState[] = useMemo(
    () => readMonthRoomStates(runActive.roomStatesBuffer, month, dataset.rooms.length),
    [runActive, month, dataset.rooms.length]
  );
  const statesS: RoomMonthState[] = useMemo(
    () => readMonthRoomStates(runS.roomStatesBuffer, month, dataset.rooms.length),
    [runS, month, dataset.rooms.length]
  );
  const statesP: RoomMonthState[] = useMemo(
    () => readMonthRoomStates(runP.roomStatesBuffer, month, dataset.rooms.length),
    [runP, month, dataset.rooms.length]
  );

  const zoneStatsActive = useMemo(() => computeZoneStats(dataset.rooms, statesActive), [dataset.rooms, statesActive]);
  const zoneStatsS = useMemo(() => computeZoneStats(dataset.rooms, statesS), [dataset.rooms, statesS]);
  const zoneStatsP = useMemo(() => computeZoneStats(dataset.rooms, statesP), [dataset.rooms, statesP]);

  // Current P - S gap for ripple intensity
  const psGap = useMemo(() => {
    const arr = dataset.monthlyCI.paired_diffs?.P_minus_S?.rent_index_treated;
    return arr && arr[month - 1] ? arr[month - 1][0] : 0;
  }, [dataset.monthlyCI, month]);

  const flyTo = (kf: CameraKeyframe, duration = 1.65) => {
    const cam = camera as THREE.PerspectiveCamera;
    const ctrl = controlsRef.current;
    gsap.killTweensOf(cam.position);
    gsap.killTweensOf(cam);
    if (ctrl) gsap.killTweensOf(ctrl.target);

    isTweeningRef.current = true;
    gsap.to(cam.position, {
      x: kf.position[0],
      y: kf.position[1],
      z: kf.position[2],
      duration,
      ease: 'power2.inOut',
      onComplete: () => {
        isTweeningRef.current = false;
      },
    });
    gsap.to(cam, {
      fov: kf.fov,
      duration,
      ease: 'power2.inOut',
      onUpdate: () => cam.updateProjectionMatrix(),
    });
    if (ctrl) {
      gsap.to(ctrl.target, {
        x: kf.target[0],
        y: kf.target[1],
        z: kf.target[2],
        duration,
        ease: 'power2.inOut',
        onUpdate: () => ctrl.update(),
      });
    }
  };

  // Animate camera whenever cameraTarget prop updates
  useEffect(() => {
    flyTo(cameraTarget, 1.7);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraTarget]);

  // Expose imperative handle (flyTo + true offscreen 4K PNG export with burned-in academic watermark!)
  useEffect(() => {
    sceneHandleRef.current = {
      flyTo,
      getCanvas: () => gl.domElement,
      exportPNG: (targetW: number, targetH: number, watermarkLines: string[] = []) => {
        const prevW = gl.domElement.width;
        const prevH = gl.domElement.height;
        const prevPR = gl.getPixelRatio();
        const cam = camera as THREE.PerspectiveCamera;
        const prevAspect = cam.aspect;

        try {
          gl.setPixelRatio(1);
          gl.setSize(targetW, targetH, false);
          cam.aspect = targetW / targetH;
          cam.updateProjectionMatrix();

          if (viewMode === 'split' && groupSRef.current && groupPRef.current) {
            const splitX = Math.round(targetW * splitRatio);
            gl.setScissorTest(true);
            gl.setViewport(0, 0, targetW, targetH);

            groupSRef.current.visible = true;
            groupPRef.current.visible = false;
            gl.setScissor(0, 0, splitX, targetH);
            gl.render(scene, camera);

            groupSRef.current.visible = false;
            groupPRef.current.visible = true;
            gl.setScissor(splitX, 0, targetW - splitX, targetH);
            gl.render(scene, camera);

            gl.setScissorTest(false);
          } else {
            gl.render(scene, camera);
          }

          // Composite onto 2D canvas to burn in split divider & academic integrity watermark (§9.1)
          const out = document.createElement('canvas');
          out.width = targetW;
          out.height = targetH;
          const ctx = out.getContext('2d');
          if (!ctx) return gl.domElement.toDataURL('image/png');
          ctx.drawImage(gl.domElement, 0, 0, targetW, targetH);

          const scale = targetW / 1920;
          if (viewMode === 'split') {
            const dx = Math.round(targetW * splitRatio);
            ctx.strokeStyle = '#FFB02E';
            ctx.lineWidth = Math.max(2, 2 * scale);
            ctx.beginPath();
            ctx.moveTo(dx, 0);
            ctx.lineTo(dx, targetH);
            ctx.stroke();

            ctx.font = `600 ${Math.round(22 * scale)}px "JetBrains Mono", sans-serif`;
            ctx.fillStyle = '#4EA8FF';
            ctx.fillText('S · Sudden Open (Uninformed)', Math.round(36 * scale), Math.round(52 * scale));
            ctx.fillStyle = '#FF6B57';
            ctx.textAlign = 'right';
            ctx.fillText('P · Pre-Announced (M13 Notice)', targetW - Math.round(36 * scale), Math.round(52 * scale));
            ctx.textAlign = 'left';
          }

          // Bottom-left metadata + watermark bar
          if (watermarkLines.length > 0) {
            const padX = Math.round(28 * scale);
            const padY = Math.round(24 * scale);
            ctx.font = `500 ${Math.round(16 * scale)}px "Source Han Sans SC", "PingFang SC", sans-serif`;
            ctx.fillStyle = 'rgba(11, 17, 28, 0.72)';
            const barH = Math.round((watermarkLines.length * 24 + 18) * scale);
            ctx.fillRect(0, targetH - barH, targetW, barH);
            ctx.fillStyle = '#CBD6E8';
            watermarkLines.forEach((line, i) => {
              ctx.fillText(line, padX, targetH - barH + padY + i * Math.round(24 * scale));
            });
          }

          return out.toDataURL('image/png');
        } finally {
          gl.setPixelRatio(prevPR);
          gl.setSize(prevW / prevPR, prevH / prevPR, false);
          cam.aspect = prevAspect;
          cam.updateProjectionMatrix();
        }
      },
    };
  });

  // Idle breathing orbit after 20s inactivity (~6°/min = 0.001745 rad/s, §5.3)
  useFrame((_, delta) => {
    const ctrl = controlsRef.current;
    if (!ctrl || isTweeningRef.current) return;
    const idleSec = (performance.now() - lastInteractRef.current) / 1000;
    if (idleSec > 20) {
      const angle = delta * ((6 * Math.PI) / 180 / 60);
      const offset = camera.position.clone().sub(ctrl.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), angle);
      camera.position.copy(ctrl.target).add(offset);
      ctrl.update();
    }
  });

  // Synchronized single-canvas scissor rendering for Split-Screen S | P (§7.3)
  useFrame(() => {
    if (viewMode !== 'split' || !groupSRef.current || !groupPRef.current) return;
    const w = size.width;
    const h = size.height;
    const splitX = Math.max(1, Math.min(w - 1, Math.round(w * splitRatio)));

    gl.autoClear = true;
    gl.setViewport(0, 0, w, h);
    gl.setScissorTest(true);

    // Left half = S (Sudden Open)
    groupSRef.current.visible = true;
    groupPRef.current.visible = false;
    gl.setScissor(0, 0, splitX, h);
    gl.render(scene, camera);

    // Right half = P (Pre-Announced)
    groupSRef.current.visible = false;
    groupPRef.current.visible = true;
    gl.setScissor(splitX, 0, w - splitX, h);
    gl.render(scene, camera);

    gl.setScissorTest(false);
  }, viewMode === 'split' ? 1 : 0);

  const activeAnnounced = scenario === 'P' && month >= dataset.meta.event_months.announce;
  const activeOpened = scenario !== 'N' && month >= dataset.meta.event_months.open;
  const isConstellation = visualStyle === 'constellation';
  const pal = useScenePalette();
  const isTerrain = visualStyle === 'terrain';

  return (
    <>
      <color attach="background" args={[pal.bg]} />
      {qualityTier === 0 && <fogExp2 attach="fog" args={[pal.bg, pal.isLight ? 0.009 : 0.0135]} />}

      <ambientLight intensity={0.85} color={pal.isLight ? '#FFFFFF' : '#B8D4F5'} />

      <OrbitControls
        ref={controlsRef}
        makeDefault
        enabled={interactiveOrbit}
        enableDamping
        dampingFactor={0.07}
        minPolarAngle={(22 * Math.PI) / 180}
        maxPolarAngle={(78 * Math.PI) / 180}
        minDistance={8}
        maxDistance={68}
        onStart={() => {
          lastInteractRef.current = performance.now();
        }}
        onChange={() => {
          lastInteractRef.current = performance.now();
        }}
      />

      <FPSGuard qualityTier={qualityTier} onAutoDegrade={onAutoDegrade} />

      {/* Shared static urban night-aerial stage (ZERO fake decorative dots!) */}
      <GroundLayer
        shockwaveTime={shockwaveTime}
        announced={viewMode === 'split' ? month >= 13 : activeAnnounced}
        opened={viewMode === 'split' ? month >= 25 : activeOpened}
      />
      <BasemapLayer basemap={dataset.basemap} projection={dataset.meta.projection} dimmed={isolateTreated} />
      <MetroLayer
        metro={dataset.metro}
        projection={dataset.meta.projection}
        visible={layers.metro}
        highlighted={hoveredVital === 'commute'}
        dimmed={isolateTreated}
      />

      {viewMode === 'split' ? (
        <>
          {/* Left Viewport World: S (Sudden Open, uninformed M13-M24) */}
          <group ref={groupSRef}>
            <EastExpressLayer
              newline={dataset.newline}
              projection={dataset.meta.projection}
              visible={layers.newline}
              announced={false}
              opened={month >= dataset.meta.event_months.open}
            />
            <BidRentTerrainLayer
              zones={dataset.zones}
              zoneStats={zoneStatsS}
              visible={isTerrain}
              isolateTreated={isolateTreated}
            />
            <LandlordConstellationLayer
              landlords={dataset.landlords}
              rooms={dataset.rooms}
              decisions={runS.decisions.decisions}
              month={month}
              announced={false}
              opened={month >= dataset.meta.event_months.open}
              visible={isConstellation}
              isolateTreated={isolateTreated}
            />
            <RoomPillarsLayer
              rooms={dataset.rooms}
              states={statesS}
              visible={layers.rooms}
              isolateTreated={isolateTreated}
              highlightZone={highlightZone}
              selectedRoomId={selectedRoomId}
              onSelectRoom={onSelectRoom}
            />
            <ZoneRipplesLayer
              zones={dataset.zones}
              psGap={0}
              announced={false}
              opened={month >= dataset.meta.event_months.open}
              showIsochrone={layers.isochrone}
              isolateTreated={isolateTreated}
            />
            <CommuteParticles
              rooms={dataset.rooms}
              states={statesS}
              visible={layers.commute}
              opened={month >= dataset.meta.event_months.open}
            />
            <DecisionPulsesLayer
              month={month}
              decisions={runS.decisions.decisions}
              rooms={dataset.rooms}
              visible={layers.pulse}
            />
          </group>

          {/* Right Viewport World: P (Pre-Announced at M13) */}
          <group ref={groupPRef}>
            <EastExpressLayer
              newline={dataset.newline}
              projection={dataset.meta.projection}
              visible={layers.newline}
              announced={month >= dataset.meta.event_months.announce}
              opened={month >= dataset.meta.event_months.open}
            />
            <BidRentTerrainLayer
              zones={dataset.zones}
              zoneStats={zoneStatsP}
              visible={isTerrain}
              isolateTreated={isolateTreated}
            />
            <LandlordConstellationLayer
              landlords={dataset.landlords}
              rooms={dataset.rooms}
              decisions={runP.decisions.decisions}
              month={month}
              announced={month >= dataset.meta.event_months.announce}
              opened={month >= dataset.meta.event_months.open}
              visible={isConstellation}
              isolateTreated={isolateTreated}
            />
            <RoomPillarsLayer
              rooms={dataset.rooms}
              states={statesP}
              visible={layers.rooms}
              isolateTreated={isolateTreated}
              highlightZone={highlightZone}
              selectedRoomId={selectedRoomId}
              onSelectRoom={onSelectRoom}
            />
            <ZoneRipplesLayer
              zones={dataset.zones}
              psGap={psGap}
              announced={month >= dataset.meta.event_months.announce}
              opened={month >= dataset.meta.event_months.open}
              showIsochrone={layers.isochrone}
              isolateTreated={isolateTreated}
            />
            <CommuteParticles
              rooms={dataset.rooms}
              states={statesP}
              visible={layers.commute}
              opened={month >= dataset.meta.event_months.open}
            />
            <DecisionPulsesLayer
              month={month}
              decisions={runP.decisions.decisions}
              rooms={dataset.rooms}
              visible={layers.pulse}
            />
          </group>
        </>
      ) : (
        <>
          <EastExpressLayer
            newline={dataset.newline}
            projection={dataset.meta.projection}
            visible={layers.newline}
            announced={viewMode === 'diff' ? month >= dataset.meta.event_months.announce : activeAnnounced}
            opened={viewMode === 'diff' ? month >= dataset.meta.event_months.open : activeOpened}
          />
          <BidRentTerrainLayer
            zones={dataset.zones}
            zoneStats={viewMode === 'diff' ? zoneStatsP : zoneStatsActive}
            diffZoneStatsS={viewMode === 'diff' ? zoneStatsS : null}
            diffMode={viewMode === 'diff'}
            visible={isTerrain}
            isolateTreated={isolateTreated}
          />
          <LandlordConstellationLayer
            landlords={dataset.landlords}
            rooms={dataset.rooms}
            decisions={runActive.decisions.decisions}
            month={month}
            announced={viewMode === 'diff' ? month >= dataset.meta.event_months.announce : activeAnnounced}
            opened={viewMode === 'diff' ? month >= dataset.meta.event_months.open : activeOpened}
            visible={isConstellation}
            isolateTreated={isolateTreated}
          />
          <RoomPillarsLayer
            rooms={dataset.rooms}
            states={viewMode === 'diff' ? statesP : statesActive}
            diffStatesS={viewMode === 'diff' ? statesS : null}
            diffMode={viewMode === 'diff'}
            visible={layers.rooms}
            isolateTreated={isolateTreated}
            highlightZone={highlightZone}
            selectedRoomId={selectedRoomId}
            highlightVacant={hoveredVital === 'vacancy'}
            onSelectRoom={onSelectRoom}
          />
          <ZoneRipplesLayer
            zones={dataset.zones}
            psGap={psGap}
            announced={viewMode === 'diff' ? month >= dataset.meta.event_months.announce : activeAnnounced}
            opened={viewMode === 'diff' ? month >= dataset.meta.event_months.open : activeOpened}
            showIsochrone={layers.isochrone}
            isolateTreated={isolateTreated}
          />
          <CommuteParticles
            rooms={dataset.rooms}
            states={viewMode === 'diff' ? statesP : statesActive}
            visible={layers.commute}
            opened={activeOpened}
            highlighted={hoveredVital === 'commute'}
          />
          <MoveArcsLayer
            month={month}
            events={runActive.events}
            rooms={dataset.rooms}
            visible={layers.arcs}
            highlighted={hoveredVital === 'moveIns'}
          />
          <DecisionPulsesLayer
            month={month}
            decisions={runActive.decisions.decisions}
            rooms={dataset.rooms}
            visible={layers.pulse}
            highlighted={hoveredVital === 'llmCalls'}
          />
          <SpatialMindCallouts
            month={month}
            decisions={runActive.decisions.decisions}
            rooms={dataset.rooms}
            zoneById={dataset.zoneById}
            mentionKeywords={dataset.meta.mention_keywords}
            lang={lang}
            visible={isConstellation && layers.mindTags && showLabels}
            onSelectRoom={onSelectRoom}
          />
          <ZoneLabelsLayer
            zones={dataset.zones}
            zoneStats={zoneStatsActive}
            lang={lang}
            visible={showLabels}
            isolateTreated={isolateTreated}
            onSelectZone={onSelectZone}
          />
          <PostEffects enabled={qualityTier === 0 && !pal.isLight} />
        </>
      )}
    </>
  );
}

export function CityScene(props: CitySceneProps) {
  return (
    <div style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [4.5, 16.5, 31.5], fov: 36, near: 0.2, far: 260 }}
        gl={{
          antialias: true,
          preserveDrawingBuffer: true, // required for instant 4K PNG export & video recording
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.08,
        }}
      >
        <InnerCityScene {...props} />
      </Canvas>
    </div>
  );
}
