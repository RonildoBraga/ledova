import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import {
  FunnelIcon,
  CurrencyBtcIcon,
  CurrencyEthIcon,
  ListBulletsIcon,
  ShieldCheckIcon,
  SortAscendingIcon,
  TagIcon,
  CurrencyCircleDollarIcon,
  CoinsIcon,
  CheckIcon,
} from 'phosphor-react-native';
import { CustomModal } from '../modal';
import { useAppTheme, useThemedStyles } from '../../contexts';

export type WalletChainFilter = 'all' | 'btc' | 'eth';
export type WalletSortOption = 'default' | 'verified' | 'name' | 'namedFirst' | 'highestValue' | 'highestBalance';

interface WalletSortModalProps {
  visible: boolean;
  selectedChain: WalletChainFilter;
  selectedSort: WalletSortOption;
  onClose: () => void;
  onApply: (chain: WalletChainFilter, sort: WalletSortOption) => void;
}

export function WalletSortModal({ visible, selectedChain, selectedSort, onClose, onApply }: WalletSortModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    header: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xs,
      marginBottom: theme.spacing.sm,
    },
    headerIcon: {
      marginBottom: theme.spacing.xs,
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    sectionLabel: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.subtle,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      marginBottom: theme.spacing.xs,
    },
    chainContainer: {
      flexDirection: 'row',
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.md,
    },
    chainChip: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 2,
      borderColor: 'transparent',
    },
    chainChipSelected: {
      borderColor: theme.colors.interactive.default,
      backgroundColor: theme.colors.surface.disabled,
    },
    chainChipLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    chainChipLabelSelected: {
      color: theme.colors.interactive.active,
    },
    optionsContainer: {
      gap: theme.spacing.xs,
    },
    optionItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 2,
      borderColor: 'transparent',
    },
    optionItemSelected: {
      borderColor: theme.colors.interactive.default,
      backgroundColor: theme.colors.surface.disabled,
    },
    optionLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      flex: 1,
    },
    iconContainer: {
      width: 32,
      height: 32,
      borderRadius: theme.borderRadius.full,
      backgroundColor: theme.colors.surface.raised,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: theme.spacing.sm,
    },
    optionContent: {
      flex: 1,
    },
    optionLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      marginBottom: 1,
    },
    optionLabelSelected: {
      color: theme.colors.interactive.active,
    },
    optionDescription: {
      fontSize: 11,
      color: theme.colors.text.muted,
    },
  }));

  const chainOptions: Array<{ id: WalletChainFilter; label: string; icon: React.ReactNode }> = [
    {
      id: 'all',
      label: 'All',
      icon: <ListBulletsIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
    {
      id: 'btc',
      label: 'BTC',
      icon: <CurrencyBtcIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
    {
      id: 'eth',
      label: 'ETH',
      icon: <CurrencyEthIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
  ];

  const sortOptions: Array<{ id: WalletSortOption; label: string; icon: React.ReactNode; description: string }> = [
    {
      id: 'default',
      label: 'Default',
      icon: <ListBulletsIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
      description: 'Hardware wallets first',
    },
    {
      id: 'verified',
      label: 'Verified First',
      icon: <ShieldCheckIcon size={theme.icon.sizes.sm} color={theme.colors.status.success.icon} weight="regular" />,
      description: 'Show verified wallets first',
    },
    {
      id: 'name',
      label: 'Alphabetical',
      icon: <SortAscendingIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
      description: 'Sort by name (A-Z)',
    },
    {
      id: 'namedFirst',
      label: 'Named First',
      icon: <TagIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
      description: 'Wallets with names before unnamed',
    },
    {
      id: 'highestValue',
      label: 'Highest Value',
      icon: <CurrencyCircleDollarIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
      description: 'Sort by market value (highest first)',
    },
    {
      id: 'highestBalance',
      label: 'Most Coins',
      icon: <CoinsIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
      description: 'Sort by native balance (highest first)',
    },
  ];

  const [localChain, setLocalChain] = React.useState<WalletChainFilter>(selectedChain);
  const [localSort, setLocalSort] = React.useState<WalletSortOption>(selectedSort);

  // Sync local state when modal opens
  React.useEffect(() => {
    if (visible) {
      setLocalChain(selectedChain);
      setLocalSort(selectedSort);
    }
  }, [visible, selectedChain, selectedSort]);

  const handleApply = () => {
    onApply(localChain, localSort);
    onClose();
  };

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      showCancelButton={true}
      cancelLabel="Close"
      confirmLabel="Apply"
      onCancel={onClose}
      onConfirm={handleApply}
    >
      {/* Header */}
      <View style={styles.header}>
        <FunnelIcon
          size={theme.icon.sizes.lg}
          color={theme.colors.interactive.active}
          weight="regular"
          style={styles.headerIcon}
        />
        <Text style={styles.title}>Sort Wallets</Text>
      </View>

      {/* Chain Filter */}
      <Text style={styles.sectionLabel}>Chain</Text>
      <View style={styles.chainContainer}>
        {chainOptions.map((option) => {
          const isSelected = localChain === option.id;
          return (
            <TouchableOpacity
              key={option.id}
              style={[styles.chainChip, isSelected && styles.chainChipSelected]}
              onPress={() => setLocalChain(option.id)}
              activeOpacity={0.7}
            >
              {option.icon}
              <Text style={[styles.chainChipLabel, isSelected && styles.chainChipLabelSelected]}>{option.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Sort Options */}
      <Text style={styles.sectionLabel}>Sort By</Text>
      <View style={styles.optionsContainer}>
        {sortOptions.map((option) => {
          const isSelected = localSort === option.id;
          return (
            <TouchableOpacity
              key={option.id}
              style={[styles.optionItem, isSelected && styles.optionItemSelected]}
              onPress={() => setLocalSort(option.id)}
              activeOpacity={0.7}
            >
              <View style={styles.optionLeft}>
                <View style={styles.iconContainer}>{option.icon}</View>
                <View style={styles.optionContent}>
                  <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>{option.label}</Text>
                  <Text style={styles.optionDescription}>{option.description}</Text>
                </View>
              </View>
              {isSelected && (
                <CheckIcon size={theme.icon.sizes.sm} color={theme.colors.interactive.active} weight="bold" />
              )}
            </TouchableOpacity>
          );
        })}
      </View>
    </CustomModal>
  );
}
