import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ClockCountdownIcon,
  ClockClockwiseIcon,
  CheckIcon,
  SortAscendingIcon,
} from 'phosphor-react-native';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export type TransactionSortOption = 'newest' | 'oldest' | 'highestValue' | 'lowestValue' | 'sent' | 'received';

interface TransactionSortModalProps {
  visible: boolean;
  selectedSort: TransactionSortOption;
  onClose: () => void;
  onSelectSort: (sortOption: TransactionSortOption) => void;
}

export function TransactionSortModal({ visible, selectedSort, onClose, onSelectSort }: TransactionSortModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    header: {
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      marginBottom: theme.spacing.sm,
    },
    headerIcon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    optionsContainer: {
      gap: theme.spacing.xs,
    },
    optionItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1.5,
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
    optionLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    optionLabelSelected: {
      color: theme.colors.interactive.active,
    },
  }));

  const sortOptions: Array<{
    id: TransactionSortOption;
    label: string;
    icon: React.ReactNode;
  }> = [
    {
      id: 'sent',
      label: 'Sent',
      icon: <ArrowUpIcon size={theme.icon.sizes.sm} color={theme.colors.status.error.icon} weight="regular" />,
    },
    {
      id: 'received',
      label: 'Received',
      icon: <ArrowDownIcon size={theme.icon.sizes.sm} color={theme.colors.status.success.icon} weight="regular" />,
    },
    {
      id: 'highestValue',
      label: 'Highest Value',
      icon: <SortAscendingIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
    {
      id: 'lowestValue',
      label: 'Lowest Value',
      icon: (
        <SortAscendingIcon
          size={theme.icon.sizes.sm}
          color={theme.colors.text.primary}
          weight="regular"
          style={{ transform: [{ scaleY: -1 }] }}
        />
      ),
    },
    {
      id: 'newest',
      label: 'Most Recent',
      icon: <ClockCountdownIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
    {
      id: 'oldest',
      label: 'Oldest First',
      icon: <ClockClockwiseIcon size={theme.icon.sizes.sm} color={theme.colors.text.primary} weight="regular" />,
    },
  ];

  const handleSelectSort = (sortOption: TransactionSortOption) => {
    onSelectSort(sortOption);
    onClose();
  };

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      showCancelButton={true}
      cancelLabel="Close"
      onCancel={onClose}
    >
      <View style={styles.header}>
        <SortAscendingIcon
          size={theme.icon.sizes.xl}
          color={theme.colors.interactive.active}
          weight="regular"
          style={styles.headerIcon}
        />
        <Text style={styles.title}>Sort Transactions</Text>
        <Text style={styles.subtitle}>Choose how to organize your transactions</Text>
      </View>

      <View style={styles.optionsContainer}>
        {sortOptions.map((option) => {
          const isSelected = selectedSort === option.id;

          return (
            <TouchableOpacity
              key={option.id}
              style={[styles.optionItem, isSelected && styles.optionItemSelected]}
              onPress={() => handleSelectSort(option.id)}
              activeOpacity={0.7}
            >
              <View style={styles.optionLeft}>
                <View style={styles.iconContainer}>{option.icon}</View>
                <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>{option.label}</Text>
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
