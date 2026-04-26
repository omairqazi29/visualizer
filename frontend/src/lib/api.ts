import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

export const getWaterfallData = () => api.get('/waterfall').then(res => res.data);
export const getSupplyDemandData = () => api.get('/supply-demand').then(res => res.data);
export const predictPD = (priorityDate: string, burnRate: number) => 
  api.get('/predict', { params: { priority_date: priorityDate, burn_rate: burnRate } }).then(res => res.data);
