import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

export const getWaterfallData = (applyFreeze: boolean = false) => 
  api.get('/waterfall', { params: { apply_freeze: applyFreeze } }).then(res => res.data);
export const getSupplyDemandData = (applyFreeze: boolean = false) => 
  api.get('/supply-demand', { params: { apply_freeze: applyFreeze } }).then(res => res.data);
export const predictPD = (priorityDate: string, applyFreeze: boolean = false) => 
  api.get('/predict', { params: { priority_date: priorityDate, apply_freeze: applyFreeze } }).then(res => res.data);
