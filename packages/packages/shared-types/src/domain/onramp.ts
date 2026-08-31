/**
 * Types for fiat on-ramp widget integration (Transak).
 */

/**
 * Request to get widget URL for Transak
 */
export interface GetOnRampWidgetRequest {
  walletUuid: string;
  fiatAmount?: number;
  fiatCurrency?: string;
  cryptoCurrency?: string;
}

/**
 * Response with Transak widget configuration
 */
export interface OnRampWidgetResponse {
  url: string;
  walletAddress: string;
  chain: string;
  cryptoCurrency?: string;
}
