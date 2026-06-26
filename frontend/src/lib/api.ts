import axios from 'axios';

/**
 * Resolve API base URL without silent multi-host fallbacks.
 *
 * - Production / Docker (`NODE_ENV=production` or `REQUIRE_API_URL=1`):
 *   `NEXT_PUBLIC_API_URL` is required. Missing → no localhost mask; requests
 *   fail via interceptor (visible error UI). We avoid throwing at module import
 *   so `next build` prerender can complete, but we never invent alternate hosts.
 * - Local dev only (`NODE_ENV !== 'production'` and not requiring API URL):
 *   explicit documented fallback to `http://localhost:8000/api` for `npm run dev`.
 *
 * Never invent alternate hosts or retry to a different base URL.
 */
const MISSING_API_URL_MSG =
  '[api] NEXT_PUBLIC_API_URL is required in production/Docker (or when REQUIRE_API_URL=1). ' +
  'Refusing silent localhost fallback so API outages are visible.';

function resolveApiBaseURL(): { baseURL: string; missingRequired: boolean } {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  const requireUrl =
    process.env.NODE_ENV === 'production' ||
    process.env.REQUIRE_API_URL === '1' ||
    process.env.REQUIRE_API_URL === 'true';

  if (configured) {
    return { baseURL: configured.replace(/\/$/, ''), missingRequired: false };
  }

  if (requireUrl) {
    if (typeof console !== 'undefined') {
      console.error(MISSING_API_URL_MSG);
    }
    // Empty base forces relative/invalid requests — interceptor rejects explicitly.
    return { baseURL: '', missingRequired: true };
  }

  // Local `npm run dev` only — documented explicit fallback, not a multi-host retry.
  const devFallback = 'http://localhost:8000/api';
  if (typeof console !== 'undefined') {
    console.warn(
      `[api] NEXT_PUBLIC_API_URL unset; using dev fallback ${devFallback}. ` +
        'Set NEXT_PUBLIC_API_URL (and REQUIRE_API_URL=1 in Docker) to avoid this.',
    );
  }
  return { baseURL: devFallback, missingRequired: false };
}

const resolved = resolveApiBaseURL();
const baseURL = resolved.baseURL;

const api = axios.create({
  baseURL: baseURL || undefined,
});

api.interceptors.request.use((config) => {
  if (resolved.missingRequired || !baseURL) {
    return Promise.reject(new Error(MISSING_API_URL_MSG));
  }
  return config;
});

/** Exported for tests / debugging — the single configured API origin (no alternates). */
export const API_BASE_URL = baseURL;
export const API_URL_MISSING_REQUIRED = resolved.missingRequired;

// ---------------------------------------------------------------------------
// In-memory request cache — deduplicates in-flight requests and caches results
// for the lifetime of the session. Backend data is static (government files),
// so there's no need for TTL or invalidation.
// ---------------------------------------------------------------------------
const _cache = new Map<string, Promise<unknown>>();

function cached<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = _cache.get(key);
  if (existing) return existing as Promise<T>;
  const promise = fn().catch((err: unknown) => {
    _cache.delete(key); // don't cache failures
    throw err;
  });
  _cache.set(key, promise);
  return promise;
}

