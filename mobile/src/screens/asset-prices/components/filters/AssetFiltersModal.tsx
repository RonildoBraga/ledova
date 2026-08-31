import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import {
  CurrencyBtcIcon,
  CurrencyEthIcon,
  CoinIcon,
  CurrencyDollarIcon,
  ChartLineIcon,
  CubeIcon,
  MagnifyingGlassIcon,
} from 'phosphor-react-native';
import { HOLDING_ASSET_TYPE, getHoldingAssetTypeLabel } from '@ledova/shared-constants';
import { useAppTheme, useThemedStyles } from '../../../../contexts';
import { CustomModal } from '../../../../components/modal';
import { CheckboxItem } from '../../../../components/checkbox';
import type { AssetFilters } from '../../useAssetPrices';

interface AssetFiltersModalProps {
  isOpen: boolean;
  filters: AssetFilters;
  onClose: () => void;
  onUpdateFilters: (filters: AssetFilters) => void;
  onApplyFilters: (filters: AssetFilters) => void;
  onClearFilters: () => void;
}

export function AssetFiltersModal({
  isOpen,
  filters,
  onClose,
  onUpdateFilters,
  onApplyFilters,
  onClearFilters,
}: AssetFiltersModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    clearButton: {
      marginTop: theme.spacing.xs,
    },
    clearButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
      textAlign: 'center',
    },
    filterSection: {
      gap: theme.spacing.sm,
      marginTop: theme.spacing.sm,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    },
    searchContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      paddingHorizontal: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    searchInput: {
      flex: 1,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    checkboxList: {
      gap: theme.spacing.sm,
    },
  }));
  const [localFilters, setLocalFilters] = useState<AssetFilters>(filters);
  const [selectedAssetTypes, setSelectedAssetTypes] = useState<Set<string>>(new Set());
  const [selectedChains, setSelectedChains] = useState<Set<string>>(new Set());
  const prevIsOpenRef = useRef(isOpen);

  useEffect(() => {
    if (isOpen && !prevIsOpenRef.current) {
      setLocalFilters(filters);

      const types = new Set<string>();
      if (filters.asset_type) {
        types.add(filters.asset_type);
      }
      setSelectedAssetTypes(types);

      const chains = new Set<string>();
      if (filters.chain) {
        chains.add(filters.chain);
      }
      setSelectedChains(chains);
    }
    prevIsOpenRef.current = isOpen;
  }, [isOpen, filters]);

  const hasActiveFilters = !!localFilters.search || selectedAssetTypes.size > 0 || selectedChains.size > 0;

  const toggleAssetType = (type: string) => {
    setSelectedAssetTypes((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(type)) {
        newSet.delete(type);
      } else {
        newSet.clear();
        newSet.add(type);
      }
      return newSet;
    });
  };

  const toggleChain = (chain: string) => {
    setSelectedChains((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(chain)) {
        newSet.delete(chain);
      } else {
        newSet.clear();
        newSet.add(chain);
      }
      return newSet;
    });
  };

  const handleApply = () => {
    const updatedFilters: AssetFilters = {
      ...localFilters,
      asset_type: selectedAssetTypes.size > 0 ? Array.from(selectedAssetTypes)[0] : undefined,
      chain: selectedChains.size > 0 ? Array.from(selectedChains)[0] : undefined,
    };
    onUpdateFilters(updatedFilters);
    onApplyFilters(updatedFilters);
  };

  const handleClear = () => {
    setLocalFilters({});
    setSelectedAssetTypes(new Set());
    setSelectedChains(new Set());
    onClearFilters();
  };

  const handleClose = () => {
    setLocalFilters(filters);

    const types = new Set<string>();
    if (filters.asset_type) {
      types.add(filters.asset_type);
    }
    setSelectedAssetTypes(types);

    const chains = new Set<string>();
    if (filters.chain) {
      chains.add(filters.chain);
    }
    setSelectedChains(chains);

    onClose();
  };

  const getAssetTypeIcon = (type: string) => {
    const iconProps = {
      size: theme.icon.sizes.sm,
      weight: theme.icon.weights.regular as 'regular',
      color: theme.colors.text.muted,
    };

    switch (type) {
      case HOLDING_ASSET_TYPE.NATIVE_CRYPTO:
        return <CoinIcon {...iconProps} />;
      case HOLDING_ASSET_TYPE.ERC20_TOKEN:
        return <CubeIcon {...iconProps} />;
      case HOLDING_ASSET_TYPE.STABLECOIN:
        return <CurrencyDollarIcon {...iconProps} />;
      case HOLDING_ASSET_TYPE.TOKENIZED_SECURITY:
        return <ChartLineIcon {...iconProps} />;
      default:
        return <CoinIcon {...iconProps} />;
    }
  };

  return (
    <CustomModal
      visible={isOpen}
      onClose={handleClose}
      showFooter={true}
      cancelLabel="Cancel"
      confirmLabel="Apply"
      onConfirm={handleApply}
    >
      <View style={styles.headerContainer}>
        <Text style={styles.title}>Filter Assets</Text>
        {hasActiveFilters && (
          <TouchableOpacity onPress={handleClear} style={styles.clearButton}>
            <Text style={styles.clearButtonText}>Clear Filters</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Search</Text>
        <View style={styles.searchContainer}>
          <MagnifyingGlassIcon
            size={theme.icon.sizes.sm}
            color={theme.colors.text.muted}
            weight={theme.icon.weights.regular}
          />
          <TextInput
            style={styles.searchInput}
            placeholder="Search by name or symbol..."
            placeholderTextColor={theme.colors.text.muted}
            value={localFilters.search || ''}
            onChangeText={(text) => setLocalFilters((prev) => ({ ...prev, search: text || undefined }))}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Asset Type</Text>
        <View style={styles.checkboxList}>
          <CheckboxItem
            label={getHoldingAssetTypeLabel(HOLDING_ASSET_TYPE.NATIVE_CRYPTO)}
            description="BTC, ETH"
            icon={getAssetTypeIcon(HOLDING_ASSET_TYPE.NATIVE_CRYPTO)}
            checked={selectedAssetTypes.has(HOLDING_ASSET_TYPE.NATIVE_CRYPTO)}
            onPress={() => toggleAssetType(HOLDING_ASSET_TYPE.NATIVE_CRYPTO)}
          />
          <CheckboxItem
            label={getHoldingAssetTypeLabel(HOLDING_ASSET_TYPE.ERC20_TOKEN)}
            description="USDC, USDT"
            icon={getAssetTypeIcon(HOLDING_ASSET_TYPE.ERC20_TOKEN)}
            checked={selectedAssetTypes.has(HOLDING_ASSET_TYPE.ERC20_TOKEN)}
            onPress={() => toggleAssetType(HOLDING_ASSET_TYPE.ERC20_TOKEN)}
          />
          <CheckboxItem
            label={getHoldingAssetTypeLabel(HOLDING_ASSET_TYPE.STABLECOIN)}
            description="USDC, USDT"
            icon={getAssetTypeIcon(HOLDING_ASSET_TYPE.STABLECOIN)}
            checked={selectedAssetTypes.has(HOLDING_ASSET_TYPE.STABLECOIN)}
            onPress={() => toggleAssetType(HOLDING_ASSET_TYPE.STABLECOIN)}
          />
          <CheckboxItem
            label={getHoldingAssetTypeLabel(HOLDING_ASSET_TYPE.TOKENIZED_SECURITY)}
            description="Tokenized stocks"
            icon={getAssetTypeIcon(HOLDING_ASSET_TYPE.TOKENIZED_SECURITY)}
            checked={selectedAssetTypes.has(HOLDING_ASSET_TYPE.TOKENIZED_SECURITY)}
            onPress={() => toggleAssetType(HOLDING_ASSET_TYPE.TOKENIZED_SECURITY)}
          />
        </View>
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Chain</Text>
        <View style={styles.checkboxList}>
          <CheckboxItem
            label="Bitcoin"
            description="BTC network"
            icon={
              <CurrencyBtcIcon
                size={theme.icon.sizes.sm}
                weight={theme.icon.weights.regular}
                color={theme.colors.text.muted}
              />
            }
            checked={selectedChains.has('BTC')}
            onPress={() => toggleChain('BTC')}
          />
          <CheckboxItem
            label="Ethereum"
            description="ETH network"
            icon={
              <CurrencyEthIcon
                size={theme.icon.sizes.sm}
                weight={theme.icon.weights.regular}
                color={theme.colors.text.muted}
              />
            }
            checked={selectedChains.has('ETH')}
            onPress={() => toggleChain('ETH')}
          />
        </View>
      </View>
    </CustomModal>
  );
}
