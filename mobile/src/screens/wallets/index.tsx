import React, { useCallback, useLayoutEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { PlusIcon, FunnelIcon } from 'phosphor-react-native';
import type { Wallet } from '@ledova/shared-types';
import type { WalletsStackParamList } from '../../navigation/WalletsStackNavigator';
import { GradientBackground } from '../../components/GradientBackground';
import { WalletList, WalletSortModal, useWalletSort } from '../../components/wallet-list';
import { AddWalletModal } from './components/AddWalletModal';
import { DeleteWalletModal } from './components/DeleteWalletModal';
import { useWallets } from './useWallets';
import { useWalletsCrud } from './useWalletsCrud';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { formatWalletAddressShort } from '@ledova/shared-utils';

export function WalletsScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
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
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.md,
      flex: 1,
    },
    emptyTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    emptySubtitle: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
    addWalletButton: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.interactive.active,
      paddingHorizontal: theme.spacing.lg,
      paddingVertical: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      gap: theme.spacing.sm,
    },
    addWalletButtonText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.utility.white,
    },
    fab: {
      position: 'absolute',
      bottom: theme.spacing.md,
      right: theme.spacing.md,
      width: 56,
      height: 56,
      borderRadius: 28,
      backgroundColor: theme.colors.interactive.active,
      alignItems: 'center',
      justifyContent: 'center',
      elevation: 4,
      shadowColor: theme.colors.utility.black,
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.25,
      shadowRadius: 4,
    },
  }));
  const navigation = useNavigation<NativeStackNavigationProp<WalletsStackParamList>>();

  const {
    wallets,
    isLoading: isLoadingWallets,
    syncWallet: syncWalletById,
    syncingWalletId,
    deleteWallet,
  } = useWalletsCrud();
  const hasNoWallets = wallets.length === 0;
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);
  const [deletingWallet, setDeletingWallet] = useState<Wallet | null>(null);

  const {
    showAddModal,
    preselectedChain,
    isCreating,
    userAccountUuid,
    handleCreateWallet,
    handleBatchCreateWallets,
    handleSoftwareWalletCreate,
    openAddModal,
    closeAddModal,
  } = useWallets();

  const handleManualRefresh = useCallback(async () => {
    setIsManualRefreshing(true);
    try {
      await Promise.all(wallets.map((w: Wallet) => syncWalletById(w.uuid)));
    } finally {
      setIsManualRefreshing(false);
    }
  }, [wallets, syncWalletById]);

  const { sortedWallets, chainFilter, sortOption, isFiltered, showSortModal, setShowSortModal, handleApply } =
    useWalletSort(wallets, 'default');

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={styles.headerButtons}>
          <TouchableOpacity
            onPress={() => setShowSortModal(true)}
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
              color={isFiltered ? theme.colors.interactive.active : theme.colors.text.muted}
              weight={isFiltered ? 'fill' : 'regular'}
            />
          </TouchableOpacity>
        </View>
      ),
    });
  }, [navigation, isFiltered, setShowSortModal]);

  const handleAddWallet = () => {
    openAddModal(null);
  };

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <Text style={styles.emptyTitle}>No wallets found</Text>
      <Text style={styles.emptySubtitle}>Add a wallet first to buy crypto</Text>
      <TouchableOpacity style={styles.addWalletButton} onPress={handleAddWallet} activeOpacity={0.7}>
        <PlusIcon size={theme.icon.sizes.sm} color={theme.colors.utility.white} weight="bold" />
        <Text style={styles.addWalletButtonText}>Add Wallet</Text>
      </TouchableOpacity>
    </View>
  );

  const renderLoading = () => (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="large" color={theme.colors.interactive.active} />
      <Text style={styles.loadingText}>Loading...</Text>
    </View>
  );

  return (
    <GradientBackground>
      <View style={styles.container}>
        {isLoadingWallets ? (
          renderLoading()
        ) : hasNoWallets ? (
          renderEmptyState()
        ) : (
          <WalletList
            wallets={sortedWallets}
            onWalletAction={(wallet) => navigation.navigate('WalletAction', { wallet })}
            onSyncWallet={(wallet) => syncWalletById(wallet.uuid)}
            onDeleteWallet={(wallet) => setDeletingWallet(wallet)}
            syncingWalletId={syncingWalletId}
            chainFilter={chainFilter}
            isLoading={isLoadingWallets}
            onRefresh={handleManualRefresh}
            refreshing={isManualRefreshing}
          />
        )}
      </View>

      {!hasNoWallets && !isLoadingWallets && (
        <TouchableOpacity style={styles.fab} onPress={handleAddWallet} activeOpacity={0.8}>
          <PlusIcon size={theme.icon.sizes.md} color={theme.colors.utility.white} weight="bold" />
        </TouchableOpacity>
      )}

      <WalletSortModal
        visible={showSortModal}
        selectedChain={chainFilter}
        selectedSort={sortOption}
        onClose={() => setShowSortModal(false)}
        onApply={handleApply}
      />

      <AddWalletModal
        visible={showAddModal}
        isLoading={isCreating}
        userAccountUuid={userAccountUuid}
        preselectedChain={preselectedChain}
        onClose={closeAddModal}
        onSubmit={handleCreateWallet}
        onBatchSubmit={handleBatchCreateWallets}
        onSoftwareWalletCreate={handleSoftwareWalletCreate}
      />

      <DeleteWalletModal
        visible={!!deletingWallet}
        walletName={deletingWallet?.name || (deletingWallet ? formatWalletAddressShort(deletingWallet.address) : '')}
        onConfirm={() => {
          if (deletingWallet) {
            deleteWallet(deletingWallet.uuid, {
              onSuccess: () => setDeletingWallet(null),
            });
          }
        }}
        onClose={() => setDeletingWallet(null)}
      />
    </GradientBackground>
  );
}