export const getWaterfallData = (applyFreeze: boolean = false, applyRealRestrictions: boolean = false) =>
  cached(`waterfall:${applyFreeze}:${applyRealRestrictions}`, () =>
    api.get('/waterfall', { params: { apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data));
export const getSupplyDemandData = (applyFreeze: boolean = false, applyRealRestrictions: boolean = false) =>
  cached(`supply-demand:${applyFreeze}:${applyRealRestrictions}`, () =>
    api.get('/supply-demand', { params: { apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data));
export const predictPD = (priorityDate: string, applyFreeze: boolean = false, applyRealRestrictions: boolean = false) =>
  cached(`predict:${priorityDate}:${applyFreeze}:${applyRealRestrictions}`, () =>
    api.get('/predict', { params: { priority_date: priorityDate, apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data));
export const getMethodology = () =>
  cached('methodology', () => api.get('/methodology').then(res => res.data));
export const getInventoryContext = () =>
  cached('inventory-context', () => api.get('/inventory-context').then(res => res.data));
export const getNVCBacklog = () =>
  cached('nvc-backlog', () => api.get('/nvc-backlog').then(res => res.data));
export const getVisaBulletinHistory = (category?: string, country?: string): Promise<VBHistoryData> =>
  cached(`vb-history:${category}:${country}`, () =>
    api.get('/visa-bulletin-history', { params: { category, country } }).then(res => res.data));
export const getDependentMultipliers = () =>
  cached('dependent-multipliers', () => api.get('/dependent-multipliers').then(res => res.data));
export const getI485Flow = () =>
  cached('i485-flow', () => api.get('/i485-flow').then(res => res.data));
export const getProcessingTimes = (category?: string, officeCode?: string) =>
  cached(`processing-times:${category}:${officeCode}`, () =>
    api.get('/processing-times', { params: { category, office_code: officeCode } }).then(res => res.data));
export const getPERMPipeline = () =>
  cached('perm-pipeline', () => api.get('/perm-pipeline').then(res => res.data));
export const getH1BDemand = () =>
  cached('h1b-demand', () => api.get('/h1b-demand').then(res => res.data));
export const getOppenheimPrediction = (category?: string, monthsAhead?: number, materializationRate?: number, applyRealRestrictions?: boolean) =>
  cached(`oppenheim:${category}:${monthsAhead}:${materializationRate}:${applyRealRestrictions}`, () =>
    api.get('/oppenheim', { params: { category, months_ahead: monthsAhead, materialization_rate: materializationRate, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data));

// Strongly typed API response shapes (mirrors backend Pydantic models)
export interface WaterfallData {
  // Full INA cascade
  eb_base_limit: number;
  fb_spillover: number;
  total_eb_pool: number;
  eb1_from_pool: number;
  eb45_spillover: number;
  total_eb1: number;
  // India EB-1
  india_eb1_baseline: number;
  india_eb1_supply: number;
  non_india_eb1: number;
  // Savings breakdown
  fb_savings: number;
  eb1_savings: number;
  eb45_savings: number;
  eb23_savings: number;
  // Per-country savings breakdown (empty objects under baseline)
  fb_savings_by_country: Record<string, number>;
  eb1_savings_by_country: Record<string, number>;
  eb45_savings_by_country: Record<string, number>;
  eb23_savings_by_country: Record<string, number>;
  // Data-driven inputs
  india_oversubscribed_share: number;
  non_india_eb1_demand: number;
  eb45_total_usage: number;
}

export interface TrajectoryPoint {
  date: string;
  backlog: number;
}

export interface SupplyDemandData {
  inventory: Record<string, number>;
  pipeline_total: number;
  nvc_backlog: Record<string, unknown> | null;
  total_queue: number;
  annual_eb1_supply: number;
  supply_by_fy: Record<string, number>;
  clearance_date: string;
  months_to_clear: number;
  trajectory: TrajectoryPoint[];
}

export interface PredictData {
  confidence_score: number;
  backlog_ahead: number;
  total_queue: number;
  annual_eb1_supply: number;
  projected_clearance_date: string;
  months_to_clear: number;
  trajectory: TrajectoryPoint[];
  // DOF estimate (data-driven from VB history)
  dof_estimate_date: string | null;
  dof_lead_months: number;
  dof_range_min: number;
  dof_range_max: number;
  dof_datapoints: number;
  // Current VB status (actual, not estimated)
  vb_bulletin_month: string | null;
  vb_current_fad: string | null;
  vb_current_dof: string | null;
  vb_fad_is_current: boolean;
  vb_dof_is_current: boolean;
  // null when category Unavailable (unknown until numbers resume)
  vb_fad_remaining_months: number | null;
  vb_dof_remaining_months: number | null;
  // Status: "date" | "C" | "U" — always present from API (may be null)
  vb_fad_status: string | null;
  vb_dof_status: string | null;
  vb_fad_unavailable: boolean;
  vb_dof_unavailable: boolean;
}

export interface VBHistoryRow {
  bulletin_month: string;
  category: string;
  fad: string | null;
  dof: string | null;
  fad_status: string;
  dof_status: string;
  fad_unavailable: boolean;
  dof_unavailable: boolean;
}

export interface VBHistoryData {
  categories: string[];
  total_rows: number;
  history: VBHistoryRow[];
}

export interface DataSource {
  name: string;
  description: string;
  url: string;
  coverage: string;
  update_frequency: string;
}

export interface LegalStatus {
  policy: string;
  description: string;
  status: string;
  model_impact: string;
}

export interface MethodologyData {
  restricted_countries: string[];
  restricted_countries_count: number;
  india_eb1_baseline: number;
  eb_base_limit: number;
  fb_statutory_limit: number;
  dependent_multiplier: number;
  data_sources: DataSource[];
  legal_status: LegalStatus[];
  last_verified: string;
}

export interface ProcessingTimePoint {
  publication_date: string;
  office_code: string;
  office_name: string;
  form_type: string;
  category: string;
  processing_time_min_months: number;
  processing_time_max_months: number;
  receipt_date_for_inquiry: string;
}

export interface ProcessingTimesData {
  time_series: ProcessingTimePoint[];
  latest: ProcessingTimePoint[];
  summary: {
    publication_date: string;
    data_points: number;
    months_of_data: number;
    coverage: string;
    centers: string[];
    eb1_fastest_center: string;
    eb1_fastest_center_name: string;
    eb1_fastest_midpoint: number;
    eb1_slowest_center: string;
    eb1_slowest_center_name: string;
    eb1_slowest_midpoint: number;
    eb1_trend: string;
    by_category: Record<string, {
      avg_min_months: number;
      avg_max_months: number;
      avg_midpoint_months: number;
      avg_spread_months: number;
      centers_count: number;
      fastest_center: string;
      slowest_center: string;
    }>;
  };
}

export interface I485FlowPoint {
  period: string;
  year: number;
  month: number;
  source: string;
  months_covered: number;
  eb_receipts: number;
  eb_approvals: number;
  eb_denials: number;
  eb_pending: number;
  fb_receipts: number;
  fb_approvals: number;
  total_receipts: number;
  total_approvals: number;
  total_denials: number;
  total_pending: number;
  eb_net_flow: number;
  total_net_flow: number;
}

export interface I485FlowData {
  monthly: I485FlowPoint[];
  quarterly: I485FlowPoint[];
  summary: {
    latest_period: string;
    latest_eb_pending: number;
    latest_total_pending: number;
    avg_monthly_eb_receipts: number;
    avg_monthly_eb_approvals: number;
    avg_monthly_eb_net_flow: number;
    queue_trend: string;
    pending_trend_pct: number;
    data_points: number;
    coverage: string;
    source: string;
  };
}

export interface PERMFYData {
  fiscal_year: number;
  total: number;
  india: number;
  china: number;
  row: number;
  has_country_data: boolean;
}

export interface PERMCategoryData {
  fiscal_year: number;
  eb2: number;
  eb3: number;
  unknown: number;
  total: number;
}

export interface PERMIndiaPipeline {
  fiscal_year: number;
  eb2: number;
  eb3: number;
  unknown: number;
  total: number;
}

export interface PERMStatusData {
  fiscal_year: number;
  certified: number;
  certified_expired: number;
  denied: number;
  withdrawn: number;
  other: number;
  total: number;
  approval_rate: number;
}

export interface PERMTopCountry {
  country: string;
  total: number;
  pct: number;
}

export interface PERMPipelineData {
  by_fy: PERMFYData[];
  by_category: PERMCategoryData[];
  india_pipeline: PERMIndiaPipeline[];
  status_breakdown: PERMStatusData[];
  top_countries: PERMTopCountry[];
  summary: {
    total_cases: number;
    total_certified: number;
    total_india_certified: number;
    fiscal_years: number[];
    latest_fy: number | null;
    india_latest: {
      fiscal_year: number;
      total: number;
      eb2: number;
      eb3: number;
    } | Record<string, never>;
    india_yoy_growth_pct: number | null;
    data_points: number;
    source: string;
  };
}

export interface H1BCapRegistration {
  fiscal_year: number;
  total_registrations: number;
  eligible_registrations: number;
  unique_beneficiaries: number;
  multiple_registrations: number;
  selected_registrations: number;
  selection_rate: number;
  multiple_reg_pct: number;
}

export interface H1BIndiaDemand {
  fiscal_year: number;
  india_approvals: number;
  india_initial: number;
  india_continuing: number;
  india_share_pct: number;
  total_approvals: number;
  selected_registrations?: number;
  selection_rate?: number;
  total_registrations?: number;
  unique_beneficiaries?: number;
}

export interface H1BTopCountry {
  country: string;
  approvals: number;
  share_pct: number;
}

export interface H1BDemandData {
  cap_registrations: H1BCapRegistration[];
  india_demand: H1BIndiaDemand[];
  top_countries: H1BTopCountry[];
  summary: {
    registration_years: number[];
    approval_years: number[];
    latest_reg_fy: number | null;
    latest_total_registrations: number;
    latest_selected: number;
    latest_selection_rate: number;
    latest_unique_beneficiaries: number;
    latest_approval_fy: number | null;
    latest_india_approvals: number;
    latest_india_initial: number;
    latest_india_share_pct: number;
    latest_total_approvals: number;
    india_yoy_growth_pct: number | null;
    registration_yoy_growth_pct: number | null;
    source: string;
  };
}

// Legislation Tracker
export interface LegislationBill {
  id: string;
  bill_number: string;
  title: string;
  short_title: string;
  sponsor: string;
  introduced: string;
  status: string;
  status_detail: string;
  chamber: string;
  direction: string;
  likelihood: string;
  categories_affected: string[];
  scenario_id: string | null;
  key_provisions: string[];
  impact_summary: string;
}

export interface LegislationScenario {
  scenario_id: string;
  scenario_name: string;
  clearance_date: string;
  months_to_clear: number;
  annual_supply: number;
  inventory_total: number;
  delta_months: number;
  trajectory: TrajectoryPoint[];
}

export interface LegislationData {
  bills: LegislationBill[];
  scenarios: Record<string, LegislationScenario>;
  baseline: {
    clearance_date: string;
    months_to_clear: number;
    annual_supply: number;
    inventory_total: number;
    trajectory: TrajectoryPoint[];
  };
  last_updated: string;
}

export const getLegislation = () =>
  cached('legislation', () => api.get('/legislation').then(res => res.data));
export const getCEACScheduling = () =>
  cached('ceac-scheduling', () => api.get('/ceac-scheduling').then(res => res.data));
export const getI140Receipts = () =>
  cached('i140-receipts', () => api.get('/i140-receipts').then(res => res.data));

// VB Forecast
export interface VBForecastPoint {
  bulletin_month: string;
  predicted_fad: string | null;
  predicted_dof: string | null;
  fad_confidence_low: string | null;
  fad_confidence_high: string | null;
}

export interface VBHistoricalRow {
  bulletin_month: string;
  category: string;
  fad: string | null;
  dof: string | null;
  fad_status: string;
  dof_status: string;
  fad_unavailable: boolean;
  dof_unavailable: boolean;
}

export interface VBLatestActual {
  bulletin_month: string | null;
  fad: string | null;
  dof: string | null;
  fad_status: string | null;
  dof_status: string | null;
  fad_unavailable: boolean;
  dof_unavailable: boolean;
  forecast_anchor_fad: string | null;
}

export interface VBForecastData {
  category: string;
  country: string;
  forecast: VBForecastPoint[];
  historical: VBHistoricalRow[];
  latest_actual: VBLatestActual;
  stats: {
    recent_avg: number;
    recent_median: number;
    recent_stdev: number;
    overall_avg: number;
    seasonal_pattern: Record<string, number>;
    n_datapoints: number;
    retrogression_count: number;
    unavailable_months: number;
  };
  supply_factor: number;
  dof_gap_months: number;
  methodology: string;
}

export const getVBForecast = (category: string = 'EB-1', monthsAhead: number = 24, applyRealRestrictions: boolean = false) =>
  cached(`vb-forecast:${category}:${monthsAhead}:${applyRealRestrictions}`, () =>
    api.get('/vb-forecast', { params: { category, months_ahead: monthsAhead, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data));

// Predictor comparison (VB trend vs demand burn-down)
export interface PredictorCompareData {
  priority_date: string;
  category: string;
  apply_real_restrictions: boolean;
  demand_months_to_clear: number | null;
  demand_projected_clearance_date: string | null;
  demand_backlog_ahead: number | null;
  demand_annual_supply: number | null;
  demand_confidence_score: number | null;
  vb_months_to_current: number | null;
  vb_estimated_bulletin_month: string | null;
  vb_confidence: string | null;
  vb_latest_fad: string | null;
  vb_latest_fad_status: string | null;
  vb_fad_unavailable: boolean;
  vb_category_unavailable: boolean;
  vb_assumes_numbers_resume: boolean;
  vb_supply_factor: number | null;
  vb_recent_avg_days_per_month: number | null;
  months_delta: number | null;
  divergence_notes: string[];
  assumptions: Record<string, unknown>;
}

export const getPredictorCompare = (
  priorityDate: string,
  category: string = 'EB-1',
  applyRealRestrictions: boolean = false,
) =>
  cached(`predictor-compare:${priorityDate}:${category}:${applyRealRestrictions}`, () =>
    api.get('/predictor-compare', {
      params: {
        priority_date: priorityDate,
        category,
        apply_real_restrictions: applyRealRestrictions,
      },
    }).then(res => res.data));

// ---------------------------------------------------------------------------
// Prefetch all endpoints at app startup — fire in parallel, results cached
// for instant page navigation. User-driven params (predictPD with custom
// dates) aren't prefetched but get cached on first call.
// ---------------------------------------------------------------------------
export function prefetchAll() {
  getWaterfallData(false, false);
  getWaterfallData(false, true);
  getSupplyDemandData(false, false);
  getSupplyDemandData(false, true);
  getMethodology();
  getDependentMultipliers();
  getI485Flow();
  getProcessingTimes();
  getPERMPipeline();
  getH1BDemand();
  getLegislation();
  getCEACScheduling();
  getI140Receipts();
  getVBForecast('EB-1', 24, false);
  getOppenheimPrediction('EB-1', 12, undefined, true);
}

// CEAC Scheduling
export interface CEACIssuancePoint {
  month: string;
  eb1_issuances: number;
  eb1_principal: number;
}

export interface CEACPostSummary {
  post: string;
  post_name: string;
  total_eb1: number;
  total_principal: number;
  months_active: number;
}

export interface CEACFYData {
  fiscal_year: number;
  total_eb1: number;
  principal_eb1: number;
  india_eb1: number;
  india_principal: number;
}

export interface CEACNVCWaitPoint {
  date: string;
  days: number;
}

export interface CEACSchedulingData {
  india_monthly: CEACIssuancePoint[];
  fiscal_year_data: CEACFYData[];
  top_posts: CEACPostSummary[];
  nvc_wait_times: Record<string, CEACNVCWaitPoint[]>;
  nvc_latest: Record<string, number>;
  data_range: {
    start: string;
    end: string;
    records: number;
    posts: number;
  };
  summary: {
    data_range: { start: string; end: string; records: number; posts: number };
    latest_complete_fy: {
      fiscal_year: number;
      total_eb1: number;
      principal_eb1: number;
      india_eb1: number;
      india_principal: number;
    };
    fiscal_year_data: CEACFYData[];
    top_posts_eb1: CEACPostSummary[];
    nvc_wait_times: Record<string, number>;
    india_posts: { slug: string; name: string }[];
    source: string;
    notes: Record<string, string>;
  };
}

// I-140 Receipts (New Filings)
export interface I140ReceiptFYData {
  fiscal_year: number;
  receipts: number;
  approved: number;
  denied: number;
  pending: number;
  approval_rate: number;
  eb1_receipts: number;
  eb2_receipts: number;
  eb3_receipts: number;
}

export interface I140ReceiptGrowth {
  fiscal_year: number;
  receipts: number;
  yoy_growth_pct: number | null;
  eb1_growth_pct: number | null;
  eb2_growth_pct: number | null;
  eb3_growth_pct: number | null;
}

export interface I140ReceiptCountry {
  country: string;
  receipts: number;
  eb1: number;
  eb2: number;
  eb3: number;
  share_pct: number;
}

export interface I140ReceiptsData {
  all_countries: I140ReceiptFYData[];
  india: I140ReceiptFYData[];
  growth_rates: I140ReceiptGrowth[];
  india_growth_rates: I140ReceiptGrowth[];
  country_comparison: I140ReceiptCountry[];
  summary: {
    fiscal_years: number[];
    latest_fy: number;
    latest_total_receipts: number;
    latest_total_approved: number;
    latest_total_pending: number;
    latest_approval_rate: number;
    india_queue_growth: {
      latest_fy: number;
      latest_receipts: number;
      latest_eb1: number;
      latest_eb2: number;
      latest_eb3: number;
      yoy_growth_pct: number | null;
      india_share_pct: number;
      cagr_5yr_pct: number;
      total_pending_all_fy: number;
      approval_rate: number;
    };
    top_countries: I140ReceiptCountry[];
    data_points: number;
    source: string;
  };
}

// Oppenheim FAD Solver (demand-supply equilibrium prediction)
export interface OppenheimPredictionPoint {
  bulletin_month: string;
  predicted_fad: string | null;
  is_current: boolean;
  fad_low: string | null;
  fad_high: string | null;
  cumulative_demand: number;
  target_monthly_supply: number;
  materialization_rate: number;
  fiscal_year: number;
  remaining_annual_supply?: number;
}

export interface OppenheimData {
  category: string;
  country: string;
  calibration: {
    current_fad: string;
    demand_at_fad: number;
    total_demand: number;
    total_demand_i485_only: number;
    shadow_demand_ratio: number;
    annual_supply: number;
    monthly_supply: number;
    calibrated_rate: number;
    current_rate: number;
  };
  next_fad: {
    bulletin_month: string;
    predicted_fad: string | null;
    is_current: boolean;
    fad_low: string | null;
    fad_high: string | null;
    cumulative_demand: number;
    target_monthly_supply: number;
    annual_supply: number;
    materialization_rate: number;
    fiscal_year: number;
    current_fad: string | null;
    latest_bulletin: string | null;
    advancement_days: number | null;
    total_demand: number;
    methodology: string;
  };
  trajectory: OppenheimPredictionPoint[];
  methodology: string;
}
