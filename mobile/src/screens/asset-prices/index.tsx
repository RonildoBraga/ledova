import React, { useState, useCallback, useRef, useLayoutEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  ActivityIndicator,
  TouchableOpacity,
  NativeScrollEvent,
  NativeSyntheticEvent,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { FunnelIcon, ChartBarIcon, SortAscendingIcon } from 'phosphor-react-native';
import type { Asset } from '@ledova/shared';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { useAssetPrices } from './useAssetPrices';
import { useFavouriteAssets } from './useFavouriteAssets';
import { AssetListItem } from './components/AssetListItem';
import { AssetDetailModal } from './components/AssetDetailModal';
import { AssetFiltersModal } from './components/filters/AssetFiltersModal';
import { AssetSortModal, SortOption } from './components/AssetSortModal';

export function AssetPricesScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
    },
    panelContent: {
      flex: 1,
      flexDirection: 'column',
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
    headerButtons: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    headerButton: {
      width: 44,
      height: 44,
      alignItems: 'center',
      justifyContent: 'center',
    },
    assetsListContent: {
      flex: 1,
    },
    assetsList: {
      flex: 1,
    },
    loadingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptyState: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.md,
    },
    emptyText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    emptySubtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
      maxWidth: 250,
    },
    countInfo: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
      paddingBottom: theme.spacing.sm,
    },
    lastUpdatedText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    countText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    overscrollIndicator: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.md,
      opacity: 0.5,
    },
    loadMoreButton: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.md,
      marginTop: theme.spacing.sm,
      marginBottom: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      minHeight: 44,
    },
    loadMoreText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
    },
  }));
  const navigation = useNavigation();
  const {
    assets,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage,
    updateFilters,
    updateAndApplyFilters,
    clearFilters,
    loadMore,
    isLoading,
    isLoadingMore,
    refetch,
  } = useAssetPrices();

  const { isFavourite, toggleFavourite } = useFavouriteAssets();

  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [showFiltersDialog, setShowFiltersDialog] = useState(false);
  const [showSortDialog, setShowSortDialog] = useState(false);
  const [selectedSort, setSelectedSort] = useState<SortOption>('assetType');
  const [isOverscrollLoading, setIsOverscrollLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const innerScrollViewRef = useRef<ScrollView>(null);
  const loadingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleAssetPress = useCallback((asset: Asset) => {
    setSelectedAsset(asset);
    setModalVisible(true);
  }, []);

  const handleCloseModal = useCallback(() => {
    setModalVisible(false);
    setSelectedAsset(null);
  }, []);

  const handleOverscrollRefresh = () => {
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
    }

    setIsOverscrollLoading(true);
    refetch();

    loadingTimeoutRef.current = setTimeout(() => {
      setIsOverscrollLoading(false);
      setLastUpdated(new Date());
    }, 3000);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;

    // Check if user scrolled to the top (overscroll top)
    if (contentOffset.y < -50 && !isOverscrollLoading && !isLoading) {
      handleOverscrollRefresh();
    }

    // Check if user scrolled to the bottom (overscroll bottom)
    const isAtBottom = contentOffset.y + layoutMeasurement.height >= contentSize.height + 50;
    if (isAtBottom && !isOverscrollLoading && !isLoading) {
      handleOverscrollRefresh();
    }
  };

  // Sort assets based on selected sort option
  const sortedAssets = useCallback(() => {
    const assetsCopy = [...assets];

    switch (selectedSort) {
      case 'assetType':
        // Sort by asset type first, then alphabetically within each type
        return assetsCopy.sort((a, b) => {
          const typeComparison = (a.assetType || '').localeCompare(b.assetType || '');
          if (typeComparison !== 0) return typeComparison;
          return a.symbol.localeCompare(b.symbol);
        });

      case 'favourites':
        // Sort favourites first, then alphabetically within favourites and non-favourites
        return assetsCopy.sort((a, b) => {
          const aIsFav = isFavourite(a.uuid) ? 1 : 0;
          const bIsFav = isFavourite(b.uuid) ? 1 : 0;
          if (bIsFav !== aIsFav) return bIsFav - aIsFav;
          return a.symbol.localeCompare(b.symbol);
        });

      case 'alphabetical':
        return assetsCopy.sort((a, b) => a.symbol.localeCompare(b.symbol));

      default:
        return assetsCopy;
    }
  }, [assets, selectedSort, isFavourite]);

  const displayedAssets = sortedAssets();

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <ChartBarIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight={theme.icon.weights.light} />
      <Text style={styles.emptyText}>No assets found</Text>
      <Text style={styles.emptySubtext}>
        {hasActiveFilters ? 'Try adjusting your filters to see more results' : 'Assets will appear here once available'}
      </Text>
    </View>
  );

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={styles.headerButtons}>
          <TouchableOpacity
            onPress={() => setShowSortDialog(true)}
            style={styles.headerButton}
            hitSlop={{
              top: theme.spacing.sm,
              bottom: theme.spacing.sm,
              left: theme.spacing.sm,
              right: theme.spacing.sm,
            }}
          >
            <SortAscendingIcon
              size={theme.icon.sizes.lg}
              color={theme.colors.text.muted}
              weight={theme.icon.weights.regular}
            />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setShowFiltersDialog(true)}
            style={styles.headerButton}
            hitSlop={{
              top: theme.spacing.sm,
              bottom: theme.spacing.sm,
              left: theme.spacing.sm,
              right: theme.spacing.sm,
            }}
          >
            <FunnelIcon
              size={theme.icon.sizes.lg}
              color={hasActiveFilters ? theme.colors.interactive.active : theme.colors.text.muted}
              weight={hasActiveFilters ? theme.icon.weights.fill : theme.icon.weights.regular}
            />
          </TouchableOpacity>
        </View>
      ),
    });
  }, [navigation, hasActiveFilters, setShowSortDialog, setShowFiltersDialog]);

  const titleContent = (
    <View style={styles.titleContainer}>
      <Text style={styles.title}>Market Prices</Text>
    </View>
  );

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel title={titleContent} icon={<ChartBarIcon />} fullHeight={true}>
            <View style={styles.panelContent}>
              {isLoading ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                  <Text style={styles.loadingText}>Loading assets...</Text>
                </View>
              ) : displayedAssets.length === 0 ? (
                renderEmptyState()
              ) : (
                <View style={styles.assetsListContent}>
                  <ScrollView
                    ref={innerScrollViewRef}
                    style={styles.assetsList}
                    showsVerticalScrollIndicator={false}
                    bounces={true}
                    onScroll={handleScroll}
                    scrollEventThrottle={16}
                  >
                    {/* Top Overscroll Indicator */}
                    {(isLoading || isOverscrollLoading) && (
                      <View style={styles.overscrollIndicator}>
                        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                      </View>
                    )}

                    {displayedAssets.map((asset) => (
                      <AssetListItem
                        key={asset.uuid}
                        asset={asset}
                        onPress={handleAssetPress}
                        isFavourite={isFavourite(asset.uuid)}
                        onToggleFavourite={toggleFavourite}
                      />
                    ))}

                    {/* Load More Button */}
                    {hasNextPage && (
                      <TouchableOpacity
                        style={styles.loadMoreButton}
                        onPress={loadMore}
                        disabled={isLoadingMore}
                        activeOpacity={0.7}
                      >
                        {isLoadingMore ? (
                          <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                        ) : (
                          <Text style={styles.loadMoreText}>Load More</Text>
                        )}
                      </TouchableOpacity>
                    )}

                    {/* Bottom Overscroll Indicator */}
                    {(isLoading || isOverscrollLoading) && (
                      <View style={styles.overscrollIndicator}>
                        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                      </View>
                    )}
                  </ScrollView>
                  <View style={styles.countInfo}>
                    <Text style={styles.lastUpdatedText} key={`updated-${lastUpdated.getTime()}`}>
                      Last updated: {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </Text>
                    <Text style={styles.countText} key={`count-${assets.length}-${totalCount}`}>
                      {totalCount > 0
                        ? `${assets.length} of ${totalCount} asset${totalCount !== 1 ? 's' : ''}`
                        : `${assets.length} asset${assets.length !== 1 ? 's' : ''}`}
                    </Text>
                  </View>
                </View>
              )}
            </View>
          </Panel>
        </View>
      </View>

      {/* Asset Detail Modal */}
      <AssetDetailModal
        visible={modalVisible}
        asset={selectedAsset}
        onClose={handleCloseModal}
        isFavourite={selectedAsset ? isFavourite(selectedAsset.uuid) : false}
        onToggleFavourite={toggleFavourite}
      />

      {/* Sort Modal */}
      <AssetSortModal
        visible={showSortDialog}
        selectedSort={selectedSort}
        onClose={() => setShowSortDialog(false)}
        onSelectSort={setSelectedSort}
      />

      {/* Filters Modal */}
      <AssetFiltersModal
        isOpen={showFiltersDialog}
        filters={filters}
        onClose={() => setShowFiltersDialog(false)}
        onUpdateFilters={updateFilters}
        onApplyFilters={(filtersToApply) => {
          updateAndApplyFilters(filtersToApply);
          setShowFiltersDialog(false);
        }}
        onClearFilters={clearFilters}
      />
    </GradientBackground>
  );
}
