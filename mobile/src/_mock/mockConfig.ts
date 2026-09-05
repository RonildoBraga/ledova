export const MOCK_ASSETS = [
  { uuid: 'btc-uuid', symbol: 'BTC', name: 'Bitcoin' },
  { uuid: 'eth-uuid', symbol: 'ETH', name: 'Ethereum' },
  { uuid: 'sol-uuid', symbol: 'SOL', name: 'Solana' },
  { uuid: 'matic-uuid', symbol: 'MATIC', name: 'Polygon' },
] as const;

const MOCK_ASSET_PRICES = {
  BTC: 45000,
  ETH: 3500,
  SOL: 120,
  MATIC: 1.2,
} as const;

const MOCK_ASSET_QUANTITIES = {
  BTC: 0.5,
  ETH: 2.5,
  SOL: 100,
  MATIC: 5000,
} as const;

export const MOCK_ASSET_VALUES = {
  BTC: MOCK_ASSET_PRICES.BTC * MOCK_ASSET_QUANTITIES.BTC,
  ETH: MOCK_ASSET_PRICES.ETH * MOCK_ASSET_QUANTITIES.ETH,
  SOL: MOCK_ASSET_PRICES.SOL * MOCK_ASSET_QUANTITIES.SOL,
  MATIC: MOCK_ASSET_PRICES.MATIC * MOCK_ASSET_QUANTITIES.MATIC,
} as const;

export const MOCK_WALLETS = [
  { uuid: 'wallet-1', name: 'Main Wallet', address: '0x1234...5678', chain: 'Ethereum' },
  { uuid: 'wallet-2', name: 'Trading Wallet', address: '0xabcd...efgh', chain: 'Polygon' },
] as const;
