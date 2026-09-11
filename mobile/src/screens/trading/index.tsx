import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { View, Text, ScrollView, RefreshControl, TouchableOpacity } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useQueryClient, type QueryCacheNotifyEvent } from '@tanstack/react-query';
import type { ShareToken, TransferOrder, CreateOrderRequest, SwapOrder, Wallet } from '@ledova/shared';
import { useOrderSubmissions, useOrderActions, useSwapSettlements, type SavedSwapSettlement } from '@ledova/shared';
import {
  selectMobileSettlement,
  settlementWalletMaterial,
  swapSettlementCrypto,
  swapSettlementStore,
} from '../../services/swapSettlements';
import { SwapSettlementModal } from './components/SwapSettlementModal';
import { orderSubmissionSession, orderSubmissionStore } from '../../services/orderSubmissions';
import { GradientBackground } from '../../components/GradientBackground';
import {
  useShareTokens,
  useInvestorEligibilityQuery,
  useUserTradingWallets,
  useWalletsWhitelistStatus,
  useAllWalletTokenBalances,
  useAllUserOrders,
  useOrderBook,
} from './useTrading';
import { useSwapOrdersMulti } from './useAtomicSwaps';
import { useTradingEvents } from './hooks/useTradingEvents';
import { MarketList } from './components/MarketList';
import { OrdersCard } from './components/OrdersCard';
import { BuySellButtons } from './components/BuySellButtons';
import { CreateOrderModal } from './components/CreateOrderModal';
import { OrderSigningModal } from './components/OrderSigningModal';
import { OrderActionModal } from './components/OrderActionModal';
import { orderActionStore } from '../../services/orderActions';
import { OrderDetailModal } from './components/OrderDetailModal';
import { SwapSigningModal } from './components/SwapSigningModal';
import { useAppTheme, useThemedStyles } from '../../contexts';

