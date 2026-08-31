import { AxiosInstance } from 'axios';
import type { GetOnRampWidgetRequest, OnRampWidgetResponse } from '@ledova/shared-types';

/**
 * Get Transak widget URL for buying crypto
 */
export const getOnRampWidgetUrl = (apiClient: AxiosInstance, request: GetOnRampWidgetRequest) =>
  apiClient.post<OnRampWidgetResponse>('/api/fiat-purchases/transak-widget-url/', {
    wallet_uuid: request.walletUuid,
    fiat_amount: request.fiatAmount,
    fiat_currency: request.fiatCurrency,
    crypto_currency_code: request.cryptoCurrency,
  });
