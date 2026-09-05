import { useState } from 'react';
import type { Asset } from '@ledova/shared';
import { PerformanceSection } from './components/PerformanceSection';
import { AssetAllocationCard } from './components/AssetAllocationCard';
import { WalletAllocationCard } from './components/WalletAllocationCard';
import { MarketCard } from './components/MarketCard';
import { TransactionsCard } from './components/TransactionsCard';
import { AssetDetailModal } from '../asset-prices/components/AssetDetailModal';
import { useHome } from './useHome';

export function HomePage() {
  const {
    performanceTimeRange,
    setPerformanceTimeRange,
    performanceChartData,
    timeRanges,
    isLoading,
    isError,
    holdings,
    wallets,
    transactions,
    selectedAsset,
    setSelectedAssetUuid,
    marketAssets,
    favouriteAssetUuids,
    isMarketAssetsLoading,
  } = useHome();

  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);

  const handleAssetClick = (assetUuid: string) => {
    setSelectedAssetUuid(assetUuid);
    setIsAssetModalOpen(true);
  };

  const handleMarketAssetPress = (asset: Asset) => {
    setSelectedAssetUuid(asset.uuid);
    setIsAssetModalOpen(true);
  };

  const handleCloseAssetModal = () => {
    setIsAssetModalOpen(false);
    setSelectedAssetUuid(null);
  };

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">
          <PerformanceSection
            snapshotData={performanceChartData}
            timeRanges={timeRanges}
            selectedTimeRange={performanceTimeRange}
            onTimeRangeChange={setPerformanceTimeRange}
            isLoading={isLoading}
            error={isError}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5 md:gap-6">
            <AssetAllocationCard
              assetAllocation={holdings.assetAllocation}
              totalValue={holdings.summary.totalValue}
              summary={holdings.summary}
              assetQuantities={holdings.assetQuantities}
              isLoading={holdings.isLoading}
              hasError={holdings.hasError}
              onAssetClick={handleAssetClick}
            />
            <WalletAllocationCard
              totals={wallets.totals}
              ethWalletsCount={wallets.ethWalletsCount}
              btcWalletsCount={wallets.btcWalletsCount}
              baseWalletsCount={wallets.baseWalletsCount}
              isLoading={wallets.isLoading}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5 md:gap-6">
            <MarketCard
              assets={marketAssets}
              favouriteAssetUuids={favouriteAssetUuids}
              isLoading={isMarketAssetsLoading}
              onAssetPress={handleMarketAssetPress}
            />
            <TransactionsCard
              transactions={transactions.list}
              totalCount={transactions.totalCount}
              isLoading={transactions.isLoading}
              isLoadingMore={transactions.isLoadingMore}
              hasNextPage={transactions.hasNextPage}
              onLoadMore={transactions.loadMore}
            />
          </div>
        </div>
      </div>

      <AssetDetailModal isOpen={isAssetModalOpen} asset={selectedAsset} onClose={handleCloseAssetModal} />
    </main>
  );
}

export default HomePage;
