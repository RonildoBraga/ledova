import { useState, useMemo } from 'react';
import { CheckCircleIcon } from '@phosphor-icons/react';
import type { TransferOrder, CreateOrderRequest, Wallet, SwapOrder } from '@ledova/shared';
import { DESIGN_TOKENS } from '@ledova/shared';
import { Modal } from '@components/Modal';
import {
  useShareTokens,
  useTrading,
  useUserTradingWallets,
  useWalletsWhitelistStatus,
  useOrderBook,
} from './useTrading';
import { useSwapOrdersMulti } from './hooks/useAtomicSwaps';
import { SwapSigningFlow } from './components/SwapSigningFlow';
import { OrderSigningFlow } from './components/OrderSigningFlow';
import { OrderModificationModal } from './components/OrderModificationModal';
import { MarketOverview } from './components/MarketOverview';
import { OrdersPanel } from './components/OrdersPanel';
import { PlaceOrderPanel } from './components/PlaceOrderPanel';
import { useTradingEvents } from './hooks/useTradingEvents';

const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

function OrderSuccessModal({
  isOpen,
  order,
  onClose,
}: {
  isOpen: boolean;
  order: TransferOrder | null;
  onClose: () => void;
}) {
  if (!order) return null;
  const isBuy = order.orderType === 'buy';

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Order Created" size="sm">
      <div className="flex flex-col items-center gap-4 py-4">
        <div className="w-16 h-16 rounded-full bg-success-light/10 flex items-center justify-center">
          <CheckCircleIcon size={ICON_XL} className="text-success-light" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-semibold text-text-primary">{isBuy ? 'Buy' : 'Sell'} Order Placed</h3>
          <p className="text-sm text-text-muted mt-1">
            Your order for {order.quantity} {order.tokenSymbol} shares has been placed.
          </p>
        </div>
        <div className="w-full p-4 rounded-lg bg-surface-tertiary space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-text-muted">Quantity</span>
            <span className="text-text-primary">{order.quantity} shares</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-text-muted">Price</span>
            <span className="text-text-primary">${order.pricePerShare}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-text-muted">Total</span>
            <span className="text-text-primary font-semibold">${order.totalValue}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-full py-3 rounded-lg bg-brand-mid hover:bg-brand text-white font-semibold transition-colors"
        >
          Done
        </button>
      </div>
    </Modal>
  );
}

