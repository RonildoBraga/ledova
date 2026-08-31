import {
  CoinIcon,
  CurrencyBtcIcon,
  CurrencyCircleDollarIcon,
  CurrencyEthIcon,
  CertificateIcon,
} from 'phosphor-react-native';
import { useAppTheme } from '../contexts';
import type { IconWeight } from 'phosphor-react-native';

interface AssetTypeIconProps {
  assetType: string;
  symbol?: string;
  size?: number;
  color?: string;
  weight?: IconWeight;
}

export function AssetTypeIcon({ assetType, symbol, size, color, weight = 'light' }: AssetTypeIconProps) {
  const theme = useAppTheme();
  const iconSize = size ?? theme.icon.sizes.sm;
  const iconColor = color ?? theme.colors.text.muted;
  switch (assetType) {
    case 'native_crypto':
      if (symbol === 'BTC') return <CurrencyBtcIcon size={iconSize} color={iconColor} weight={weight} />;
      return <CurrencyEthIcon size={iconSize} color={iconColor} weight={weight} />;
    case 'stablecoin':
      return <CurrencyCircleDollarIcon size={iconSize} color={iconColor} weight={weight} />;
    case 'tokenized_security':
    case 'tokenized_rwa':
      return <CertificateIcon size={iconSize} color={iconColor} weight={weight} />;
    case 'erc20_token':
    case 'synthetic':
    default:
      return <CoinIcon size={iconSize} color={iconColor} weight={weight} />;
  }
}
