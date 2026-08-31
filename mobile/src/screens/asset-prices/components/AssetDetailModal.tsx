import React, { useState, useCallback, useMemo } from 'react';
import { View, Text } from 'react-native';
import { StarIcon } from 'phosphor-react-native';
import { TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { Asset, PortfolioSnapshotDataPoint } from '@ledova/shared-types';
import type { BottomTabParamList } from '../../../navigation/BottomTabNavigator';
import { useCurrency } from '../../../hooks/useCurrency';
import { BUYABLE_ASSETS } from '@ledova/shared-constants';
import { AssetTypeIcon } from '../../../components/AssetTypeIcon';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { AssetPriceChart } from './AssetPriceChart';
import { useAssetPriceHistory } from '../useAssetPrices';

interface AssetDetailModalProps {
  visible: boolean;
  asset: Asset | null;
  onClose: () => void;
  portfolioMode?: boolean;
  portfolioChartData?: PortfolioSnapshotDataPoint[] | null;
  assetSymbol?: string;
  isFavourite?: boolean;
  onToggleFavourite?: (assetUuid: string) => void;
}

export function AssetDetailModal({
  visible,
  asset,
  onClose,
  portfolioMode = false,
  portfolioChartData,
  assetSymbol,
  isFavourite = false,
  onToggleFavourite,
}: AssetDetailModalProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: theme.spacing.md,
    },
    headerIcon: {
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    assetName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    favouriteButton: {
      position: 'absolute',
      right: 0,
      padding: theme.spacing.xs,
    },
    priceSection: {
      alignItems: 'center',
      marginBottom: theme.spacing.lg,
    },
    currentPrice: {
      fontSize: theme.fontSize.xxl,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    changeText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      marginTop: theme.spacing.xs,
    },
    dateLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    chartSection: {
      minHeight: 280,
      marginHorizontal: -theme.spacing.md,
    },
  }));
  const navigation = useNavigation<NativeStackNavigationProp<BottomTabParamList>>();

  const [activePointIndex, setActivePointIndex] = useState<number | null>(null);

  const handleActivePointChange = useCallback((index: number) => {
    setActivePointIndex(index);
  }, []);

  const {
    chartData: assetChartData,
    periodChangePercent: assetChangePercent,
    selectedTimeRange,
    setSelectedTimeRange,
    isLoading: assetLoading,
    error: assetError,
  } = useAssetPriceHistory(portfolioMode ? null : asset?.uuid || null);

  const portfolioAssetChartData = useMemo(() => {
    if (!portfolioMode || !portfolioChartData || !assetSymbol) return null;

    return portfolioChartData.map((point, index, array) => {
      const currentPrice = point.assetValues[assetSymbol] || 0;
      const previousPrice = index > 0 ? array[index - 1].assetValues[assetSymbol] || 0 : currentPrice;
      const changePercent = previousPrice !== 0 ? ((currentPrice - previousPrice) / previousPrice) * 100 : 0;

      return {
        date: point.date,
        price: currentPrice,
        dayIndex: point.dayIndex,
        changePercent,
      };
    });
  }, [portfolioMode, portfolioChartData, assetSymbol]);

  const portfolioChangePercent = useMemo(() => {
    if (!portfolioAssetChartData || portfolioAssetChartData.length < 2) return null;

    const firstValue = portfolioAssetChartData[0].price;
    const lastValue = portfolioAssetChartData[portfolioAssetChartData.length - 1].price;

    if (firstValue === 0) return null;

    return ((lastValue - firstValue) / firstValue) * 100;
  }, [portfolioAssetChartData]);

  if (!asset) return null;

  const chartData = portfolioMode ? portfolioAssetChartData : assetChartData;
  const periodChangePercent = portfolioMode ? portfolioChangePercent : assetChangePercent;
  const isLoading = portfolioMode ? false : assetLoading;
  const error = portfolioMode ? null : assetError;

  const activePoint = activePointIndex != null ? chartData?.[activePointIndex] : null;
  const isScrubbing = activePoint != null;

  const currentPrice = isScrubbing
    ? activePoint.price
    : portfolioMode && portfolioAssetChartData && portfolioAssetChartData.length > 0
      ? portfolioAssetChartData[portfolioAssetChartData.length - 1].price
      : asset.currentPrice
        ? parseFloat(asset.currentPrice)
        : null;

  const displayChangePercent = isScrubbing ? activePoint.changePercent : periodChangePercent;
  const isPositiveChange = displayChangePercent !== null ? displayChangePercent >= 0 : true;

  const scrubbedDateLabel = isScrubbing
    ? (() => {
        try {
          const date = new Date(activePoint.date);
          if (isNaN(date.getTime())) return '';
          return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
          return '';
        }
      })()
    : null;

  const handleBuy = () => {
    const buyableAsset = BUYABLE_ASSETS.find((a) => a.symbol === asset.symbol);
    if (!buyableAsset) return;
    onClose();
    navigation.navigate('Buy', { screen: 'BuySelect', params: { asset: buyableAsset.symbol } });
  };

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      showCancelButton={true}
      cancelLabel="Close"
      confirmLabel="Buy"
      onCancel={onClose}
      onConfirm={handleBuy}
    >
      <View style={styles.header}>
        <View style={styles.headerIcon}>
          <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} size={32} />
          <Text style={styles.assetName}>{asset.name}</Text>
        </View>
        {onToggleFavourite && (
          <TouchableOpacity
            onPress={() => onToggleFavourite(asset.uuid)}
            style={styles.favouriteButton}
            hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}
          >
            <StarIcon
              size={theme.icon.sizes.md}
              color={isFavourite ? theme.colors.status.warning.icon : theme.colors.text.subtle}
              weight={isFavourite ? 'fill' : 'regular'}
            />
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.priceSection}>
        <Text style={styles.currentPrice}>{currentPrice !== null ? formatDisplayCurrency(currentPrice) : 'N/A'}</Text>
        {displayChangePercent !== null && (
          <Text
            style={[
              styles.changeText,
              { color: isPositiveChange ? theme.colors.status.success.text : theme.colors.status.error.text },
            ]}
          >
            {isPositiveChange ? '+' : ''}
            {displayChangePercent.toFixed(2)}%
          </Text>
        )}
        {scrubbedDateLabel ? <Text style={styles.dateLabel}>{scrubbedDateLabel}</Text> : null}
      </View>

      <View style={styles.chartSection}>
        <AssetPriceChart
          chartData={chartData || []}
          isLoading={isLoading}
          error={error}
          selectedTimeRange={selectedTimeRange}
          onTimeRangeChange={setSelectedTimeRange}
          onActivePointChange={handleActivePointChange}
        />
      </View>
    </CustomModal>
  );
}