export function TradingScreen() {
  const submissions = useOrderSubmissions(orderSubmissionStore, orderSubmissionSession);
  const actions = useOrderActions(orderActionStore, orderSubmissionSession);
  const queryClient = useQueryClient();
  const walletObserver = useRef<((event: QueryCacheNotifyEvent) => void) | null>(null);
  useEffect(() => queryClient.getQueryCache().subscribe((event) => walletObserver.current?.(event)), [queryClient]);
  const settlements = useSwapSettlements(swapSettlementStore, swapSettlementCrypto, orderSubmissionSession);
  const settlementGeneration = useRef(0);
  const currentSettlementGeneration = settlementGeneration.current;
  const settlementScreen = useRef({ focused: true, close: () => {} });
  settlementScreen.current.close = settlements.close;
  useFocusEffect(
    useCallback(() => {
      settlementScreen.current.focused = true;
      return () => {
        settlementScreen.current.focused = false;
        settlementGeneration.current++;
        settlementScreen.current.close();
      };
    }, []),
  );
  const signingGeneration = useRef(0);
  const currentSigningGeneration = signingGeneration.current;
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: { flex: 1 },
    content: { flex: 1 },
    scrollContent: {
      paddingTop: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      paddingBottom: theme.spacing.xl,
      gap: theme.spacing.md,
    },
  }));

  const [refreshing, setRefreshing] = useState(false);
  const [selectedTokenUuid, setSelectedTokenUuid] = useState<string | null>(null);

  const { data: tokens, isLoading: isLoadingTokens, refetch: refetchTokens } = useShareTokens();
  const { data: eligibility } = useInvestorEligibilityQuery();
  const isEligible = eligibility?.isEligible ?? false;
  const { wallets, actionWallets, walletAddresses } = useUserTradingWallets();
  const currentWallets = useRef(wallets);
  currentWallets.current = wallets;
  settlements.active?.isCurrent();
  const whitelistStatus = useWalletsWhitelistStatus(walletAddresses);
  const tokenBalances = useAllWalletTokenBalances(walletAddresses);
  const userOrders = useAllUserOrders(walletAddresses);
  const swapOrders = useSwapOrdersMulti(walletAddresses);

  const effectiveTokenUuid = selectedTokenUuid ?? (tokens && tokens.length > 0 ? tokens[0].uuid : null);

  useTradingEvents(effectiveTokenUuid);

  const selectedToken = useMemo(() => {
    if (!tokens || !effectiveTokenUuid) return null;
    return tokens.find((t: ShareToken) => t.uuid === effectiveTokenUuid) || null;
  }, [tokens, effectiveTokenUuid]);

  const { data: orderBookData, isLoading: isLoadingOrderBook } = useOrderBook(effectiveTokenUuid || undefined);

  const [createOrderType, setCreateOrderType] = useState<'buy' | 'sell'>('buy');
  const [showCreateOrder, setShowCreateOrder] = useState(false);

  const [detailOrder, setDetailOrder] = useState<TransferOrder | null>(null);
  const [showDetailOrder, setShowDetailOrder] = useState(false);

  const [signSwap, setSignSwap] = useState<SwapOrder | null>(null);
  const [signSwapWallet, setSignSwapWallet] = useState<Wallet | null>(null);
  const [showSwapSigning, setShowSwapSigning] = useState(false);
  const [settlementError, setSettlementError] = useState<string | null>(null);
  const closeSettlement = () => {
    settlementGeneration.current++;
    settlements.close();
    walletObserver.current = null;
    setShowSwapSigning(false);
  };
  const walletBoundary = (wallet: Wallet) => {
    const material = settlementWalletMaterial(wallet);
    let retired = false;
    walletObserver.current = (event) => {
      const key = event.query.queryKey;
      if (key[0] !== 'wallets' || key[1] !== wallet.userAccount || key[2] !== 'trading') return;
      const data = event.query.state.data as { data: { results: Wallet[] } } | undefined;
      const current =
        event.type === 'removed' ? undefined : data?.data?.results?.find((item) => item.uuid === wallet.uuid);
      if (material !== settlementWalletMaterial(current)) retired = true;
    };
    return () =>
      !retired &&
      settlementScreen.current.focused &&
      material === settlementWalletMaterial(currentWallets.current.find((item) => item.uuid === wallet.uuid));
  };
  const recoverSettlement = (record: SavedSwapSettlement) => {
    closeSettlement();
    const wallet = wallets.find(
      (item) => item.uuid === record.walletUuid && item.userAccount === record.ownerAccountUuid,
    );
    if (!wallet) {
      setSettlementError('The original wallet is unavailable in this account. The saved settlement remains.');
      return;
    }
    setSettlementError(null);
    submissions.close();
    actions.close();
    settlements.recover(record, walletBoundary(wallet));
  };

  const findWalletForAddress = useCallback(
    (address: string): Wallet | null =>
      wallets.find((w: Wallet) => w.address.toLowerCase() === address.toLowerCase()) || null,
    [wallets],
  );

  const handleBuy = () => {
    closeSettlement();
    signingGeneration.current++;
    submissions.close();
    actions.close();
    setCreateOrderType('buy');
    setShowCreateOrder(true);
  };

  const handleSell = () => {
    closeSettlement();
    signingGeneration.current++;
    submissions.close();
    actions.close();
    setCreateOrderType('sell');
    setShowCreateOrder(true);
  };

  const handleCreateOrderSubmit = async (data: CreateOrderRequest): Promise<boolean> => {
    const generation = signingGeneration.current;
    const accepted = await submissions.begin(data, wallets.find((wallet) => wallet.uuid === data.walletUuid) ?? null);
    if (accepted && generation === signingGeneration.current) setShowCreateOrder(false);
    return accepted;
  };

  const handleCancelOrder = (orderUuid: string) => {
    closeSettlement();
    signingGeneration.current++;
    submissions.close();
    setShowCreateOrder(false);
    setShowDetailOrder(false);
    actions.open(orderUuid, 'cancel');
  };

  const handleEditOrder = (order: TransferOrder) => {
    closeSettlement();
    signingGeneration.current++;
    submissions.close();
    setShowCreateOrder(false);
    setShowDetailOrder(false);
    actions.open(order.uuid, 'modify');
  };

  const handleViewOrder = (order: TransferOrder) => {
    closeSettlement();
    setDetailOrder(order);
    setShowDetailOrder(true);
  };

  const handleSignSwap = (swap: SwapOrder) => {
    closeSettlement();
    setSettlementError(null);
    submissions.close();
    actions.close();
    setShowCreateOrder(false);
    if (swap.settlementProtocolVersion === 0) {
      const isSeller =
        !swap.sellerHasSigned &&
        walletAddresses.some((address) => address.toLowerCase() === swap.sellerAddress.toLowerCase());
      setSignSwap(swap);
      setSignSwapWallet(findWalletForAddress(isSeller ? swap.sellerAddress : swap.buyerAddress));
      setShowSwapSigning(true);
      return;
    }
    try {
      if (!settlements.owner) throw new Error('No current account.');
      const { selection, wallet } = selectMobileSettlement(swap, settlements.owner, wallets);
      settlements.open(selection, walletBoundary(wallet));
    } catch {
      setSettlementError(
        'This settlement cannot be opened with the current account and wallet. Refresh its captured details.',
      );
    }
  };

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([refetchTokens(), userOrders.refetch(), tokenBalances.refetch(), swapOrders.refetch()]);
    setRefreshing(false);
  }, [refetchTokens, userOrders, tokenBalances, swapOrders]);

  const handleSigningSuccess = () => {
    if (signingGeneration.current !== currentSigningGeneration) return;
    userOrders.refetch();
    tokenBalances.refetch();
  };

  const handleSwapSuccess = useCallback(() => {
    swapOrders.refetch();
    userOrders.refetch();
  }, [swapOrders, userOrders]);

  const walletsWithHoldings = useMemo(() => {
    if (!selectedToken) return [];
    return tokenBalances.getWalletsWithHoldings(selectedToken.uuid);
  }, [selectedToken, tokenBalances]);

  const handleSelectToken = useCallback((uuid: string) => {
    setSelectedTokenUuid(uuid);
  }, []);

  return (
    <GradientBackground>
      <View style={styles.container}>
        <ScrollView
          style={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              tintColor={theme.colors.interactive.default}
            />
          }
        >
          <View style={styles.scrollContent}>
            <MarketList
              tokens={tokens || []}
              selectedTokenUuid={effectiveTokenUuid}
              onSelectToken={handleSelectToken}
              isLoading={isLoadingTokens}
              isEligible={isEligible}
            />

            <View style={{ gap: theme.spacing.sm }} accessibilityLabel="Saved orders">
              <Text style={{ color: theme.colors.text.primary, fontWeight: theme.fontWeight.semibold }}>
                Saved orders
              </Text>
              <Text style={{ color: theme.colors.text.secondary }}>
                Check unfinished orders here. New buy and sell orders are separate orders, even with the same terms.
              </Text>
              {submissions.error && (
                <Text accessibilityRole="alert" style={{ color: theme.colors.status.error.icon }}>
                  {submissions.error}
                </Text>
              )}
              {submissions.pending.map((record, index) => (
                <TouchableOpacity
                  key={record.submissionId}
                  accessibilityRole="button"
                  onPress={() => {
                    signingGeneration.current++;
                    closeSettlement();
                    actions.close();
                    submissions.recover(record);
                  }}
                >
                  <Text style={{ color: theme.colors.interactive.default }}>Check saved order {index + 1}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity
                accessibilityRole="button"
                onPress={() => void submissions.refresh()}
                disabled={submissions.isLoading}
              >
                <Text style={{ color: theme.colors.interactive.default }}>Refresh saved orders</Text>
              </TouchableOpacity>
            </View>

            <View style={{ gap: theme.spacing.sm }} accessibilityLabel="Saved cancellations and changes">
              <Text style={{ color: theme.colors.text.primary, fontWeight: theme.fontWeight.semibold }}>
                Saved cancellations and changes
              </Text>
              {actions.error && (
                <Text accessibilityRole="alert" style={{ color: theme.colors.status.error.icon }}>
                  {actions.error}
                </Text>
              )}
              {actions.pending.map((record, index) => (
                <TouchableOpacity
                  key={record.actionId}
                  accessibilityRole="button"
                  onPress={() => {
                    signingGeneration.current++;
                    closeSettlement();
                    submissions.close();
                    setShowCreateOrder(false);
                    actions.recover(record);
                  }}
                >
                  <Text style={{ color: theme.colors.interactive.default }}>
                    Check {record.purpose === 'cancel' ? 'cancellation' : 'change'} {index + 1}
                  </Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity
                accessibilityRole="button"
                disabled={actions.isLoading}
                onPress={() => void actions.refresh()}
              >
                <Text style={{ color: theme.colors.interactive.default }}>Refresh saved actions</Text>
              </TouchableOpacity>
            </View>

            <View style={{ gap: theme.spacing.sm }} accessibilityLabel="Saved settlements">
              <Text style={{ color: theme.colors.text.primary, fontWeight: theme.fontWeight.semibold }}>
                Saved settlements
              </Text>
              <Text style={{ color: theme.colors.text.secondary }}>
                Check signatures and original approval transactions whose outcome is still unconfirmed.
              </Text>
              {(settlementError || settlements.error) && (
                <Text accessibilityRole="alert" style={{ color: theme.colors.status.error.icon }}>
                  {settlementError || settlements.error}
                </Text>
              )}
              {settlements.pending.map((record, index) => (
                <View
                  key={`${record.swapUuid}/${record.walletUuid}/${record.kind}/${record.kind === 'approval' ? record.txHash : record.signerAddress}`}
                >
                  <TouchableOpacity accessibilityRole="button" onPress={() => recoverSettlement(record)}>
                    <Text style={{ color: theme.colors.interactive.default }}>Check saved settlement {index + 1}</Text>
                  </TouchableOpacity>
                  {record.kind === 'approval' && (
                    <Text selectable style={{ color: theme.colors.text.secondary }}>
                      Unconfirmed approval: {record.txHash}
                    </Text>
                  )}
                </View>
              ))}
              <TouchableOpacity
                accessibilityRole="button"
                disabled={settlements.isLoading}
                onPress={() => void settlements.refresh()}
              >
                <Text style={{ color: theme.colors.interactive.default }}>Refresh saved settlements</Text>
              </TouchableOpacity>
            </View>

            {selectedToken && (
              <>
                <OrdersCard
                  tokenSymbol={selectedToken.symbol}
                  orderBook={orderBookData || null}
                  isLoadingOrderBook={isLoadingOrderBook}
                  userOrders={userOrders.orders}
                  isLoadingUserOrders={userOrders.isLoading}
                  onCancelOrder={handleCancelOrder}
                  onEditOrder={handleEditOrder}
                  onViewOrder={handleViewOrder}
                  swaps={swapOrders.data}
                  isLoadingSwaps={swapOrders.isLoading}
                  walletAddresses={walletAddresses}
                  onSignSwap={handleSignSwap}
                />

                <BuySellButtons
                  tokenSymbol={selectedToken.symbol}
                  onBuy={handleBuy}
                  onSell={handleSell}
                  disabled={wallets.length === 0}
                />
              </>
            )}
          </View>
        </ScrollView>
      </View>

      {selectedToken && (
        <CreateOrderModal
          visible={showCreateOrder}
          onClose={() => {
            signingGeneration.current++;
            submissions.close();
            setShowCreateOrder(false);
          }}
          token={selectedToken}
          orderType={createOrderType}
          wallets={wallets}
          walletsWithHoldings={walletsWithHoldings}
          onSubmit={handleCreateOrderSubmit}
          submissionError={submissions.error}
          isWalletWhitelisted={whitelistStatus.isWhitelisted}
          getWhitelistStatus={whitelistStatus.getStatus}
          isLoadingWhitelistStatus={whitelistStatus.isLoading}
        />
      )}

      <OrderSigningModal
        visible={!!submissions.active}
        onClose={() => {
          signingGeneration.current++;
          submissions.close();
        }}
        submission={submissions.active}
        tokens={tokens ?? []}
        wallet={wallets.find((wallet) => wallet.uuid === submissions.active?.record.walletUuid) ?? null}
        onSuccess={handleSigningSuccess}
      />

      {actions.active && (
        <OrderActionModal
          key={actions.active.record?.actionId ?? `${actions.active.orderUuid}/${actions.active.purpose}`}
          action={actions.active}
          wallets={actionWallets}
          onClose={actions.close}
        />
      )}

      <OrderDetailModal
        visible={showDetailOrder}
        onClose={() => setShowDetailOrder(false)}
        order={detailOrder}
        onModify={handleEditOrder}
        onCancel={handleCancelOrder}
      />

      {showSwapSigning && signSwap?.settlementProtocolVersion === 0 && (
        <SwapSigningModal
          key={`${signSwap.uuid}/${signSwapWallet?.uuid}`}
          visible={true}
          onClose={closeSettlement}
          swap={signSwap}
          wallet={signSwapWallet}
          onSuccess={handleSwapSuccess}
        />
      )}
      {settlements.active && (
        <SwapSettlementModal
          key={`${settlements.active.selection.swapUuid}/${currentSettlementGeneration}`}
          settlement={settlements.active}
          wallet={wallets.find((item) => item.uuid === settlements.active?.selection.walletUuid) ?? null}
          onClose={() => {
            if (settlementGeneration.current === currentSettlementGeneration) closeSettlement();
          }}
        />
      )}
    </GradientBackground>
  );
}
