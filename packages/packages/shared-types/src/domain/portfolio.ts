import type { BaseEntity } from '../common';
import type { TimeSeriesQueryParams } from '../api';
import type { Wallet } from './wallet';

export interface Portfolio extends BaseEntity {
  userAccount: string;
  name: string;
  template: string | null;
  isActive: boolean;
  walletUuids: string[];
  walletCount: number;
  totalValue: string;
  wallets?: Wallet[];
}

export type CreatePortfolio = Omit<Portfolio, 'uuid' | 'createdAt' | 'updatedAt' | 'totalValue' | 'userAccount'>;
export type UpdatePortfolio = Partial<Omit<Portfolio, 'uuid' | 'createdAt' | 'updatedAt' | 'totalValue'>>;

export type PortfolioSnapshotReason = 'DAILY' | 'SWAP' | 'MANUAL';

export interface PortfolioSnapshot extends BaseEntity {
  portfolio: string;
  portfolioName?: string;
  accountId?: string;
  holdingsData: Record<
    string,
    {
      symbol: string;
      quantity: string;
      price?: string;
      marketValue?: string;
      wallets?: Array<{ walletUuid: string; quantity: string }>;
    }
  >;
  totalMarketValue?: string;
  snapshotDate: string;
  snapshotReason: PortfolioSnapshotReason;
}

/**
 * Query parameters for portfolio snapshot endpoints.
 * Extends TimeSeriesQueryParams for limit-based pagination with date range filtering.
 *
 * NAMING CONVENTION: Query params use snake_case following REST API URL standards.
 */
export interface PortfolioSnapshotQueryParams extends TimeSeriesQueryParams {
  portfolio?: string;
  user_account?: string;
  user_profile?: string;
  snapshot_reason?: PortfolioSnapshotReason;
}

/**
 * Data point for portfolio chart visualization.
 * Represents a single point in time with aggregated portfolio values.
 */
export interface PortfolioSnapshotDataPoint {
  dayIndex: number;
  date: string;
  totalMarketValue: number;
  assetValues: Record<string, number>;
  assetQuantities: Record<string, number>;
  assetSymbols: string[];
}
