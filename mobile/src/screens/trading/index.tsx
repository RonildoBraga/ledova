import React, { useState, useCallback, useMemo, useRef } from 'react';
import { View, Text, ScrollView, RefreshControl, TouchableOpacity } from 'react-native';
import type { ShareToken, TransferOrder, CreateOrderRequest, SwapOrder, Wallet } from '@ledova/shared';
import { useOrderSubmissions } from '@ledova/shared';
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
import { OrderModificationModal } from './components/OrderModificationModal';
import { OrderDetailModal } from './components/OrderDetailModal';
import { SwapSigningModal } from './components/SwapSigningModal';
import { useAppTheme, useThemedStyles } from '../../contexts';

export function TradingScreen() {
  const submissions = useOrderSubmissions(orderSubmissionStore, orderSubmissionSession);
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
  const { wallets, walletAddresses } = useUserTradingWallets();
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

  const [cancelOrderUuid, setCancelOrderUuid] = useState<string | undefined>();
  const [cancelOrderSymbol, setCancelOrderSymbol] = useState<string | undefined>();
  const [cancelWallet, setCancelWallet] = useState<Wallet | null>(null);
  const [showCancelSigning, setShowCancelSigning] = useState(false);

  const [modifyOrder, setModifyOrder] = useState<TransferOrder | null>(null);
  const [modifyWallet, setModifyWallet] = useState<Wallet | null>(null);
  const [showModifyOrder, setShowModifyOrder] = useState(false);

  const [detailOrder, setDetailOrder] = useState<TransferOrder | null>(null);
  const [showDetailOrder, setShowDetailOrder] = useState(false);

  const [signSwap, setSignSwap] = useState<SwapOrder | null>(null);
  const [signSwapWallet, setSignSwapWallet] = useState<Wallet | null>(null);
  const [showSwapSigning, setShowSwapSigning] = useState(false);

  const findWalletForAddress = useCallback(
    (address: string): Wallet | null =>
      wallets.find((w: Wallet) => w.address.toLowerCase() === address.toLowerCase()) || null,
    [wallets],
  );

  const handleBuy = () => {
    signingGeneration.current++;
    submissions.close();
    setCreateOrderType('buy');
    setShowCreateOrder(true);
  };

  const handleSell = () => {
    signingGeneration.current++;
    submissions.close();
    setCreateOrderType('sell');
    setShowCreateOrder(true);
  };

  const handleCreateOrderSubmit = async (data: CreateOrderRequest): Promise<boolean> => {
    const generation = signingGeneration.current;
    const accepted = await submissions.begin(data, wallets.find((wallet) => wallet.uuid === data.walletUuid) ?? null);
    if (accepted && generation === signingGeneration.current) setShowCreateOrder(false);
    return accepted;
  };

  const handleCancelOrder = useCallback(
    (orderUuid: string) => {
      const order = userOrders.orders.find((o) => o.uuid === orderUuid);
      if (!order) return;
      setCancelOrderUuid(orderUuid);
      setCancelOrderSymbol(order.tokenSymbol);
      setCancelWallet(findWalletForAddress(order.walletAddress));
      setShowCancelSigning(true);
    },
    [userOrders.orders, findWalletForAddress],
  );

  const handleEditOrder = useCallback(
    (order: TransferOrder) => {
      setModifyOrder(order);
      setModifyWallet(findWalletForAddress(order.walletAddress));
      setShowModifyOrder(true);
    },
    [findWalletForAddress],
  );

  const handleViewOrder = useCallback((order: TransferOrder) => {
    setDetailOrder(order);
    setShowDetailOrder(true);
  }, []);

  const handleSignSwap = useCallback(
    (swap: SwapOrder) => {
      const isSeller = walletAddresses.some((a: string) => a.toLowerCase() === swap.sellerAddress.toLowerCase());
      setSignSwap(swap);
      setSignSwapWallet(findWalletForAddress(isSeller ? swap.sellerAddress : swap.buyerAddress));
      setShowSwapSigning(true);
    },
    [walletAddresses, findWalletForAddress],
  );

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
        mode="create"
        submission={submissions.active}
        tokens={tokens ?? []}
        wallet={wallets.find((wallet) => wallet.uuid === submissions.active?.record.walletUuid) ?? null}
        onSuccess={handleSigningSuccess}
      />

      <OrderSigningModal
        visible={showCancelSigning}
        onClose={() => setShowCancelSigning(false)}
        mode="cancel"
        orderUuid={cancelOrderUuid}
        orderSymbol={cancelOrderSymbol}
        wallet={cancelWallet}
        onSuccess={handleSigningSuccess}
      />

      <OrderModificationModal
        visible={showModifyOrder}
        onClose={() => setShowModifyOrder(false)}
        order={modifyOrder}
        wallet={modifyWallet}
        onSuccess={handleSigningSuccess}
      />

      <OrderDetailModal
        visible={showDetailOrder}
        onClose={() => setShowDetailOrder(false)}
        order={detailOrder}
        onModify={handleEditOrder}
        onCancel={handleCancelOrder}
      />

      <SwapSigningModal
        visible={showSwapSigning}
        onClose={() => setShowSwapSigning(false)}
        swap={signSwap}
        wallet={signSwapWallet}
        onSuccess={handleSwapSuccess}
      />
    </GradientBackground>
  );
}
