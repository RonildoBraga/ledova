/**
 * Asset type classification - must match backend AssetType enum in assets/models/asset.py
 *
 * Backend source of truth:
 * - NATIVE_CRYPTO: BTC, ETH, SOL (chain-native coins)
 * - ERC20_TOKEN: LINK, UNI, AAVE (ERC-20 tokens on Ethereum)
 * - STABLECOIN: USDC, USDT, DAI
 * - TOKENIZED_SECURITY: AAPL.t, VAS.t
 * - TOKENIZED_RWA: US Treasuries, bonds
 * - SYNTHETIC: Synthetic tracking tokens
 */
export const HOLDING_ASSET_TYPE = {
  NATIVE_CRYPTO: 'native_crypto',
  ERC20_TOKEN: 'erc20_token',
  STABLECOIN: 'stablecoin',
  TOKENIZED_SECURITY: 'tokenized_security',
  TOKENIZED_RWA: 'tokenized_rwa',
  SYNTHETIC: 'synthetic',
} as const;

export type HoldingAssetType = (typeof HOLDING_ASSET_TYPE)[keyof typeof HOLDING_ASSET_TYPE];

const HOLDING_ASSET_TYPE_LABELS: Record<string, string> = {
  [HOLDING_ASSET_TYPE.NATIVE_CRYPTO]: 'Native Cryptocurrencies',
  [HOLDING_ASSET_TYPE.ERC20_TOKEN]: 'ERC-20 Tokens',
  [HOLDING_ASSET_TYPE.STABLECOIN]: 'Stablecoins',
  [HOLDING_ASSET_TYPE.TOKENIZED_SECURITY]: 'Tokenized Securities',
  [HOLDING_ASSET_TYPE.TOKENIZED_RWA]: 'Real World Assets',
  [HOLDING_ASSET_TYPE.SYNTHETIC]: 'Synthetic Assets',
};

export function getHoldingAssetTypeLabel(assetType: string): string {
  return HOLDING_ASSET_TYPE_LABELS[assetType] || 'Other Assets';
}
