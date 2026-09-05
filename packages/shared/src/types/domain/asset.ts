import type { BaseQueryParams, TimeSeriesQueryParams } from '../api';

export interface AssetChainDeployment {
  uuid: string;
  chain: string;
  contractAddress: string | null;
  decimals: number;
  isActive: boolean;
}

export interface Asset {
  uuid: string;
  symbol: string;
  name: string;
  assetType: string;
  assetTypeDisplay?: string;
  settlementPermission?: string;
  regulatoryClassification?: string;
  chain: string | null;
  contractAddress: string | null;
  decimals: number;
  chainDeployments?: AssetChainDeployment[];
  navPerToken?: string | null;
  lastNavUpdate?: string | null;
  isYieldToken?: boolean;
  underlyingTicker?: string | null;
  issuerName?: string | null;
  isin?: string | null;
  currentPrice: string | null;
  priceCurrency: string;
  priceSource?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AssetQueryParams extends BaseQueryParams {
  uuid?: string;
  symbol?: string;
  name?: string;
  asset_type?: string;
  settlement_permission?: string;
  chain?: string;
  contract_address?: string;
  underlying_ticker?: string;
  is_active?: 'true' | 'false';
  min_price?: number;
  max_price?: number;
  search?: string;
  order_by?: string;
}

export interface AssetSnapshot {
  uuid: string;
  asset: string;
  assetName: string;
  assetSymbol: string;
  price: string;
  change: string;
  changePercent: string;
  sourceTimestamp: string;
}

export interface AssetSnapshotQueryParams extends TimeSeriesQueryParams {
  asset?: string;
  min_price?: number;
  max_price?: number;
}

export interface AssetFilters {
  search?: string;
  asset_type?: string;
  chain?: string;
}

export interface ExchangeRate {
  baseCurrency: string;
  targetCurrency: string;
  rate: string;
}
