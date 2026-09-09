import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { getActiveChains } from '@ledova/shared';
import { useThemedStyles } from '../../../contexts';

interface WalletNetworkSelectorProps {
  network: string;
  onChange: (network: string) => void;
  evmOnly?: boolean;
}

export function WalletNetworkSelector({ network, onChange, evmOnly = false }: WalletNetworkSelectorProps) {
  const styles = useThemedStyles((theme) => ({
    row: { flexDirection: 'row', gap: theme.spacing.sm, marginBottom: theme.spacing.md },
    option: {
      flex: 1,
      padding: theme.spacing.sm,
      borderWidth: 1,
      borderRadius: theme.borderRadius.md,
      borderColor: theme.colors.border.default,
    },
    selected: {
      borderColor: theme.colors.interactive.selected.border,
      backgroundColor: theme.colors.interactive.selected.background,
    },
    label: { color: theme.colors.text.primary, textAlign: 'center' },
  }));
  return (
    <View style={styles.row}>
      {getActiveChains()
        .filter((chain) => !evmOnly || chain.code === 'base' || chain.code === 'ethereum')
        .map((chain) => (
          <TouchableOpacity
            key={chain.code}
            accessibilityRole="radio"
            accessibilityLabel={`${chain.name} network`}
            accessibilityState={{ selected: network === chain.code }}
            style={[styles.option, network === chain.code && styles.selected]}
            onPress={() => onChange(chain.code)}
          >
            <Text style={styles.label}>{chain.name}</Text>
          </TouchableOpacity>
        ))}
    </View>
  );
}