export function TradingPage() {
  const { data: tokens, isLoading } = useShareTokens();
  const [selectedTokenUuid, setSelectedTokenUuid] = useState<string | null>(null);

  const [successModalOpen, setSuccessModalOpen] = useState(false);
  const [createdOrder, setCreatedOrder] = useState<TransferOrder | null>(null);

  const [selectedSwap, setSelectedSwap] = useState<SwapOrder | null>(null);
  const [isSwapSigningOpen, setIsSwapSigningOpen] = useState(false);

  const [pendingOrderData, setPendingOrderData] = useState<CreateOrderRequest | null>(null);
  const [pendingCancelOrderUuid, setPendingCancelOrderUuid] = useState<string | null>(null);
  const [pendingCancelOrderSymbol, setPendingCancelOrderSymbol] = useState<string | null>(null);
  const [orderSigningWallet, setOrderSigningWallet] = useState<Wallet | null>(null);
  const [isOrderSigningOpen, setIsOrderSigningOpen] = useState(false);

  const [orderToModify, setOrderToModify] = useState<TransferOrder | null>(null);
  const [isModificationModalOpen, setIsModificationModalOpen] = useState(false);

  useTradingEvents(selectedTokenUuid);

  const { wallets, walletAddresses } = useUserTradingWallets();
  const { isWhitelisted, isLoading: isLoadingWhitelistStatus } = useWalletsWhitelistStatus(walletAddresses);
  const { data: swaps, isLoading: isLoadingSwaps } = useSwapOrdersMulti(walletAddresses);

  // Auto-select first token
  useMemo(() => {
    if (tokens && tokens.length > 0 && !selectedTokenUuid) {
      setSelectedTokenUuid(tokens[0].uuid);
    }
  }, [tokens, selectedTokenUuid]);

  const selectedToken = useMemo(() => {
    if (!tokens || !selectedTokenUuid) return null;
    return tokens.find((t) => t.uuid === selectedTokenUuid) || null;
  }, [tokens, selectedTokenUuid]);

  const { userOrders, isLoadingUserOrders, getWalletsWithHoldings } = useTrading({
    tokenUuid: selectedTokenUuid || undefined,
    walletAddresses,
  });

  const { data: orderBookData, isLoading: isLoadingOrderBook } = useOrderBook(selectedTokenUuid || undefined);

  // --- Handlers ---

  const handleCreateOrder = async (data: CreateOrderRequest): Promise<TransferOrder> => {
    const signingWallet = wallets.find((w) => w.uuid === data.walletUuid);
    setOrderSigningWallet(signingWallet || null);
    setPendingOrderData(data);
    setIsOrderSigningOpen(true);
    return {} as TransferOrder;
  };

  const handleCancelOrder = (uuid: string) => {
    const order = userOrders.find((o) => o.uuid === uuid);
    if (order) {
      const signingWallet = wallets.find((w) => w.address.toLowerCase() === order.walletAddress.toLowerCase());
      setOrderSigningWallet(signingWallet || wallets[0] || null);
      setPendingCancelOrderSymbol(order.tokenSymbol);
    } else {
      setOrderSigningWallet(wallets[0] || null);
      setPendingCancelOrderSymbol(null);
    }
    setPendingCancelOrderUuid(uuid);
    setIsOrderSigningOpen(true);
  };

  const handleEditOrder = (order: TransferOrder) => {
    setOrderToModify(order);
    setIsModificationModalOpen(true);
  };

  const handleSignSwap = (swap: SwapOrder) => {
    setSelectedSwap(swap);
    setIsSwapSigningOpen(true);
  };

  const getSwapSigningWalletAddress = (swap: SwapOrder | null): string | undefined => {
    if (!swap) return undefined;
    return (
      walletAddresses.find((a) => a.toLowerCase() === swap.sellerAddress.toLowerCase()) ||
      walletAddresses.find((a) => a.toLowerCase() === swap.buyerAddress.toLowerCase())
    );
  };

  const getSwapSigningWallet = (swap: SwapOrder | null): Wallet | null => {
    const address = getSwapSigningWalletAddress(swap);
    if (!address) return null;
    return wallets.find((w) => w.address.toLowerCase() === address.toLowerCase()) || null;
  };

  const getModificationWallet = (order: TransferOrder | null): Wallet | null => {
    if (!order) return null;
    return wallets.find((w) => w.address.toLowerCase() === order.walletAddress.toLowerCase()) || null;
  };

  const handleCloseOrderSigningFlow = () => {
    setIsOrderSigningOpen(false);
    setPendingOrderData(null);
    setPendingCancelOrderUuid(null);
    setPendingCancelOrderSymbol(null);
    setOrderSigningWallet(null);
  };

  const handleOrderSigningSuccess = (order: TransferOrder) => {
    if (pendingOrderData) {
      setCreatedOrder(order);
      setSuccessModalOpen(true);
    }
    handleCloseOrderSigningFlow();
  };

  // --- Render ---

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">
          {/* Section 1: Market Overview */}
          <MarketOverview
            tokens={tokens || []}
            selectedTokenUuid={selectedTokenUuid}
            onSelectToken={setSelectedTokenUuid}
            isLoading={isLoading}
          />

          {selectedToken && (
            <>
              {/* Section 2: Orders (market + yours combined) */}
              <OrdersPanel
                tokenSymbol={selectedToken.symbol}
                orderBook={orderBookData || null}
                isLoadingOrderBook={isLoadingOrderBook}
                userOrders={userOrders}
                isLoadingUserOrders={isLoadingUserOrders}
                onCancelOrder={handleCancelOrder}
                onEditOrder={handleEditOrder}
                swaps={swaps}
                isLoadingSwaps={isLoadingSwaps}
                walletAddresses={walletAddresses}
                onSignSwap={handleSignSwap}
              />

              {/* Section 3: Place Order */}
              <PlaceOrderPanel
                token={selectedToken}
                wallets={wallets}
                walletsWithHoldings={getWalletsWithHoldings(selectedToken.uuid)}
                onSubmit={handleCreateOrder}
                isWalletWhitelisted={walletAddresses.length > 0 && isWhitelisted(walletAddresses[0])}
                isLoadingWhitelistStatus={isLoadingWhitelistStatus}
              />
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      <OrderSuccessModal isOpen={successModalOpen} order={createdOrder} onClose={() => setSuccessModalOpen(false)} />

      <SwapSigningFlow
        isOpen={isSwapSigningOpen}
        onClose={() => {
          setIsSwapSigningOpen(false);
          setSelectedSwap(null);
        }}
        swap={selectedSwap}
        walletAddress={getSwapSigningWalletAddress(selectedSwap) || ''}
        wallet={getSwapSigningWallet(selectedSwap)}
        orderUuid={selectedSwap?.sellOrderUuid || selectedSwap?.buyOrderUuid}
      />

      <OrderSigningFlow
        isOpen={isOrderSigningOpen}
        onClose={handleCloseOrderSigningFlow}
        mode={pendingCancelOrderUuid ? 'cancel' : 'create'}
        orderData={pendingOrderData || undefined}
        orderUuid={pendingCancelOrderUuid || undefined}
        orderSymbol={pendingCancelOrderSymbol || undefined}
        wallet={orderSigningWallet}
        onSuccess={handleOrderSigningSuccess}
      />

      <OrderModificationModal
        isOpen={isModificationModalOpen}
        onClose={() => {
          setIsModificationModalOpen(false);
          setOrderToModify(null);
        }}
        order={orderToModify}
        wallet={getModificationWallet(orderToModify)}
        onSuccess={() => {
          setIsModificationModalOpen(false);
          setOrderToModify(null);
        }}
      />
    </main>
  );
}

export default TradingPage;
