import React, { useState, useCallback, useMemo } from 'react';
import { View, Text, ScrollView, RefreshControl, TouchableOpacity } from 'react-native';
import type { ShareToken, TransferOrder, CreateOrderRequest, SwapOrder, Wallet } from '@ledova/shared';
import { GradientBackground } from '../../components/GradientBackground';
import {
  useShareTokens,
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

  const [signingOrderData, setSigningOrderData] = useState<CreateOrderRequest | null>(null);
  const [signingOrderSymbol, setSigningOrderSymbol] = useState<string | undefined>();
  const [signingWallet, setSigningWallet] = useState<Wallet | null>(null);
  const [showOrderSigning, setShowOrderSigning] = useState(false);

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

  const handleBuy = useCallback(() => {
    setCreateOrderType('buy');
    setShowCreateOrder(true);
  }, []);

  const handleSell = useCallback(() => {
    setCreateOrderType('sell');
    setShowCreateOrder(true);
  }, []);

  const handleCreateOrderSubmit = useCallback(
    (data: CreateOrderRequest) => {
      setShowCreateOrder(false);
      setSigningOrderData(data);
      setSigningOrderSymbol(selectedToken?.symbol);
      setSigningWallet(wallets.find((wallet: Wallet) => wallet.uuid === data.walletUuid) || null);
      setShowOrderSigning(true);
    },
    [selectedToken, wallets],
  );

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

  const handleSigningSuccess = useCallback(() => {
    userOrders.refetch();
    tokenBalances.refetch();
  }, [userOrders, tokenBalances]);

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
            />

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
          onClose={() => setShowCreateOrder(false)}
          token={selectedToken}
          orderType={createOrderType}
          wallets={wallets}
          walletsWithHoldings={walletsWithHoldings}
          onSubmit={handleCreateOrderSubmit}
          isWalletWhitelisted={whitelistStatus.isWhitelisted}
          isLoadingWhitelistStatus={whitelistStatus.isLoading}
        />
      )}

      <OrderSigningModal
        visible={showOrderSigning}
        onClose={() => setShowOrderSigning(false)}
        mode="create"
        orderData={signingOrderData || undefined}
        orderSymbol={signingOrderSymbol}
        wallet={signingWallet}
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
