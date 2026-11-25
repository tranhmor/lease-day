import type { ChapterSpec, LayerToggles } from '@/types/viz';

export const DEFAULT_LAYERS: LayerToggles = {
  rooms: true,
  metro: true,
  newline: true,
  pulse: true,
  commute: true,
  arcs: true,
  mindTags: true,
  isochrone: false,
};

/**
 * 8-Chapter Presentation Script (§3 Narrative Structure)
 * Coordinate system: CBD (Z00) = (0, 0, 0), Guoyuan (Z05) ≈ (+15.8, 0, +1.5), Wuyi (Z11) ≈ (+18.0, 0, +1.5).
 * Default framing shifts target slightly east (+4, 0, 0.5) so treated zones land in right third, leaving left clear for HUD.
 */
export const CHAPTERS: ChapterSpec[] = [
  // Ch 0: Opening — High altitude sweep into Eastern Beijing, progressive reveal
  {
    id: 0,
    monthStart: 1,
    monthEnd: 1,
    autoPlay: false,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [12, 42, 46],
      target: [6, 0, 1],
      fov: 38,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: false,
      pulse: false,
      commute: true,
      arcs: false,
      mindTags: false,
      isochrone: false,
    },
    panels: {
      showHUD: false,
      showIntroTitle: true,
    },
  },
  // Ch 1: City & Market (M1-M12) — sweeping low-oblique night-aerial perspective like Shenzhen reference
  {
    id: 1,
    monthStart: 1,
    monthEnd: 12,
    autoPlay: true,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [4.5, 16.5, 31.5],
      target: [6.0, 0, -1.0],
      fov: 36,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: false,
      pulse: true,
      commute: true,
      arcs: false,
      mindTags: false,
      isochrone: false,
    },
    panels: {
      showHUD: true,
    },
  },
  // Ch 2: Three Worlds (M12) — Synchronized Split Screen Left=S, Right=P
  {
    id: 2,
    monthStart: 12,
    monthEnd: 12,
    autoPlay: false,
    defaultScenario: 'P',
    viewMode: 'split',
    camera: {
      position: [7, 26, 31],
      target: [6.5, 0, 1.0],
      fov: 35,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: false,
      pulse: true,
      commute: true,
      arcs: false,
      mindTags: false,
      isochrone: false,
    },
    panels: {
      showHUD: true,
      highlightTabs: true,
    },
  },
  // Ch 3: Announcement (M13) — Push into Eastern Corridor, shockwave + holographic dashed line
  {
    id: 3,
    monthStart: 13,
    monthEnd: 15,
    autoPlay: true,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [10, 14, 21],
      target: [10.5, 0, 1.2],
      fov: 34,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: true,
      pulse: true,
      commute: true,
      arcs: false,
      mindTags: false,
      isochrone: false,
    },
    panels: {
      showHUD: true,
      triggerShockwave: true,
    },
  },
  // Ch 4: Inside Landlord Minds (M13-M24) — Low flyby over Guoyuan & Wuyi Garden, expanded Reason Feed
  {
    id: 4,
    monthStart: 18,
    monthEnd: 24,
    autoPlay: true,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [14.5, 9.5, 13.5],
      target: [16.2, 0.5, 1.4],
      fov: 34,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: true,
      pulse: true,
      commute: false,
      arcs: false,
      mindTags: false,
      isochrone: false,
    },
    panels: {
      showHUD: true,
      expandFeed: true,
    },
  },
  // Ch 5: Opening (M25) — Pull back, solid glowing line + fast light flow + shrinking isochrones
  {
    id: 5,
    monthStart: 25,
    monthEnd: 28,
    autoPlay: true,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [9, 22, 27],
      target: [9.0, 0, 1.2],
      fov: 35,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: true,
      pulse: true,
      commute: true,
      arcs: true,
      mindTags: false,
      isochrone: true,
    },
    panels: {
      showHUD: true,
    },
  },
  // Ch 6: Who Benefits & Who Pays (M25-M36) — Top-down view, move-in arcs by income group (H2)
  {
    id: 6,
    monthStart: 25,
    monthEnd: 36,
    autoPlay: true,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [8, 36, 12],
      target: [7.5, 0, 1.2],
      fov: 36,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: true,
      pulse: false,
      commute: false,
      arcs: true,
      mindTags: true,
      isochrone: false,
    },
    panels: {
      showHUD: true,
      showMoverProfile: true,
    },
  },
  // Ch 7: Conclusion (M36) — Freeze, isolate treated zones, display H1-H3 Pre-registered Verdict Cards
  {
    id: 7,
    monthStart: 36,
    monthEnd: 36,
    autoPlay: false,
    defaultScenario: 'P',
    viewMode: 'single',
    camera: {
      position: [13, 17, 22],
      target: [14.0, 0, 1.2],
      fov: 34,
    },
    layers: {
      rooms: true,
      metro: true,
      newline: true,
      pulse: false,
      commute: true,
      arcs: false,
      mindTags: false,
      isochrone: true,
    },
    panels: {
      showHUD: true,
      showVerdicts: true,
      isolateTreated: true,
    },
  },
];
