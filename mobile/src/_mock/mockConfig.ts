/**
 * Shared Mock Data Configuration
 *
 * This file contains the central configuration for all mock data across the application.
 * All mock data generators should use these values to ensure consistency.
 */

export const MOCK_ASSETS = [
  { uuid: 'btc-uuid', symbol: 'BTC', name: 'Bitcoin' },
  { uuid: 'eth-uuid', symbol: 'ETH', name: 'Ethereum' },
  { uuid: 'sol-uuid', symbol: 'SOL', name: 'Solana' },
  { uuid: 'matic-uuid', symbol: 'MATIC', name: 'Polygon' },
] as const;

/**
 * Base prices for each asset (in USD)
 * Used as the starting point for price calculations
 */
const MOCK_ASSET_PRICES = {
  BTC: 45000,
  ETH: 3500,
  SOL: 120,
  MATIC: 1.2,
} as const;

/**
 * Holdings quantities for each asset
 * These quantities are used across portfolio, holdings, and charts
 */
const MOCK_ASSET_QUANTITIES = {
  BTC: 0.5,
  ETH: 2.5,
  SOL: 100,
  MATIC: 5000,
} as const;

/**
 * Calculate total market values based on quantities and prices
 * This ensures consistency across all mock data
 */
export const MOCK_ASSET_VALUES = {
  BTC: MOCK_ASSET_PRICES.BTC * MOCK_ASSET_QUANTITIES.BTC, // 22,500
  ETH: MOCK_ASSET_PRICES.ETH * MOCK_ASSET_QUANTITIES.ETH, // 8,750
  SOL: MOCK_ASSET_PRICES.SOL * MOCK_ASSET_QUANTITIES.SOL, // 12,000
  MATIC: MOCK_ASSET_PRICES.MATIC * MOCK_ASSET_QUANTITIES.MATIC, // 6,000
} as const;

/**
 * Wallet configuration for mock data
 */
export const MOCK_WALLETS = [
  { uuid: 'wallet-1', name: 'Main Wallet', address: '0x1234...5678', chain: 'Ethereum' },
  { uuid: 'wallet-2', name: 'Trading Wallet', address: '0xabcd...efgh', chain: 'Polygon' },
] as const;
