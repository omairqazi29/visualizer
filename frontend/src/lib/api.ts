import axios from 'axios';

// Use runtime env var when provided (Docker / production), fall back to localhost for dev.
const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL,
});

export const getWaterfallData = (applyFreeze: boolean = false, applyRealRestrictions: boolean = false) => 
  api.get('/waterfall', { params: { apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data);
export const getSupplyDemandData = (applyFreeze: boolean = false, applyRealRestrictions: boolean = false) => 
  api.get('/supply-demand', { params: { apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data);
export const predictPD = (priorityDate: string, applyFreeze: boolean = false, applyRealRestrictions: boolean = false) => 
  api.get('/predict', { params: { priority_date: priorityDate, apply_freeze: applyFreeze, apply_real_restrictions: applyRealRestrictions } }).then(res => res.data);
export const getMethodology = () =>
  api.get('/methodology').then(res => res.data);
export const getI485Flow = () =>
  api.get('/i485-flow').then(res => res.data);
export const getProcessingTimes = (category?: string, officeCode?: string) =>
  api.get('/processing-times', { params: { category, office_code: officeCode } }).then(res => res.data);
export const getPERMPipeline = () =>
  api.get('/perm-pipeline').then(res => res.data);

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
  // Data-driven share
  india_oversubscribed_share: number;
}

export interface TrajectoryPoint {
  date: string;
  backlog: number;
}

export interface SupplyDemandData {
  inventory: Record<string, number>;
  pipeline_total: number;
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
  vb_fad_remaining_months: number;
  vb_dof_remaining_months: number;
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
