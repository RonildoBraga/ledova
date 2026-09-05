import {
  CoinIcon,
  CurrencyBtcIcon,
  CurrencyCircleDollarIcon,
  CurrencyEthIcon,
  CertificateIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import type { IconWeight } from '@phosphor-icons/react';

interface AssetTypeIconProps {
  assetType: string;
  symbol?: string;
  size?: number;
  className?: string;
  weight?: IconWeight;
}

export function AssetTypeIcon({
  assetType,
  symbol,
  size = DESIGN_TOKENS.icon.sizes.sm,
  className = 'text-text-muted',
  weight = 'light',
}: AssetTypeIconProps) {
  switch (assetType) {
    case 'native_crypto':
      if (symbol === 'BTC') return <CurrencyBtcIcon size={size} className={className} weight={weight} />;
      return <CurrencyEthIcon size={size} className={className} weight={weight} />;
    case 'stablecoin':
      return <CurrencyCircleDollarIcon size={size} className={className} weight={weight} />;
    case 'tokenized_security':
    case 'tokenized_rwa':
      return <CertificateIcon size={size} className={className} weight={weight} />;
    case 'erc20_token':
    case 'synthetic':
    default:
      return <CoinIcon size={size} className={className} weight={weight} />;
  }
}
