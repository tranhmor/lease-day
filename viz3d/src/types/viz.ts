export type Scenario = 'N' | 'S' | 'P';
export type Lang = 'zh' | 'en';
export type AppMode = 'presentation' | 'explore' | 'export';
export type ViewMode = 'single' | 'split' | 'diff';
export type VisualStyle = 'constellation' | 'terrain';
export type RoomShape = 'disc' | 'bar';
export type QualityTier = 0 | 1 | 2; // 0 = Full 3D+Bloom, 1 = 3D Light (no bloom/fog, half particles), 2 = 2D Fallback
export type IncomeGroup = 'low' | 'mid' | 'high';
export type RoomKind = '低价房' | '便宜单间' | '合租单间' | '整租';

export interface LayerToggles {
  rooms: boolean;
  metro: boolean;
  newline: boolean;
  pulse: boolean;
  commute: boolean;
  arcs: boolean;
  mindTags: boolean;
  isochrone: boolean;
}

export interface ProjectionMeta {
  type: string;
  origin_zone: string;
  origin_lat: number;
  origin_lon: number;
  cos_lat0: number;
  meters_per_unit: number;
}

export interface VizMeta {
  version: string;
  generated_at: string;
  group: string;
  scenarios: Scenario[];
  seeds: number[];
  all_aggregate_seeds: number[];
  default_seed: number;
  default_seed_rule: string;
  months: number;
  n_rooms: number;
  n_landlords: number;
  event_months: { announce: number; open: number };
  treated_zones: string[];
  source_label: string;
  is_illustrative: boolean;
  has_room_states: boolean;
  mention_keywords: string[];
  feed_sample_seed: number;
  projection: ProjectionMeta;
  room_states_schema: {
    bytes_per_record: number;
    endian: string;
    fields: Array<{ name: string; type: string; offset: number }>;
  };
}

export interface ZoneInfo {
  id: string;
  name: string;
  name_en: string;
  dir: string;
  ring: string;
  lat: number;
  lon: number;
  x: number;
  z: number;
  true_x: number;
  true_z: number;
  radius: number;
  treated: boolean;
  major: boolean;
  n_rooms: number;
  subway_min: number;
  whole_rent: number;
  label_offset: [number, number];
}

export interface RoomStatic {
  id: number;
  zone: string;
  kind: RoomKind;
  landlord_id: number;
  start_rent: number;
  station_dist_m: number;
  layout_xy: [number, number];
  kind_rent_range: [number, number];
}

export interface LandlordMeta {
  landlord_id: number;
  kind: string;
  risk: string;
  treated: boolean;
  zones: string[];
  n_rooms: number;
}

export interface RoomMonthState {
  rent: number;
  tenantId: number; // -1 if vacant
  occupied: boolean;
  vacantFor: number;
  groupCode: number; // 0 vacant, 1 low, 2 mid, 3 high
  group: IncomeGroup | null;
  commuteMin: number;
  income: number;
}

export interface SimEvent {
  m: number;
  type: 'move_in' | 'move_out' | 'renew' | 'counter';
  reason?: string;
  tenant_id: number;
  from_room: number | null;
  to_room: number | null;
  income_group: IncomeGroup;
  income: number;
  rent: number;
  rent_before?: number;
  mode?: string;
  accepted?: boolean;
}

export interface DecisionRecord {
  m: number;
  agent_type: 'landlord' | 'tenant';
  agent_id: number;
  decision: string;
  room_id: number | null;
  zone: string | null;
  kind?: string;
  ll_kind?: string;
  ll_risk?: string;
  vacant_for?: number;
  rent_before?: number | null;
  rent_after?: number | null;
  action?: string;
  apply?: Array<{ room_id: number; mode: string }>;
  counter_rent?: number | null;
  tenant_group?: IncomeGroup;
  tenant_income?: number;
  candidates?: Array<{ room_id: number; zone: string; kind: string; rent: number; min: number }>;
  reason: string;
  mentions_line: boolean;
  prompt_hash: string;
  fallback: boolean;
  inputs?: Record<string, unknown>;
}

export interface MentionStat {
  total: number;
  mentions: number;
  rate: number;
  treated_total: number;
  treated_mentions: number;
  treated_rate: number;
}

export interface DecisionsPayload {
  decisions: DecisionRecord[];
  mention_stats: Record<string, MentionStat>;
  feed_sample_by_month: Record<string, number[]>;
  llm_calls_by_month: Record<string, number>;
}

