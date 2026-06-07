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
