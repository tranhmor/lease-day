import type {
  DecisionsPayload,
  GeoJSONCollection,
  IncomeGroup,
  LandlordMeta,
  MonthlyCIData,
  MonthlyRecord,
  RoomMonthState,
  RoomStatic,
  RunBundle,
  Scenario,
  SimEvent,
  VerdictsData,
  VizDataset,
  VizMeta,
  ZoneInfo,
} from '@/types/viz';

const RECORD_BYTES = 16;
const GROUP_BY_CODE: Array<IncomeGroup | null> = [null, 'low', 'mid', 'high'];

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function fetchBuffer(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status} ${res.statusText}`);
  }
  return res.arrayBuffer();
}

export async function loadRunBundle(baseUrl: string, scenario: Scenario, seed: number): Promise<RunBundle> {
  const prefix = `${baseUrl}/runs/${scenario}_${seed}`;
  const [roomStatesBuffer, events, decisions, monthly] = await Promise.all([
    fetchBuffer(`${prefix}/room_states.bin`),
    fetchJson<SimEvent[]>(`${prefix}/events.json`),
    fetchJson<DecisionsPayload>(`${prefix}/decisions.json`),
    fetchJson<MonthlyRecord[]>(`${prefix}/monthly.json`),
  ]);
  return { scenario, seed, roomStatesBuffer, events, decisions, monthly };
}

export async function loadVizDataset(baseUrl = './viz_data'): Promise<VizDataset> {
  const meta = await fetchJson<VizMeta>(`${baseUrl}/meta.json`);
  const [zones, rooms, landlords, metro, newline, basemap, buildings, monthlyCI, verdicts] = await Promise.all([
    fetchJson<ZoneInfo[]>(`${baseUrl}/geo/zones.json`),
    fetchJson<RoomStatic[]>(`${baseUrl}/rooms.json`),
    fetchJson<LandlordMeta[]>(`${baseUrl}/landlords.json`),
    fetchJson<GeoJSONCollection>(`${baseUrl}/geo/metro.geojson`),
    fetchJson<GeoJSONCollection>(`${baseUrl}/geo/newline.geojson`),
    fetchJson<GeoJSONCollection>(`${baseUrl}/geo/basemap.geojson`),
    fetchJson<GeoJSONCollection>(`${baseUrl}/geo/buildings.geojson`),
    fetchJson<MonthlyCIData>(`${baseUrl}/aggregate/monthly_ci.json`),
    fetchJson<VerdictsData>(`${baseUrl}/aggregate/verdicts.json`),
  ]);

  // Load default (median) seed for all 3 scenarios in parallel so switching N/S/P is instantaneous
  const seed = meta.default_seed;
  const runList = await Promise.all(
    meta.scenarios.map((sc) => loadRunBundle(baseUrl, sc, seed))
  );
  const runs: Record<string, RunBundle> = {};
  for (const r of runList) {
    runs[`${r.scenario}_${r.seed}`] = r;
  }

  const zoneById: Record<string, ZoneInfo> = {};
  for (const z of zones) zoneById[z.id] = z;

  const landlordById: Record<number, LandlordMeta> = {};
  for (const ll of landlords) landlordById[ll.landlord_id] = ll;

  return {
    meta,
    zones,
    zoneById,
    rooms,
    landlords,
    landlordById,
    metro,
    newline,
    basemap,
    buildings,
    monthlyCI,
    verdicts,
    runs,
  };
}

/** Zero-allocation reader for a single (month 1..36, roomId 0..239) binary record */
export function readRoomState(
  buffer: ArrayBuffer,
  month: number,
  roomId: number,
  nRooms = 240
): RoomMonthState {
  const view = new DataView(buffer);
  const off = ((month - 1) * nRooms + roomId) * RECORD_BYTES;
  if (off + RECORD_BYTES > buffer.byteLength) {
    return { rent: 0, tenantId: -1, occupied: false, vacantFor: 0, groupCode: 0, group: null, commuteMin: 0, income: 0 };
  }
  const rent = view.getFloat32(off, true);
  const tenantId = view.getInt32(off + 4, true);
  const occupied = view.getUint8(off + 8) === 1;
  const vacantFor = view.getUint8(off + 9);
  const groupCode = view.getUint8(off + 10);
  const commuteMin = view.getUint8(off + 11);
  const income = view.getFloat32(off + 12, true);
  return {
    rent,
    tenantId,
    occupied,
    vacantFor,
    groupCode,
    group: GROUP_BY_CODE[groupCode] ?? null,
    commuteMin,
    income,
  };
}

export function readMonthRoomStates(buffer: ArrayBuffer, month: number, nRooms = 240): RoomMonthState[] {
  const out = new Array<RoomMonthState>(nRooms);
  const view = new DataView(buffer);
  const baseOff = (month - 1) * nRooms * RECORD_BYTES;
  for (let i = 0; i < nRooms; i++) {
    const off = baseOff + i * RECORD_BYTES;
    if (off + RECORD_BYTES > buffer.byteLength) {
      out[i] = { rent: 0, tenantId: -1, occupied: false, vacantFor: 0, groupCode: 0, group: null, commuteMin: 0, income: 0 };
      continue;
    }
    const rent = view.getFloat32(off, true);
    const tenantId = view.getInt32(off + 4, true);
    const occupied = view.getUint8(off + 8) === 1;
    const vacantFor = view.getUint8(off + 9);
    const groupCode = view.getUint8(off + 10);
    const commuteMin = view.getUint8(off + 11);
    const income = view.getFloat32(off + 12, true);
    out[i] = {
      rent,
      tenantId,
      occupied,
      vacantFor,
      groupCode,
      group: GROUP_BY_CODE[groupCode] ?? null,
      commuteMin,
      income,
    };
  }
  return out;
}

/** Compute per-zone rent index delta (vs M1 start_rent) and occupancy stats for a given month */
export function computeZoneStats(
  rooms: RoomStatic[],
  states: RoomMonthState[]
): Record<string, { rentDeltaPts: number; rentIndex: number; occupied: number; total: number; avgCommute: number; avgBurden: number }> {
  const acc: Record<string, { ratioSum: number; n: number; occ: number; commSum: number; burdenSum: number }> = {};
  for (let i = 0; i < rooms.length; i++) {
    const r = rooms[i];
    const st = states[i];
    if (!acc[r.zone]) {
      acc[r.zone] = { ratioSum: 0, n: 0, occ: 0, commSum: 0, burdenSum: 0 };
    }
    const a = acc[r.zone];
    const ratio = r.start_rent > 0 && st.rent > 0 ? st.rent / r.start_rent : 1.0;
    a.ratioSum += ratio;
    a.n += 1;
    if (st.occupied) {
      a.occ += 1;
      a.commSum += st.commuteMin;
      if (st.income > 0) a.burdenSum += st.rent / st.income;
    }
  }
  const out: Record<string, { rentDeltaPts: number; rentIndex: number; occupied: number; total: number; avgCommute: number; avgBurden: number }> = {};
  for (const [zid, a] of Object.entries(acc)) {
    const idx = a.n > 0 ? (a.ratioSum / a.n) * 100 : 100;
    out[zid] = {
      rentIndex: idx,
      rentDeltaPts: idx - 100,
      occupied: a.occ,
      total: a.n,
      avgCommute: a.occ > 0 ? a.commSum / a.occ : 0,
      avgBurden: a.occ > 0 ? a.burdenSum / a.occ : 0,
    };
  }
  return out;
}
