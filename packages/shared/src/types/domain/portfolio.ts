import type { BaseEntity } from '../common';
import type { TimeSeriesQueryParams } from '../api';

export interface Portfolio extends BaseEntity {
  userAccount: string;
  name: string;
  isActive: boolean;
  walletUuids: string[];
  walletCount: number;
}

/** The value series is computed on read; every emitted row is a DAILY point. */
export type PortfolioSnapshotReason = 'DAILY';

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
