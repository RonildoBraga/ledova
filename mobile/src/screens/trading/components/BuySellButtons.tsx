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
  const buyLabel = tokenSymbol ? `New buy order — ${tokenSymbol}` : 'New buy order';
  const sellLabel = tokenSymbol ? `New sell order — ${tokenSymbol}` : 'New sell order';

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
