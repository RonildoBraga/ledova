import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { WalletIcon, KeyIcon, QrCodeIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { WalletType } from '@ledova/shared-types';

interface WalletTypeSelectorProps {
  onSelect: (type: WalletType) => void;
}

const WALLET_TYPE_OPTIONS: {
  type: WalletType;
  label: string;
  description: string;
  Icon: typeof KeyIcon;
}[] = [
  {
    type: 'software',
    label: 'Software Wallet',
    description: 'Generate a wallet on this device',
    Icon: KeyIcon,
  },
  {
    type: 'hardware',
    label: 'Hardware Wallet',
    description: 'Connect a hardware wallet via QR',
    Icon: QrCodeIcon,
  },
];

export function WalletTypeSelector({ onSelect }: WalletTypeSelectorProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    heroSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    optionsContainer: {
      gap: theme.spacing.sm,
    },
    option: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      gap: theme.spacing.md,
    },
    iconContainer: {
      width: theme.icon.sizes.hero,
      height: theme.icon.sizes.hero,
      borderRadius: theme.borderRadius.full,
      backgroundColor: theme.colors.surface.raised,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textContainer: {
      flex: 1,
    },
    optionLabel: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
    },
    optionDescription: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  return (
    <View>
      <View style={styles.heroSection}>
        <WalletIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.heroSubtitle}>Choose how to add your wallet</Text>
      </View>

      <View style={styles.optionsContainer}>
        {WALLET_TYPE_OPTIONS.map(({ type, label, description, Icon }) => (
          <TouchableOpacity key={type} style={styles.option} onPress={() => onSelect(type)} activeOpacity={0.7}>
            <View style={styles.iconContainer}>
              <Icon size={theme.icon.sizes.md} color={theme.colors.interactive.active} weight="regular" />
            </View>
            <View style={styles.textContainer}>
              <Text style={styles.optionLabel}>{label}</Text>
              <Text style={styles.optionDescription}>{description}</Text>
            </View>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}
