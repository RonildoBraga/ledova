import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { SortAscendingIcon, StarIcon, TagIcon, CheckIcon } from 'phosphor-react-native';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export type SortOption = 'assetType' | 'favourites' | 'alphabetical';

interface AssetSortModalProps {
  visible: boolean;
  selectedSort: SortOption;
  onClose: () => void;
  onSelectSort: (sortOption: SortOption) => void;
}

export function AssetSortModal({ visible, selectedSort, onClose, onSelectSort }: AssetSortModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    header: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
      marginBottom: theme.spacing.md,
    },
    headerIcon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    optionsContainer: {
      gap: theme.spacing.sm,
    },
    optionItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: theme.spacing.md,
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
      width: 40,
      height: 40,
      borderRadius: theme.borderRadius.full,
      backgroundColor: theme.colors.surface.raised,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: theme.spacing.md,
    },
    optionContent: {
      flex: 1,
    },
    optionLabel: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      marginBottom: 2,
    },
    optionLabelSelected: {
      color: theme.colors.interactive.active,
    },
    optionDescription: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
  }));
  const sortOptions: Array<{ id: SortOption; label: string; icon: React.ReactNode; description: string }> = [
    {
      id: 'assetType',
      label: 'Asset Type',
      icon: <TagIcon size={theme.icon.sizes.md} color={theme.colors.text.primary} weight="regular" />,
      description: 'Group by cryptocurrency, stock, etc.',
    },
    {
      id: 'favourites',
      label: 'Favourites',
      icon: <StarIcon size={theme.icon.sizes.md} color={theme.colors.status.warning.icon} weight="fill" />,
      description: 'Show favourites first',
    },
    {
      id: 'alphabetical',
      label: 'Alphabetical',
      icon: <SortAscendingIcon size={theme.icon.sizes.md} color={theme.colors.text.primary} weight="regular" />,
      description: 'Sort by name (A-Z)',
    },
  ];

  const handleSelectSort = (sortOption: SortOption) => {
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
      {/* Header */}
      <View style={styles.header}>
        <SortAscendingIcon
          size={theme.icon.sizes.xl}
          color={theme.colors.interactive.active}
          weight="regular"
          style={styles.headerIcon}
        />
        <Text style={styles.title}>Sort Assets</Text>
        <Text style={styles.subtitle}>Choose how to organize your asset list</Text>
      </View>

      {/* Sort Options */}
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
                <View style={styles.optionContent}>
                  <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>{option.label}</Text>
                  <Text style={styles.optionDescription}>{option.description}</Text>
                </View>
              </View>
              {isSelected && (
                <CheckIcon size={theme.icon.sizes.md} color={theme.colors.interactive.active} weight="bold" />
              )}
            </TouchableOpacity>
          );
        })}
      </View>
    </CustomModal>
  );
}
