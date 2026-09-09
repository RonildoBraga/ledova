import type { BaseEntity } from '../common';
import type { TimeSeriesQueryParams } from '../api';

export interface Portfolio extends BaseEntity {
  userAccount: string;
  name: string;
  isActive: boolean;
  walletUuids: string[];
  walletCount: number;
}

export type PortfolioSnapshotReason = 'DAILY';

export interface PortfolioSnapshotChain {
  chain: string;
  quantity: string;
  wallets: string[];
  marketValue?: string;
}

export interface PortfolioSnapshotHolding {
  assetUuid: string;
  quantity: string;
  price?: string;
  marketValue?: string;
  wallets: string[];
  perChain?: PortfolioSnapshotChain[];
}

export interface PortfolioSnapshot extends BaseEntity {
  portfolio: string;
  portfolioName?: string;
  accountId?: string;
  holdingsData: Record<string, PortfolioSnapshotHolding>;
  totalMarketValue?: string | null;
  hasValueData?: boolean;
  snapshotDate: string;
  snapshotReason: PortfolioSnapshotReason;
}

export interface PortfolioSnapshotQueryParams extends TimeSeriesQueryParams {
  portfolio?: string;
  user_account?: string;
  user_profile?: string;
}

export interface PortfolioSnapshotDataPoint {
  dayIndex: number;
  date: string;
  totalMarketValue: number;
  assetValues: Record<string, number>;
  assetHoldings: Record<string, PortfolioSnapshotHolding>;
  assetSymbols: string[];
}
