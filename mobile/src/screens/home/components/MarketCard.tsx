import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { ChartBarIcon, StarIcon } from 'phosphor-react-native';
import { Accordion } from '../../../components/accordion';
import { AssetTypeIcon } from '../../../components/AssetTypeIcon';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useCurrency } from '../../../hooks/useCurrency';
import type { Asset } from '@ledova/shared';

interface MarketCardProps {
  assets: Asset[];
  favouriteAssetUuids: Set<string>;
  isLoading: boolean;
  onAssetPress: (asset: Asset) => void;
}

export function MarketCard({ assets, favouriteAssetUuids, isLoading, onAssetPress }: MarketCardProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    panelContent: {
      minHeight: 60,
    },
    titleContainer: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.secondary,
    },
    assetsList: {
      gap: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
    },
    assetRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.xs,
    },
    leftSection: {
      flexDirection: 'row',
      gap: theme.spacing.xs,
      flex: 1,
      alignItems: 'center',
    },
    symbolBadge: {
      fontSize: theme.fontSize.sm,
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
    price: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    loadingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.sm,
      paddingVertical: theme.spacing.lg,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptyState: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.lg,
      gap: theme.spacing.xs,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  const renderLoading = () => (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="small" color={theme.colors.interactive.active} />
      <Text style={styles.loadingText}>Loading market data...</Text>
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyState}>
      <Text style={styles.emptyText}>No assets available</Text>
    </View>
  );

  const renderContent = () => (
    <View style={styles.assetsList}>
      {assets.map((asset) => {
        const currentPrice = asset.currentPrice ? parseFloat(asset.currentPrice) : null;
        const isFavourite = favouriteAssetUuids.has(asset.uuid);

        return (
          <TouchableOpacity
            key={asset.uuid}
            style={styles.assetRow}
            onPress={() => onAssetPress(asset)}
            activeOpacity={0.7}
          >
            <View style={styles.leftSection}>
              <StarIcon
                size={theme.icon.sizes.sm}
                color={isFavourite ? theme.colors.status.warning.icon : theme.colors.text.subtle}
                weight={isFavourite ? 'fill' : 'regular'}
              />
              <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} />
              <Text style={styles.symbolBadge} numberOfLines={1}>
                {asset.symbol}
              </Text>
              <Text style={styles.separator}>•</Text>
              <Text style={styles.name} numberOfLines={1}>
                {asset.name}
              </Text>
            </View>
            <Text style={styles.price} numberOfLines={1}>
              {currentPrice !== null ? formatDisplayCurrency(currentPrice) : 'N/A'}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );

  const titleContent = (
    <View style={styles.titleContainer}>
      <Text style={styles.title}>Market</Text>
    </View>
  );

  return (
    <Accordion title={titleContent} icon={<ChartBarIcon />}>
      <View style={styles.panelContent}>
        {isLoading ? renderLoading() : assets.length === 0 ? renderEmpty() : renderContent()}
      </View>
    </Accordion>
  );
}
