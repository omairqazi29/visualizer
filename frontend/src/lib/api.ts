import axios from 'axios';

// Use runtime env var when provided (Docker / production), fall back to localhost for dev.
const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL,
});

export const getWaterfallData = (applyFreeze: boolean = false) => 
  api.get('/waterfall', { params: { apply_freeze: applyFreeze } }).then(res => res.data);
export const getSupplyDemandData = (applyFreeze: boolean = false) => 
  api.get('/supply-demand', { params: { apply_freeze: applyFreeze } }).then(res => res.data);
export const predictPD = (priorityDate: string, applyFreeze: boolean = false) => 
  api.get('/predict', { params: { priority_date: priorityDate, apply_freeze: applyFreeze } }).then(res => res.data);

// Strongly typed API response shapes (mirrors backend Pydantic models)
export interface WaterfallData {
  eb_base_limit: number;
  fb_spillover_std: number;
  fb_savings_freeze: number;
  eb45_spillover_std: number;
  eb45_savings_freeze: number;
  total_eb_supply: number;
  eb1_supply: number;
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
}
