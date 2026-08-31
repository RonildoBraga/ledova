import type { Asset } from '@ledova/shared-types';

const ASSET_TYPE_LABELS = {
  native_crypto: 'Crypto',
  stablecoin: 'Stablecoin',
  tokenized_security: 'Tokenized Security',
  tokenized_rwa: 'Real-World Asset',
  synthetic: 'Synthetic',
} as const;

export function getAssetType(asset: Asset): string {
  return ASSET_TYPE_LABELS[asset.assetType as keyof typeof ASSET_TYPE_LABELS] || 'Synthetic';
}

export function getAssetTypeVariant(asset: Asset): 'primary' | 'warning' | 'success' | 'info' | 'neutral' {
  const variants: Record<string, 'primary' | 'warning' | 'success' | 'info' | 'neutral'> = {
    native_crypto: 'success',
    stablecoin: 'info',
    tokenized_security: 'primary',
    tokenized_rwa: 'warning',
    synthetic: 'neutral',
  };
  return variants[asset.assetType as string] || 'neutral';
}
