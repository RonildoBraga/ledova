export interface GetOnRampWidgetRequest {
  walletUuid: string;
  fiatAmount?: number;
  fiatCurrency?: string;
  cryptoCurrency?: string;
}

export interface OnRampWidgetResponse {
  url: string;
  walletAddress: string;
  chain: string;
  cryptoCurrency?: string;
}
