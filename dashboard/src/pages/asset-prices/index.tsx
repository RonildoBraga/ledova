import { useState, useCallback, useMemo, useEffect } from 'react';
import type { Asset } from '@ledova/shared';
import { DESIGN_TOKENS } from '@ledova/shared';
import { ChartBarIcon, FunnelIcon, ArrowsClockwiseIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { useHeaderActions } from '@hooks/useHeaderActions';
import { useBuyCrypto } from '@hooks/useBuyCrypto';
import { useFavouriteAssets } from '@hooks/useFavouriteAssets';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;
import { useAssetPrices } from './useAssetPrices';
import { AssetListItem } from './components/AssetListItem';
import { AssetDetailModal } from './components/AssetDetailModal';
import { AssetFilterModal } from './components/AssetFilterModal';

type SortOption = 'alphabetical' | 'assetType';

export function AssetPricesPage() {
  const {
    assets,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage,
    updateAndApplyFilters,
    clearFilters,
    loadMore,
    isLoading,
    isLoadingMore,
    refetch,
  } = useAssetPrices();

  const { openBuyCrypto } = useBuyCrypto();
  const { isFavourite, toggleFavourite } = useFavouriteAssets();

  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSort, setSelectedSort] = useState<SortOption>('assetType');
  const [selectedAssetType, setSelectedAssetType] = useState<string>('');
  const [showFiltersModal, setShowFiltersModal] = useState(false);
  const [lastUpdated] = useState<Date>(new Date());

  const assetTypes = useMemo(() => {
    const types = new Set<string>();
    assets.forEach((asset) => {
      if (asset.assetType) {
        types.add(asset.assetType);
      }
    });
    return Array.from(types).sort();
  }, [assets]);

  const displayedAssets = useMemo(() => {
    let filtered = [...assets];

    if (selectedAssetType) {
      filtered = filtered.filter((a) => a.assetType === selectedAssetType);
    }

    switch (selectedSort) {
      case 'alphabetical':
        return filtered.sort((a, b) => a.symbol.localeCompare(b.symbol));
      case 'assetType':
      default:
        return filtered.sort((a, b) => {
          const typeComparison = (a.assetType || '').localeCompare(b.assetType || '');
          if (typeComparison !== 0) return typeComparison;
          return a.symbol.localeCompare(b.symbol);
        });
    }
  }, [assets, selectedSort, selectedAssetType]);

  const handleAssetPress = useCallback((asset: Asset) => {
    setSelectedAsset(asset);
    setModalVisible(true);
  }, []);

  const handleCloseModal = useCallback(() => {
    setModalVisible(false);
    setSelectedAsset(null);
  }, []);

  const handleApplyFilters = useCallback(() => {
    updateAndApplyFilters({ ...filters, search: searchQuery || undefined });
    setShowFiltersModal(false);
  }, [searchQuery, filters, updateAndApplyFilters]);

  const handleClearAll = useCallback(() => {
    setSearchQuery('');
    setSelectedAssetType('');
    setSelectedSort('assetType');
    clearFilters();
    setShowFiltersModal(false);
  }, [clearFilters]);

  const handleBuy = useCallback(() => {
    if (!selectedAsset) return;
    setModalVisible(false);
    openBuyCrypto(selectedAsset.symbol);
  }, [selectedAsset, openBuyCrypto]);

  const hasLocalFilters = selectedAssetType !== '' || hasActiveFilters;

  const { setActions } = useHeaderActions();

  useEffect(() => {
    setActions(
      <button
        type="button"
        onClick={() => setShowFiltersModal(true)}
        className={`p-1.5 rounded transition-colors ${
          hasLocalFilters ? 'text-brand-mid' : 'text-text-muted hover:text-text-secondary'
        }`}
      >
        <FunnelIcon size={ICON_SM} weight={hasLocalFilters ? 'fill' : 'regular'} />
      </button>,
    );
    return () => setActions(null);
  }, [setActions, hasLocalFilters]);

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel
          title="Asset Prices"
          icon={<ChartBarIcon size={ICON_MD} />}
          actions={
            <button
              type="button"
              onClick={() => refetch()}
              className="p-1.5 text-text-muted hover:text-text-secondary transition-colors"
              title="Refresh"
            >
              <ArrowsClockwiseIcon size={ICON_SM} className={isLoading ? 'animate-spin' : ''} />
            </button>
          }
        >
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-mid"></div>
              <p className="text-sm text-text-muted">Loading assets...</p>
            </div>
          ) : displayedAssets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <ChartBarIcon size={ICON_XXL} className="text-text-subtle" />
              <p className="text-base font-medium text-text-muted">No assets found</p>
              <p className="text-xs text-text-subtle text-center max-w-[250px]">
                {hasLocalFilters
                  ? 'Try adjusting your filters to see more results'
                  : 'Assets will appear here once available'}
              </p>
            </div>
          ) : (
            <div className="space-y-0">
              <div className="divide-y divide-border-subtle max-h-[500px] overflow-y-auto">
                {displayedAssets.map((asset) => (
                  <AssetListItem key={asset.uuid} asset={asset} onPress={handleAssetPress} />
                ))}
              </div>

              {hasNextPage && (
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={isLoadingMore}
                  className="w-full mt-4 py-3 bg-surface-tertiary text-brand-mid text-sm font-medium rounded-lg hover:bg-surface-disabled transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? (
                    <div className="flex items-center justify-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-mid"></div>
                      <span>Loading...</span>
                    </div>
                  ) : (
                    'Load More'
                  )}
                </button>
              )}

              <div className="flex items-center justify-between pt-4 mt-4 border-t border-border-subtle text-xs text-text-subtle">
                <span>Last updated: {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                <span>
                  {totalCount > 0
                    ? `${displayedAssets.length} of ${totalCount} asset${totalCount !== 1 ? 's' : ''}`
                    : `${displayedAssets.length} asset${displayedAssets.length !== 1 ? 's' : ''}`}
                </span>
              </div>
            </div>
          )}
        </Panel>
      </div>

      <AssetFilterModal
        isOpen={showFiltersModal}
        searchQuery={searchQuery}
        selectedSort={selectedSort}
        selectedAssetType={selectedAssetType}
        assetTypes={assetTypes}
        onClose={() => setShowFiltersModal(false)}
        onSearchChange={setSearchQuery}
        onSortChange={setSelectedSort}
        onAssetTypeChange={setSelectedAssetType}
        onApply={handleApplyFilters}
        onClear={handleClearAll}
      />

      <AssetDetailModal
        isOpen={modalVisible}
        asset={selectedAsset}
        onClose={handleCloseModal}
        onBuy={handleBuy}
        isFavourite={selectedAsset ? isFavourite(selectedAsset.uuid) : false}
        onToggleFavourite={toggleFavourite}
      />
    </main>
  );
}

export default AssetPricesPage;
