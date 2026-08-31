import React from 'react';
import { ButtonGroup } from '../../../components/buttons';
import type { ViewStyle } from 'react-native';

interface BuySellButtonsProps {
  tokenSymbol?: string;
  onBuy: () => void;
  onSell: () => void;
  disabled?: boolean;
  style?: ViewStyle;
}

export function BuySellButtons({ tokenSymbol, onBuy, onSell, disabled, style }: BuySellButtonsProps) {
  const buyLabel = tokenSymbol ? `Buy ${tokenSymbol}` : 'Buy';
  const sellLabel = tokenSymbol ? `Sell ${tokenSymbol}` : 'Sell';

  return (
    <ButtonGroup
      secondaryButton={{
        label: sellLabel,
        onPress: onSell,
        disabled,
      }}
      primaryButton={{
        label: buyLabel,
        onPress: onBuy,
        disabled,
      }}
      style={style}
    />
  );
}
