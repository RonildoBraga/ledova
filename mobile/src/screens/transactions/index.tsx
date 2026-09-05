import React, { useState, useRef, useLayoutEffect, useMemo } from 'react';
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
import { FunnelIcon, SortAscendingIcon, CubeIcon } from 'phosphor-react-native';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { useTransactions } from './useTransactions';
import { TransactionListItem, TransactionDetailModal } from '../../components/blockchain/transactions';
import { TransactionFiltersModal } from './components/filters/TransactionFiltersModal';
import { TransactionSortModal } from './components/TransactionSortModal';
import type { TransactionSortOption } from './components/TransactionSortModal';
import type { Transaction } from '@ledova/shared';

function isIncomingTransaction(tx: Transaction): boolean {
  const walletAddr = tx.walletAddress?.toLowerCase() || '';
  return walletAddr !== tx.fromAddress?.toLowerCase();
}

export function TransactionsScreen() {
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
    transactionsListContent: {
      flex: 1,
    },
    transactionsList: {
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
  }));
  const navigation = useNavigation();
  const {
    transactions,
    ethWallets,
    btcWallets,
    isLoading,
    filters,
    hasActiveFilters,
    totalCount,
    loadMore,
    updateFilters,
    updateAndApplyFilters,
    clearFilters,
  } = useTransactions();

  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showFiltersDialog, setShowFiltersDialog] = useState(false);
  const [showSortDialog, setShowSortDialog] = useState(false);
  const [selectedSort, setSelectedSort] = useState<TransactionSortOption>('newest');
  const [isOverscrollLoading, setIsOverscrollLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const innerScrollViewRef = useRef<ScrollView>(null);
  const loadingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sortedTransactions = useMemo(() => {
    if (!transactions.length) return transactions;

    const sorted = [...transactions];
    switch (selectedSort) {
      case 'newest':
        return sorted.sort((a, b) => new Date(b.blockTimestamp).getTime() - new Date(a.blockTimestamp).getTime());
      case 'oldest':
        return sorted.sort((a, b) => new Date(a.blockTimestamp).getTime() - new Date(b.blockTimestamp).getTime());
      case 'highestValue':
        return sorted.sort((a, b) => parseFloat(b.amount || '0') - parseFloat(a.amount || '0'));
      case 'lowestValue':
        return sorted.sort((a, b) => parseFloat(a.amount || '0') - parseFloat(b.amount || '0'));
      case 'sent':
        return sorted.sort((a, b) => {
          const aIncoming = isIncomingTransaction(a);
          const bIncoming = isIncomingTransaction(b);
          if (!aIncoming && bIncoming) return -1;
          if (aIncoming && !bIncoming) return 1;
          return new Date(b.blockTimestamp).getTime() - new Date(a.blockTimestamp).getTime();
        });
      case 'received':
        return sorted.sort((a, b) => {
          const aIncoming = isIncomingTransaction(a);
          const bIncoming = isIncomingTransaction(b);
          if (aIncoming && !bIncoming) return -1;
          if (!aIncoming && bIncoming) return 1;
          return new Date(b.blockTimestamp).getTime() - new Date(a.blockTimestamp).getTime();
        });
      default:
        return sorted;
    }
  }, [transactions, selectedSort]);

  const handleTransactionClick = (transaction: Transaction) => {
    setSelectedTransaction(transaction);
    setShowDetailModal(true);
  };

  const handleCloseDetailModal = () => {
    setShowDetailModal(false);
    setSelectedTransaction(null);
  };

  const handleOverscrollRefresh = () => {
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
    }

    setIsOverscrollLoading(true);
    loadMore();

    loadingTimeoutRef.current = setTimeout(() => {
      setIsOverscrollLoading(false);
      setLastUpdated(new Date());
    }, 3000);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;

    if (contentOffset.y < -50 && !isOverscrollLoading && !isLoading) {
      handleOverscrollRefresh();
    }

    const isAtBottom = contentOffset.y + layoutMeasurement.height >= contentSize.height + 50;
    if (isAtBottom && !isOverscrollLoading && !isLoading) {
      handleOverscrollRefresh();
    }
  };

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <CubeIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight={theme.icon.weights.light} />
      <Text style={styles.emptyText}>No transactions found</Text>
      <Text style={styles.emptySubtext}>
        {hasActiveFilters
          ? 'Try adjusting your filters to see more results'
          : 'Transactions will appear here once confirmed on the blockchain'}
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
            <SortAscendingIcon size={theme.icon.sizes.lg} color={theme.colors.text.muted} weight="regular" />
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
  }, [navigation, hasActiveFilters, setShowFiltersDialog, setShowSortDialog]);

  const titleContent = (
    <View style={styles.titleContainer}>
      <Text style={styles.title}>Transaction History</Text>
    </View>
  );

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel title={titleContent} icon={<CubeIcon />} fullHeight={true}>
            <View style={styles.panelContent}>
              {isLoading ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                  <Text style={styles.loadingText}>Loading transactions...</Text>
                </View>
              ) : transactions.length === 0 ? (
                renderEmptyState()
              ) : (
                <View style={styles.transactionsListContent}>
                  <ScrollView
                    ref={innerScrollViewRef}
                    style={styles.transactionsList}
                    showsVerticalScrollIndicator={false}
                    bounces={true}
                    onScroll={handleScroll}
                    scrollEventThrottle={16}
                  >
                    {(isLoading || isOverscrollLoading) && (
                      <View style={styles.overscrollIndicator}>
                        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                      </View>
                    )}

                    {sortedTransactions.map((transaction, index) => (
                      <TransactionListItem key={index} transaction={transaction} onPress={handleTransactionClick} />
                    ))}

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
                    <Text style={styles.countText} key={`count-${transactions.length}-${totalCount}`}>
                      {totalCount > 0
                        ? `${transactions.length} of ${totalCount} transaction${totalCount !== 1 ? 's' : ''}`
                        : `${transactions.length} transaction${transactions.length !== 1 ? 's' : ''}`}
                    </Text>
                  </View>
                </View>
              )}
            </View>
          </Panel>
        </View>
      </View>

      {/* Detail Modal */}
      <TransactionDetailModal
        visible={showDetailModal}
        transaction={selectedTransaction}
        onClose={handleCloseDetailModal}
      />

      {/* Sort Modal */}
      <TransactionSortModal
        visible={showSortDialog}
        selectedSort={selectedSort}
        onClose={() => setShowSortDialog(false)}
        onSelectSort={setSelectedSort}
      />

      {/* Filters Modal */}
      <TransactionFiltersModal
        isOpen={showFiltersDialog}
        filters={filters}
        ethWallets={ethWallets}
        btcWallets={btcWallets}
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
