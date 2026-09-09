import type { BaseEntity } from '../common';
import type { BaseQueryParams } from '../api';
import type { Asset, ValueSource } from './asset';

export interface WalletHolding extends BaseEntity {
  walletUuid: string;
  walletAddress: string;
  chain: string;
  asset: Asset;
  assetSymbol: string;
  assetName: string;
  quantity: string;
  marketValue: string | null;
  valueSource: ValueSource;
  lastSyncedAt: string;
}

export interface HoldingsQueryParams extends BaseQueryParams {
  wallet?: string;
  asset_type?: string;
  network?: string;
  max_value?: number;
}

export interface WalletInfo {
  uuid: string;
  name: string | undefined;
  address: string;
  chain: string;
}

export interface HoldingWithWallet extends WalletHolding {
  walletInfo: WalletInfo;
}

export interface AssetTypeSummary {
  assetType: string;
  label: string;
  totalValue: number;
  holdingsCount: number;
}

export interface HoldingsSummary {
  totalValue: number;
  holdingsCount: number;
  walletsCount: number;
  byAssetType: AssetTypeSummary[];
}

export type AllocationBasis = 'value' | 'quantity' | 'unpriced';

export interface AssetChainSlice {
  chain: string;
  quantity: number;
  totalValue: number;
  priced: boolean;
}

export interface AssetAllocationItem {
  assetUuid: string;
  symbol: string;
  name: string;
  totalValue: number;
  percentage: number;
  basis: AllocationBasis;
  source: ValueSource;
  color: string;
  totalQuantity: number;
  perChain: AssetChainSlice[];
  navPerToken?: string | null;
}

export interface WalletTotals {
  btc: number;
  eth: number;
  base: number;
  btcMarketValue: number;
  ethMarketValue: number;
  baseMarketValue: number;
  btcTotalMarketValue: number;
  ethTotalMarketValue: number;
  baseTotalMarketValue: number;
}
