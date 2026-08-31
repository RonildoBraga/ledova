import React, { useMemo } from 'react';
import { ActivityIndicator, Text, View, ScrollView, RefreshControl } from 'react-native';
import { CurrencyBtcIcon, CurrencyEthIcon, WalletIcon } from 'phosphor-react-native';
import type { Wallet } from '@ledova/shared-types';
import { BLOCKCHAIN, getBlockchainDisplayName } from '@ledova/shared-constants';
import { formatCryptoBalance, calculateWalletTotals, filterWalletsByChain } from '@ledova/shared-utils';
import { useCurrency } from '../../hooks/useCurrency';
import { Panel } from '../panel';
import { Accordion } from '../accordion';
import { PrimaryButton } from '../buttons';
import { WalletItem } from '../../screens/wallets/components/WalletItem';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface WalletListProps {
  wallets: Wallet[];
  onWalletAction: (wallet: Wallet) => void;
  onSyncWallet?: (wallet: Wallet) => void;
  onDeleteWallet?: (wallet: Wallet) => void;
  syncingWalletId?: string;
  showBottomButton?: boolean;
  bottomButtonLabel?: string;
  onBottomButtonPress?: () => void;
  bottomButtonDisabled?: boolean;
  bottomButtonLoading?: boolean;
  isLoading?: boolean;
  chainFilter?: 'all' | 'btc' | 'eth';
  onRefresh?: () => void;
  refreshing?: boolean;
}

function ChainEmptyState({ chainName }: { chainName: string }) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    chainEmptyState: {
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.sm,
    },
    chainEmptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  return (
    <View style={styles.chainEmptyState}>
      <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight="light" />
      <Text style={styles.chainEmptyText}>No {chainName} wallets</Text>
    </View>
  );
}

export function WalletList({
  wallets,
  onWalletAction,
  onSyncWallet,
  onDeleteWallet,
  syncingWalletId,
  showBottomButton = false,
  bottomButtonLabel = 'Add Wallet',
  onBottomButtonPress,
  bottomButtonDisabled = false,
  bottomButtonLoading = false,
  isLoading = false,
  chainFilter = 'all',
  onRefresh,
  refreshing = false,
}: WalletListProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
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
      paddingBottom: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    headerValues: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    headerBalance: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    headerSeparator: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
    },
    headerMarketValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    walletItemsContainer: {
      gap: theme.spacing.sm,
    },
    loadingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    bottomButtonContainer: {
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.md,
    },
  }));
  const ethWallets = useMemo(() => filterWalletsByChain(wallets, BLOCKCHAIN.ETHEREUM), [wallets]);
  const btcWallets = useMemo(() => filterWalletsByChain(wallets, BLOCKCHAIN.BITCOIN), [wallets]);
  const totals = useMemo(() => calculateWalletTotals(wallets), [wallets]);

  const renderChainPanel = (
    networkWallets: Wallet[],
    networkName: string,
    networkSymbol: 'BTC' | 'ETH',
    total: number,
    marketValue: number,
  ) => {
    const Icon = networkSymbol === 'BTC' ? CurrencyBtcIcon : CurrencyEthIcon;
    const headerActions =
      networkWallets.length > 0 ? (
        <View style={styles.headerValues}>
          <Text style={styles.headerBalance}>{formatCryptoBalance(total, '').trimEnd()}</Text>
          <Text style={styles.headerSeparator}>·</Text>
          <Text style={styles.headerMarketValue}>{formatDisplayCurrency(marketValue)}</Text>
        </View>
      ) : undefined;

    return (
      <Accordion title={networkName} icon={<Icon />} actions={headerActions}>
        {networkWallets.length === 0 ? (
          <ChainEmptyState chainName={networkName} />
        ) : (
          <View style={styles.walletItemsContainer}>
            {networkWallets.map((wallet) => (
              <WalletItem
                key={wallet.uuid}
                wallet={wallet}
                onPress={() => onWalletAction(wallet)}
                onSync={onSyncWallet ? () => onSyncWallet(wallet) : undefined}
                onDelete={onDeleteWallet ? () => onDeleteWallet(wallet) : undefined}
                isSyncing={syncingWalletId === wallet.uuid}
              />
            ))}
          </View>
        )}
      </Accordion>
    );
  };

  if (isLoading && !wallets.length) {
    return (
      <Panel title="Wallets" icon={<WalletIcon />}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color={theme.colors.interactive.active} />
          <Text style={styles.loadingText}>Loading wallets...</Text>
        </View>
      </Panel>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          onRefresh ? (
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.interactive.active} />
          ) : undefined
        }
      >
        {chainFilter !== 'btc' &&
          renderChainPanel(ethWallets, getBlockchainDisplayName('ETH'), 'ETH', totals.eth, totals.ethTotalMarketValue)}
        {chainFilter !== 'eth' &&
          renderChainPanel(btcWallets, getBlockchainDisplayName('BTC'), 'BTC', totals.btc, totals.btcTotalMarketValue)}
      </ScrollView>
      {showBottomButton && onBottomButtonPress && (
        <View style={styles.bottomButtonContainer}>
          <PrimaryButton
            onPress={onBottomButtonPress}
            disabled={bottomButtonDisabled}
            loading={bottomButtonLoading}
            fullWidth
          >
            {bottomButtonLabel}
          </PrimaryButton>
        </View>
      )}
    </View>
  );
}
