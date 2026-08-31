import type { BaseEntity } from '../common';
import type { BaseQueryParams } from '../api';
import type { Asset } from './asset';

export interface WalletHolding extends BaseEntity {
  wallet: string;
  walletAddress: string;
  asset: Asset;
  assetSymbol: string;
  assetName: string;
  quantity: string;
  marketValue: string;
  lastSyncedAt: string;
}

export interface HoldingsQueryParams extends BaseQueryParams {
  wallet?: string;
  asset_type?: string;
  network?: string;
  min_value?: number;
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

export interface AssetAllocationItem {
  assetUuid: string;
  symbol: string;
  name: string;
  totalValue: number;
  percentage: number;
  color: string;
  navPerToken?: string | null;
  isYieldToken?: boolean;
}

export interface WalletTotals {
  btc: number;
  eth: number;
  btcMarketValue: number;
  ethMarketValue: number;
  btcTotalMarketValue: number;
  ethTotalMarketValue: number;
}
