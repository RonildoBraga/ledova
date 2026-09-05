import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { StarIcon } from 'phosphor-react-native';
import type { Asset } from '@ledova/shared';
import { useCurrency } from '../../../hooks/useCurrency';
import { AssetTypeIcon } from '../../../components/AssetTypeIcon';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface AssetListItemProps {
  asset: Asset;
  onPress: (asset: Asset) => void;
  isFavourite?: boolean;
  onToggleFavourite?: (assetUuid: string) => void;
}

export function AssetListItem({ asset, onPress, isFavourite = false, onToggleFavourite }: AssetListItemProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      paddingVertical: theme.spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    main: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    leftSection: {
      flexDirection: 'row',
      gap: theme.spacing.xs,
      flex: 1,
      alignItems: 'center',
    },
    starButton: {
      marginRight: theme.spacing.xs,
    },
    symbolBadge: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.secondary,
      fontWeight: theme.fontWeight.semibold,
    },
    separator: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    name: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      flex: 1,
    },
    rightSection: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    price: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
  }));
  const currentPrice = asset.currentPrice ? parseFloat(asset.currentPrice) : null;

  const handleStarPress = () => {
    onToggleFavourite?.(asset.uuid);
  };

  return (
    <TouchableOpacity style={styles.container} onPress={() => onPress(asset)} activeOpacity={0.7}>
      <View style={styles.main}>
        <View style={styles.leftSection}>
          {onToggleFavourite && (
            <TouchableOpacity
              style={styles.starButton}
              onPress={handleStarPress}
              hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}
            >
              <StarIcon
                size={theme.icon.sizes.md}
                color={isFavourite ? theme.colors.status.warning.icon : theme.colors.text.subtle}
                weight={isFavourite ? 'fill' : 'regular'}
              />
            </TouchableOpacity>
          )}
          <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} />
          <Text style={styles.symbolBadge} numberOfLines={1}>
            {asset.symbol}
          </Text>
          <Text style={styles.separator}>•</Text>
          <Text style={styles.name} numberOfLines={1}>
            {asset.name}
          </Text>
        </View>
        <View style={styles.rightSection}>
          <Text style={styles.price} numberOfLines={1}>
            {currentPrice !== null ? formatDisplayCurrency(currentPrice) : 'N/A'}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}
