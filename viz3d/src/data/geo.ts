import * as THREE from 'three';
import type { ProjectionMeta } from '@/types/viz';

const EARTH_R = 6378137.0;

function mercatorXY(lat: number, lon: number): [number, number] {
  const x = EARTH_R * ((lon * Math.PI) / 180);
  const y = EARTH_R * Math.log(Math.tan(Math.PI / 4 + ((lat * Math.PI) / 180) / 2));
  return [x, y];
}

export class LocalProjector {
  private readonly ox: number;
  private readonly oy: number;
  private readonly scale: number;

  constructor(meta: ProjectionMeta) {
    const [ox, oy] = mercatorXY(meta.origin_lat, meta.origin_lon);
    this.ox = ox;
    this.oy = oy;
    this.scale = meta.cos_lat0 / meta.meters_per_unit;
  }

  /** Convert [lon, lat] (GeoJSON order) -> Three.js [x, z] where +X=East, -Z=North, CBD=(0,0) */
  lonLatToXZ(lon: number, lat: number): [number, number] {
    const [mx, my] = mercatorXY(lat, lon);
    const x = (mx - this.ox) * this.scale;
    const z = -((my - this.oy) * this.scale);
    return [x, z];
  }

  lonLatToVec3(lon: number, lat: number, y = 0): THREE.Vector3 {
    const [x, z] = this.lonLatToXZ(lon, lat);
    return new THREE.Vector3(x, y, z);
  }
}

/** Map rent index delta (-4..+4) to diverging palette: #6F9FC7 -> #8A8F98 -> #D2876A -> #E4572E */
const C_NEG = new THREE.Color('#6F9FC7');
const C_ZERO = new THREE.Color('#8A8F98');
const C_MID_POS = new THREE.Color('#D2876A');
const C_MAX_POS = new THREE.Color('#E4572E');

export function rentDeltaToColor(deltaPts: number, target = new THREE.Color()): THREE.Color {
  const d = Math.max(-4, Math.min(4, deltaPts));
  if (d <= 0) {
    const t = (d + 4) / 4; // 0 at -4, 1 at 0
    return target.copy(C_NEG).lerp(C_ZERO, t);
  }
  if (d <= 2) {
    return target.copy(C_ZERO).lerp(C_MID_POS, d / 2);
  }
  return target.copy(C_MID_POS).lerp(C_MAX_POS, (d - 2) / 2);
}

export function rentDeltaToHex(deltaPts: number): string {
  return '#' + rentDeltaToColor(deltaPts).getHexString();
}
