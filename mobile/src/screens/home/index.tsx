import { useState, useMemo, useCallback } from 'react';
import { View, ScrollView, RefreshControl, Text } from 'react-native';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { PerformanceCard } from './components/PerformanceCard';
import { AssetAllocationCard } from './components/AssetAllocationCard';
import { MarketCard } from './components/MarketCard';
import { WalletsCard } from './components/WalletsCard';
import { TransactionsCard } from './components/TransactionsCard';
import { AssetDetailModal } from '../asset-prices/components/AssetDetailModal';
import { useHome } from './useHome';
import { useAppTheme, useThemedStyles } from '../../contexts';

export function HomeScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    scrollView: {
      flex: 1,
    },
    scrollContent: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
      paddingBottom: theme.layout.screenBottomPadding,
      gap: theme.spacing.md,
    },
    panelContent: {
      height: 340,
    },
    lastUpdatedText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
  }));
  const [isAssetModalVisible, setIsAssetModalVisible] = useState(false);

  const {
    invalidateAll,
    performanceTimeRange,
    setPerformanceTimeRange,
    performanceChartData,
    timeRanges,
    isLoading,
    error,
    holdings,
    assetQuantities,
    selectedAsset,
    setSelectedAssetUuid,
    wallets,
    marketAssets,
    favouriteAssetUuids,
    isMarketAssetsLoading,
    transactions,
  } = useHome();

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await invalidateAll();
      setLastUpdated(new Date());
    } finally {
      setIsRefreshing(false);
    }
  }, [invalidateAll]);

  const assetColorMap = useMemo(
    () => Object.fromEntries(holdings.assetAllocation.map((item) => [item.symbol, item.color])),
    [holdings.assetAllocation],
  );

  const handleAssetClick = (assetUuid: string) => {
    setSelectedAssetUuid(assetUuid);
    setIsAssetModalVisible(true);
  };

  const handleCloseAssetModal = () => {
    setIsAssetModalVisible(false);
    setSelectedAssetUuid(null);
  };

  const selectedAssetSymbol = selectedAsset
    ? holdings.assetAllocation.find((a) => a.assetUuid === selectedAsset.uuid)?.symbol
    : undefined;

  return (
    <GradientBackground>
      <View style={styles.container}>
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor={theme.colors.interactive.active}
            />
          }
        >
          {lastUpdated && (
            <Text style={styles.lastUpdatedText}>
              Last updated: {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </Text>
          )}

          <Panel>
            <View style={styles.panelContent}>
              <PerformanceCard
                chartData={performanceChartData}
                totalValue={holdings.summary.totalValue}
                timeRanges={timeRanges}
                selectedTimeRange={performanceTimeRange}
                onTimeRangeChange={setPerformanceTimeRange}
                isLoading={isLoading}
                error={error}
                assetColorMap={assetColorMap}
              />
            </View>
          </Panel>

          <AssetAllocationCard
            assetAllocation={holdings.assetAllocation}
            totalValue={holdings.summary.totalValue}
            summary={holdings.summary}
            assetQuantities={assetQuantities}
            isLoading={holdings.isLoading}
            hasError={holdings.hasError}
            onAssetClick={handleAssetClick}
          />

          <WalletsCard
            btcWalletsCount={wallets.btcWalletsCount}
            ethWalletsCount={wallets.ethWalletsCount}
            totals={wallets.totals}
            isLoading={wallets.isLoading}
          />

          <MarketCard
            assets={marketAssets}
            favouriteAssetUuids={favouriteAssetUuids as Set<string>}
            isLoading={isMarketAssetsLoading}
            onAssetPress={(asset) => handleAssetClick(asset.uuid)}
          />

          <TransactionsCard
            transactions={transactions.list}
            totalCount={transactions.totalCount}
            isLoading={transactions.isLoading}
            isLoadingMore={transactions.isLoadingMore}
            hasNextPage={transactions.hasNextPage}
            onLoadMore={transactions.loadMore}
          />
        </ScrollView>
      </View>

      <AssetDetailModal
        visible={isAssetModalVisible}
        asset={selectedAsset}
        onClose={handleCloseAssetModal}
        portfolioMode={true}
        portfolioChartData={performanceChartData}
        assetSymbol={selectedAssetSymbol}
      />
    </GradientBackground>
  );
}
