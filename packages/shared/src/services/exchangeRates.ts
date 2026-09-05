import { AxiosInstance } from 'axios';
import { ASSET_ENDPOINTS } from '../constants';
import type { ExchangeRate } from '../types';

export const getExchangeRate = (apiClient: AxiosInstance, currency: string = 'AUD') => {
  return apiClient.get<ExchangeRate>(ASSET_ENDPOINTS.EXCHANGE_RATES, {
    params: { currency },
  });
};
