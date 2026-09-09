import { ONRAMP_ENDPOINTS } from '../constants';
import { AxiosInstance } from 'axios';
import type { GetOnRampWidgetRequest, OnRampWidgetResponse } from '../types';

export const getOnRampWidgetUrl = (apiClient: AxiosInstance, request: GetOnRampWidgetRequest) =>
  apiClient.post<OnRampWidgetResponse>(ONRAMP_ENDPOINTS.WIDGET_URL, {
    wallet_uuid: request.walletUuid,
    fiat_amount: request.fiatAmount,
    fiat_currency: request.fiatCurrency,
    crypto_currency_code: request.cryptoCurrency,
  });
