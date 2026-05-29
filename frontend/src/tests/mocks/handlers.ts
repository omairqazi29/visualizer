import { http, HttpResponse } from 'msw'
import type { WaterfallData, SupplyDemandData, PredictData, DataSourcesData } from '@/lib/api'

const API_BASE = 'http://localhost:8000/api'

export const mockWaterfallData: WaterfallData = {
  eb_base_limit: 140000,
  fb_spillover_std: 15000,
  fb_savings_freeze: 0,
  eb45_spillover_std: 3000,
  eb45_savings_freeze: 0,
  total_eb_supply: 158000,
  eb1_supply: 28000,
  india_eb1_supply: 9000,
}

export const mockWaterfallRealData: WaterfallData = {
  eb_base_limit: 140000,
  fb_spillover_std: 15000,
  fb_savings_freeze: 2000,
  eb45_spillover_std: 3000,
  eb45_savings_freeze: 1000,
  total_eb_supply: 161000,
  eb1_supply: 31000,
  india_eb1_supply: 10500,
}

export const mockWaterfallFreezeData: WaterfallData = {
  eb_base_limit: 140000,
  fb_spillover_std: 15000,
  fb_savings_freeze: 5000,
  eb45_spillover_std: 3000,
  eb45_savings_freeze: 2000,
  total_eb_supply: 165000,
  eb1_supply: 35000,
  india_eb1_supply: 12000,
}

export const mockSupplyDemandStandardData: SupplyDemandData = {
  inventory: { EB1: 5000 },
  pipeline_total: 10000,
  total_queue: 15000,
  annual_eb1_supply: 9000,
  monthly_inflow: 500,
  clearance_date: '2028-06-01',
  months_to_clear: 36,
  cleared: true,
  trajectory: [
    { date: '2025-06-01', backlog: 15000 },
    { date: '2025-07-01', backlog: 14500 },
  ],
}

export const mockSupplyDemandRealData: SupplyDemandData = {
  inventory: { EB1: 5000 },
  pipeline_total: 10000,
  total_queue: 15000,
  annual_eb1_supply: 10500,
  monthly_inflow: 500,
  clearance_date: '2027-09-01',
  months_to_clear: 28,
  cleared: true,
  trajectory: [
    { date: '2025-06-01', backlog: 15000 },
    { date: '2025-07-01', backlog: 14300 },
  ],
}

export const mockSupplyDemandFreezeData: SupplyDemandData = {
  inventory: { EB1: 5000 },
  pipeline_total: 10000,
  total_queue: 15000,
  annual_eb1_supply: 12000,
  monthly_inflow: 500,
  clearance_date: '2027-03-01',
  months_to_clear: 22,
  cleared: true,
  trajectory: [
    { date: '2025-06-01', backlog: 15000 },
    { date: '2025-07-01', backlog: 14000 },
  ],
}

export const mockPredictData: PredictData = {
  confidence_score: 0.85,
  backlog_ahead: 5000,
  total_queue: 15000,
  annual_eb1_supply: 9000,
  monthly_inflow: 500,
  target_fy: 2026,
  projected_clearance_date: '2028-06-01',
  months_to_clear: 36,
  cleared: true,
  trajectory: [
    { date: '2025-06-01', backlog: 15000 },
    { date: '2025-07-01', backlog: 14500 },
  ],
}

export const mockPredictFreezeData: PredictData = {
  confidence_score: 0.90,
  backlog_ahead: 5000,
  total_queue: 15000,
  annual_eb1_supply: 12000,
  monthly_inflow: 500,
  target_fy: 2026,
  projected_clearance_date: '2027-06-01',
  months_to_clear: 24,
  cleared: true,
  trajectory: [
    { date: '2025-06-01', backlog: 15000 },
    { date: '2025-07-01', backlog: 14000 },
  ],
}

export const mockDataSourcesData: DataSourcesData = {
  dos_directory: '/data/dos',
  dos_files: [
    { filename: 'issuances_2024_01.csv', parsed_date: '2024-01', exists: true },
  ],
  inventory_file: { filename: 'inventory.xlsx', parsed_date: null, exists: true },
  pipeline_file: { filename: 'pipeline.xlsx', parsed_date: null, exists: true },
}

export const handlers = [
  http.get(`${API_BASE}/waterfall`, ({ request }) => {
    const url = new URL(request.url)
    const applyFreeze = url.searchParams.get('apply_freeze') === 'true'
    const applyReal = url.searchParams.get('apply_real_restrictions') === 'true'
    if (applyFreeze) return HttpResponse.json(mockWaterfallFreezeData)
    if (applyReal) return HttpResponse.json(mockWaterfallRealData)
    return HttpResponse.json(mockWaterfallData)
  }),

  http.get(`${API_BASE}/supply-demand`, ({ request }) => {
    const url = new URL(request.url)
    const applyFreeze = url.searchParams.get('apply_freeze') === 'true'
    const applyReal = url.searchParams.get('apply_real_restrictions') === 'true'
    if (applyFreeze) return HttpResponse.json(mockSupplyDemandFreezeData)
    if (applyReal) return HttpResponse.json(mockSupplyDemandRealData)
    return HttpResponse.json(mockSupplyDemandStandardData)
  }),

  http.get(`${API_BASE}/predict`, ({ request }) => {
    const url = new URL(request.url)
    const applyFreeze = url.searchParams.get('apply_freeze') === 'true'
    return HttpResponse.json(applyFreeze ? mockPredictFreezeData : mockPredictData)
  }),

  http.get(`${API_BASE}/data-sources`, () => {
    return HttpResponse.json(mockDataSourcesData)
  }),
]
