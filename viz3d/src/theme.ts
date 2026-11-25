import { useSyncExternalStore } from 'react';
import * as THREE from 'three';

export type Theme = 'dark' | 'light';

/**
 * Module-level store so the theme reaches both the DOM HUD and the R3F canvas
 * (React context does not cross the <Canvas> reconciler boundary).
 */
const STORAGE_KEY = 'leaseday.theme';

function initialTheme(): Theme {
  const q = new URLSearchParams(window.location.search).get('theme');
  if (q === 'light' || q === 'dark') return q;
  try {
    const s = window.localStorage.getItem(STORAGE_KEY);
    if (s === 'light' || s === 'dark') return s;
  } catch {
    /* ignore */
  }
  return 'dark';
}

let current: Theme = initialTheme();
const listeners = new Set<() => void>();
document.documentElement.dataset.theme = current;

export function getTheme(): Theme {
  return current;
}

export function setTheme(t: Theme) {
  if (t === current) return;
  current = t;
  document.documentElement.dataset.theme = t;
  try {
    window.localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

export function toggleTheme() {
  setTheme(current === 'dark' ? 'light' : 'dark');
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getTheme, getTheme);
}

export interface ScenePalette {
  isLight: boolean;
  bg: string;
  /** Additive glow on dark; normal alpha blending on light paper. */
  glowBlending: THREE.Blending;
  /** HDR boost multiplier (dark only; light clamps to 1). */
  boost: (x: number) => number;
  ground: { outer: [number, number, number]; core: [number, number, number]; cbd: [number, number, number]; east: [number, number, number]; wave: [number, number, number] };
  basemap: { water: string; arterial: string; district: string; ring: string; building: string; opacity: number };
  metro: { ribbon: string; core: string; comet: [number, number, number] };
  rent: { neg: string; zero: string; mid: string; max: string; neutralLerp: string };
  room: { vacant: string; dim: string; vacantRing: string; selected: string; alert: string };
  announce: string;
  announceSoft: string;
  cream: string;
  p: string;
  s: string;
  cool: string;
  coolSoft: string;
  income: { low: string; mid: string; high: string };
  isochrone: string;
  label: { name: string; treated: string; shadow: string; up: string; down: string; flat: string };
  callout: { bg: string; border: string; text: string; sub: string };
}

export const SCENE_PALETTES: Record<Theme, ScenePalette> = {
  dark: {
    isLight: false,
    bg: '#243347',
    glowBlending: THREE.AdditiveBlending,
    boost: (x) => x,
    ground: {
      outer: [0.118, 0.165, 0.235],
      core: [0.086, 0.125, 0.188],
      cbd: [0.16, 0.28, 0.44],
      east: [0.95, 0.65, 0.2],
      wave: [1.0, 0.75, 0.28],
    },
    basemap: { water: '#0C1726', arterial: '#18385C', district: '#3C5476', ring: '#344B6E', building: '#587DB0', opacity: 1 },
    metro: { ribbon: '#6BB7FF', core: '#CBE8FF', comet: [0.86, 0.95, 1.0] },
    rent: { neg: '#5FB4FF', zero: '#9AA7BD', mid: '#FFB02E', max: '#FF5A3C', neutralLerp: '#E8F3FF' },
    room: { vacant: '#3B557A', dim: '#20314A', vacantRing: '#7CB6F5', selected: '#FFB02E', alert: '#FF6B57' },
    announce: '#FFB02E',
    announceSoft: '#FFF1C7',
    cream: '#FFF1C7',
    p: '#FF6B57',
    s: '#4EA8FF',
    cool: '#5FB4FF',
    coolSoft: '#85C7FF',
    income: { low: '#2DD4BF', mid: '#A78BFA', high: '#F472B6' },
    isochrone: '#6BD3A0',
    label: { name: '#E3EEFF', treated: '#FFD27D', shadow: 'rgba(10,16,28,0.95)', up: '#FF9D7E', down: '#7FE0B0', flat: '#A9BDD8' },
    callout: { bg: 'rgba(13, 21, 35, 0.84)', border: 'rgba(255, 176, 46, 0.65)', text: '#E8F0FA', sub: '#FF9D7E' },
  },
  light: {
    isLight: true,
    bg: '#EEF1F5',
    glowBlending: THREE.NormalBlending,
    boost: () => 1,
    ground: {
      outer: [0.925, 0.937, 0.953],
      core: [0.965, 0.969, 0.976],
      cbd: [-0.04, -0.02, 0.01],
      east: [0.95, 0.55, 0.1],
      wave: [0.85, 0.55, 0.14],
    },
    basemap: { water: '#C9DCEC', arterial: '#C3CCD8', district: '#B4BFCD', ring: '#A9B6C7', building: '#8597AE', opacity: 1 },
    metro: { ribbon: '#3D8FD6', core: '#2F78BE', comet: [0.18, 0.47, 0.75] },
    rent: { neg: '#2F86D0', zero: '#8A96A8', mid: '#E39A1E', max: '#D9432A', neutralLerp: '#6E7B8F' },
    room: { vacant: '#B5C0CF', dim: '#DCE2EA', vacantRing: '#7E8FA6', selected: '#D98A10', alert: '#D95B4A' },
    announce: '#D98A10',
    announceSoft: '#F6D79A',
    cream: '#FFFFFF',
    p: '#D95B4A',
    s: '#3A88CF',
    cool: '#3D8FD6',
    coolSoft: '#5D9FD8',
    income: { low: '#1E9E90', mid: '#7F65C4', high: '#CC5A8E' },
    isochrone: '#3EA877',
    label: { name: '#1F2A3C', treated: '#B86E00', shadow: 'rgba(245,247,250,0.95)', up: '#C9472F', down: '#2E8F62', flat: '#5C687D' },
    callout: { bg: 'rgba(255, 255, 255, 0.92)', border: 'rgba(217, 138, 16, 0.7)', text: '#1F2A3C', sub: '#C9472F' },
  },
};

export function useScenePalette(): ScenePalette {
  return SCENE_PALETTES[useTheme()];
}