export interface MonthlyRecord {
  month: number;
  announced: boolean;
  line_open: boolean;
  occupied: number;
  vacancy_all: number;
  vacancy_treated: number;
  vacancy_other: number;
  rent_index_all: number;
  rent_index_treated: number;
  rent_index_other: number;
  commute_all: number;
  commute_treated: number;
  commute_other: number;
  over60: number;
  burden_all: number;
  treated_low_share: number;
  treated_vacates: number;
  treated_move_ins: number;
  treated_move_in_incomes: number[];
  treated_move_in_cash: number[];
  treated_move_in_groups: Record<IncomeGroup, number>;
  treated_expiries: number;
  treated_renewals: number;
  treated_renewal_hikes: number[];
  counters: number;
  counter_accepts: number;
  multi_app_rooms: number;
}

export interface MonthlyCIData {
  seeds: number[];
  months: number;
  median_seed: number;
  median_seed_m24_ps: number;
  m24_ps_by_seed: Record<string, number>;
  scenarios: Record<Scenario, Record<string, [number, number][]>>;
  paired_diffs: Record<'P_minus_S' | 'P_minus_N' | 'S_minus_N', Record<string, [number, number][]>>;
}

export interface VerdictsData {
  group: string;
  seeds: number[];
  criteria?: Record<string, string>;
  results: {
    quality?: { max_fallback_rate: number; void_runs: Record<string, number>; verdict: string };
    H1?: {
      n_offers: number;
      b_P_pct: number | null;
      ci95_pct: [number, number] | null;
      seeds_positive: string;
      aux_P_minus_S_rent_index_M24: string;
      verdict: string;
    };
    H2?: {
      income: { P_minus_S: number | null; ci95: [number, number] | null };
      cash: { P_minus_S: number | null; ci95: [number, number] | null };
      n_move_ins: { P: number; S: number };
      verdict: string;
    };
    H3?: {
      L_no_hike_when_tight: number | null;
      L_counter_accept: number | null;
      R_no_hike_when_tight?: number | null;
      R_counter_accept?: number | null;
      n_tight_quotes: number;
      n_counters: number;
      verdict: string;
    };
    B?: {
      diff_mean_ci95?: Record<string, [number, number]>;
      verdict: string;
    };
    exploratory_persona?: {
      treated_quote_change_by_persona?: Record<string, { P_minus_S_pct: number | null; n_P: number; n_S: number }>;
    };
  };
}

export interface GeoJSONFeature {
  type: 'Feature';
  properties: Record<string, any>;
  geometry: {
    type: 'Point' | 'LineString' | 'Polygon' | 'MultiLineString' | 'MultiPolygon';
    coordinates: any;
  };
}

export interface GeoJSONCollection {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
}

export interface RunBundle {
  scenario: Scenario;
  seed: number;
  roomStatesBuffer: ArrayBuffer;
  events: SimEvent[];
  decisions: DecisionsPayload;
  monthly: MonthlyRecord[];
}

export interface VizDataset {
  meta: VizMeta;
  zones: ZoneInfo[];
  zoneById: Record<string, ZoneInfo>;
  rooms: RoomStatic[];
  landlords: LandlordMeta[];
  landlordById: Record<number, LandlordMeta>;
  metro: GeoJSONCollection;
  newline: GeoJSONCollection;
  basemap: GeoJSONCollection;
  buildings: GeoJSONCollection;
  monthlyCI: MonthlyCIData;
  verdicts: VerdictsData;
  runs: Record<string, RunBundle>; // key: `${scen}_${seed}`
}

export interface CameraKeyframe {
  position: [number, number, number];
  target: [number, number, number];
  fov: number;
}

export interface ChapterSpec {
  id: number;
  monthStart: number;
  monthEnd: number;
  autoPlay: boolean;
  defaultScenario: Scenario;
  viewMode: ViewMode;
  camera: CameraKeyframe;
  layers: Partial<LayerToggles>;
  panels: {
    showHUD: boolean;
    showIntroTitle?: boolean;
    expandFeed?: boolean;
    showMoverProfile?: boolean;
    showVerdicts?: boolean;
    highlightTabs?: boolean;
    isolateTreated?: boolean;
    triggerShockwave?: boolean;
  };
}
