import { useState, useMemo, useRef } from 'react';
import { CheckCircleIcon } from '@phosphor-icons/react';
import type { TransferOrder, CreateOrderRequest, Wallet, SwapOrder } from '@ledova/shared';
import { DESIGN_TOKENS, useOrderSubmissions } from '@ledova/shared';
import { orderSubmissionStore } from '@services/orderSubmissions';
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
import { useInvestorEligibilityQuery } from './useTrading';

const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

function OrderSuccessModal({
  isOpen,
  order,
  onClose,
  recovered,
}: {
  isOpen: boolean;
  order: TransferOrder | null;
  onClose: () => void;
  recovered: boolean;
}) {
  if (!order) return null;
  const isBuy = order.orderType === 'buy';

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={recovered ? 'Order recovered' : 'Order created'} size="sm">
      <div className="flex flex-col items-center gap-4 py-4">
        <div className="w-16 h-16 rounded-full bg-success-light/10 flex items-center justify-center">
          <CheckCircleIcon size={ICON_XL} className="text-success-light" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-semibold text-text-primary">
            {isBuy ? 'Buy' : 'Sell'} order {recovered ? 'recovered' : 'placed'}
          </h3>
          <p className="text-sm text-text-muted mt-1">
            Current status: {order.statusDisplay ?? order.status.replace(/_/g, ' ')}.
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
  const submissions = useOrderSubmissions(orderSubmissionStore);
  const signingGeneration = useRef(0);
  const currentSigningGeneration = signingGeneration.current;
  const { data: tokens, isLoading } = useShareTokens();
  const { data: eligibility } = useInvestorEligibilityQuery();
  const isEligible = eligibility?.isEligible ?? false;
  const [selectedTokenUuid, setSelectedTokenUuid] = useState<string | null>(null);

  const [successModalOpen, setSuccessModalOpen] = useState(false);
  const [createdOrder, setCreatedOrder] = useState<TransferOrder | null>(null);
  const [recoveredOrder, setRecoveredOrder] = useState(false);

  const [selectedSwap, setSelectedSwap] = useState<SwapOrder | null>(null);
  const [isSwapSigningOpen, setIsSwapSigningOpen] = useState(false);

  const [pendingCancelOrderUuid, setPendingCancelOrderUuid] = useState<string | null>(null);
  const [pendingCancelOrderSymbol, setPendingCancelOrderSymbol] = useState<string | null>(null);
  const [orderSigningWallet, setOrderSigningWallet] = useState<Wallet | null>(null);
  const [isOrderSigningOpen, setIsOrderSigningOpen] = useState(false);

  const [orderToModify, setOrderToModify] = useState<TransferOrder | null>(null);
  const [isModificationModalOpen, setIsModificationModalOpen] = useState(false);

  useTradingEvents(selectedTokenUuid);

  const { wallets, walletAddresses } = useUserTradingWallets();
  const {
    isWhitelisted,
    getStatus: getWhitelistStatusFor,
    isLoading: isLoadingWhitelistStatus,
  } = useWalletsWhitelistStatus(walletAddresses);
  const { data: swaps, isLoading: isLoadingSwaps } = useSwapOrdersMulti(walletAddresses);

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

  const handleCreateOrder = (data: CreateOrderRequest): Promise<boolean> => {
    const signingWallet = wallets.find((w) => w.uuid === data.walletUuid);
    return submissions.begin(data, signingWallet ?? null);
  };

  const handleCancelOrder = (uuid: string) => {
    signingGeneration.current++;
    submissions.close();
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
    signingGeneration.current++;
    submissions.close();
    setIsOrderSigningOpen(false);
    setPendingCancelOrderUuid(null);
    setPendingCancelOrderSymbol(null);
    setOrderSigningWallet(null);
  };

  const handleOrderSigningSuccess = (order: TransferOrder, recovered = false) => {
    if (signingGeneration.current !== currentSigningGeneration) return;
    if (submissions.active) {
      setCreatedOrder(order);
      setRecoveredOrder(recovered);
      setSuccessModalOpen(true);
    }
    handleCloseOrderSigningFlow();
  };

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">
          <MarketOverview
            tokens={tokens || []}
            selectedTokenUuid={selectedTokenUuid}
            onSelectToken={setSelectedTokenUuid}
            isLoading={isLoading}
            isEligible={isEligible}
          />

          <section className="space-y-2 rounded-lg bg-surface-tertiary p-4" aria-label="Saved orders">
            <h2 className="font-semibold">Saved orders</h2>
            <p className="text-sm text-text-muted">
              Check unfinished orders here. New buy and sell orders are separate orders, even with the same terms.
            </p>
            {submissions.error && <p role="alert">{submissions.error}</p>}
            {submissions.pending.map((record, index) => (
              <button
                key={record.submissionId}
                className="block text-brand-light"
                onClick={() => {
                  signingGeneration.current++;
                  setPendingCancelOrderUuid(null);
                  setIsOrderSigningOpen(false);
                  submissions.recover(record);
                }}
              >
                Check saved order {index + 1}
                {wallets.find((wallet) => wallet.uuid === record.walletUuid)?.name
                  ? ` — ${wallets.find((wallet) => wallet.uuid === record.walletUuid)?.name}`
                  : ''}
              </button>
            ))}
            <button
              onClick={() => void submissions.refresh()}
              disabled={submissions.isLoading}
              className="text-sm text-brand-light"
            >
              Refresh saved orders
            </button>
          </section>

          {selectedToken && (
            <>
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

              <PlaceOrderPanel
                token={selectedToken}
                wallets={wallets}
                walletsWithHoldings={getWalletsWithHoldings(selectedToken.uuid)}
                onSubmit={handleCreateOrder}
                onNewOrder={handleCloseOrderSigningFlow}
                onDismiss={handleCloseOrderSigningFlow}
                submissionError={submissions.error}
                isWalletWhitelisted={walletAddresses.length > 0 && isWhitelisted(walletAddresses[0])}
                isWhitelistStatusUnknown={
                  walletAddresses.length > 0 && getWhitelistStatusFor(walletAddresses[0])?.status === 'unknown'
                }
                isLoadingWhitelistStatus={isLoadingWhitelistStatus}
              />
            </>
          )}
        </div>
      </div>

      <OrderSuccessModal
        isOpen={successModalOpen}
        order={createdOrder}
        recovered={recoveredOrder}
        onClose={() => setSuccessModalOpen(false)}
      />

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
        isOpen={!!submissions.active || isOrderSigningOpen}
        onClose={handleCloseOrderSigningFlow}
        mode={pendingCancelOrderUuid ? 'cancel' : 'create'}
        submission={submissions.active}
        tokens={tokens ?? []}
        orderUuid={pendingCancelOrderUuid || undefined}
        orderSymbol={pendingCancelOrderSymbol || undefined}
        wallet={
          submissions.active
            ? (wallets.find((wallet) => wallet.uuid === submissions.active?.record.walletUuid) ?? null)
            : orderSigningWallet
        }
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
