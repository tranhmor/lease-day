import { useMemo } from 'react';
import * as THREE from 'three';
import type { GeoJSONCollection, ProjectionMeta } from '@/types/viz';
import { LocalProjector } from '@/data/geo';

interface BasemapLayerProps {
  basemap: GeoJSONCollection;
  projection: ProjectionMeta;
  dimmed?: boolean;
}

function buildLineSegmentsGeometry(polylines: Array<Array<[number, number]>>, y: number): THREE.BufferGeometry {
  let segCount = 0;
  for (const line of polylines) {
    if (line.length >= 2) segCount += line.length - 1;
  }
  const positions = new Float32Array(segCount * 6);
  let ptr = 0;
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      const a = line[i];
      const b = line[i + 1];
      positions[ptr++] = a[0];
      positions[ptr++] = y;
      positions[ptr++] = a[1];
      positions[ptr++] = b[0];
      positions[ptr++] = y;
      positions[ptr++] = b[1];
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  return geo;
}

function buildWaterPolygonsGeometry(polygons: Array<Array<[number, number]>>, y: number): THREE.BufferGeometry | null {
  const positions: number[] = [];
  for (const ring of polygons) {
    if (ring.length < 3) continue;
    const shape = new THREE.Shape();
    shape.moveTo(ring[0][0], -ring[0][1]);
    for (let i = 1; i < ring.length; i++) {
      shape.lineTo(ring[i][0], -ring[i][1]);
    }
    const shapeGeo = new THREE.ShapeGeometry(shape);
    const posAttr = shapeGeo.getAttribute('position');
    const idx = shapeGeo.getIndex();
    if (idx) {
      for (let i = 0; i < idx.count; i++) {
        const vi = idx.getX(i);
        positions.push(posAttr.getX(vi), y, -posAttr.getY(vi));
      }
    } else {
      for (let i = 0; i < posAttr.count; i++) {
        positions.push(posAttr.getX(i), y, -posAttr.getY(i));
      }
    }
    shapeGeo.dispose();
  }
  if (!positions.length) return null;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.computeVertexNormals();
  return geo;
}

/**
 * L1: Crisp dark-aerial Beijing road network (2nd-6th ring roads, arterials), dark water bodies, and subtle district borders.
 */
export function BasemapLayer({ basemap, projection, dimmed = false }: BasemapLayerProps) {
  const geometries = useMemo(() => {
    const proj = new LocalProjector(projection);
    const ringLines: Array<Array<[number, number]>> = [];
    const arterialLines: Array<Array<[number, number]>> = [];
    const waterLines: Array<Array<[number, number]>> = [];
    const districtLines: Array<Array<[number, number]>> = [];
    const waterPolys: Array<Array<[number, number]>> = [];

    for (const f of basemap.features) {
      const layer = f.properties?.layer;
      const g = f.geometry;
      if (!g) continue;
      if (g.type === 'LineString') {
        const pts = (g.coordinates as [number, number][]).map(([lon, lat]) => proj.lonLatToXZ(lon, lat));
        if (layer === 'ring_road') ringLines.push(pts);
        else if (layer === 'waterway') waterLines.push(pts);
        else if (layer === 'district') districtLines.push(pts);
        else arterialLines.push(pts);
      } else if (g.type === 'Polygon' && layer === 'water_poly') {
        const outer = (g.coordinates[0] as [number, number][]).map(([lon, lat]) => proj.lonLatToXZ(lon, lat));
        waterPolys.push(outer);
      }
    }

    return {
      ringGeo: buildLineSegmentsGeometry(ringLines, 0.025),
      arterialGeo: buildLineSegmentsGeometry(arterialLines, 0.016),
      waterLineGeo: buildLineSegmentsGeometry(waterLines, 0.012),
      districtGeo: buildLineSegmentsGeometry(districtLines, 0.02),
      waterPolyGeo: buildWaterPolygonsGeometry(waterPolys, 0.005),
    };
  }, [basemap, projection]);

  const dimFactor = dimmed ? 0.42 : 1.0;

  return (
    <group name="L1_basemap">
      {geometries.waterPolyGeo && (
        <mesh geometry={geometries.waterPolyGeo}>
          <meshBasicMaterial color="#0A0B0E" transparent opacity={0.95 * dimFactor} depthWrite={false} />
        </mesh>
      )}
      <lineSegments geometry={geometries.waterLineGeo}>
        <lineBasicMaterial color="#22262C" transparent opacity={0.7 * dimFactor} depthWrite={false} />
      </lineSegments>
      <lineSegments geometry={geometries.districtGeo}>
        <lineBasicMaterial color="#3A3F47" transparent opacity={0.35 * dimFactor} depthWrite={false} />
      </lineSegments>
      <lineSegments geometry={geometries.arterialGeo}>
        <lineBasicMaterial color="#30343B" transparent opacity={0.75 * dimFactor} depthWrite={false} />
      </lineSegments>
      <lineSegments geometry={geometries.ringGeo}>
        <lineBasicMaterial color="#4A4F57" transparent opacity={0.85 * dimFactor} depthWrite={false} />
      </lineSegments>
    </group>
  );
}
