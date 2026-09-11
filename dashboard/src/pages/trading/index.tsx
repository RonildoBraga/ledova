import { useState, useMemo, useRef, useEffect } from 'react';
import { CheckCircleIcon } from '@phosphor-icons/react';
import type { TransferOrder, CreateOrderRequest, Wallet, SwapOrder } from '@ledova/shared';
import {
  DESIGN_TOKENS,
  hasSwapSettlementContext,
  selectSwapSettlementLookup,
  useOrderSubmissions,
  useOrderActions,
  useSwapSettlements,
} from '@ledova/shared';
import { orderSubmissionStore } from '@services/orderSubmissions';
import { settlementWalletKey, swapSettlementCrypto, swapSettlementStore } from '@services/swapSettlements';
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
import { SwapSettlementFlow } from './components/SwapSettlementFlow';
import { OrderSigningFlow } from './components/OrderSigningFlow';
import { OrderActionFlow } from './components/OrderActionFlow';
import { orderActionStore } from '@services/orderActions';
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
  const actions = useOrderActions(orderActionStore);
  const settlements = useSwapSettlements(swapSettlementStore, swapSettlementCrypto);
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
  const [swapSelectionError, setSwapSelectionError] = useState<string | null>(null);

  useTradingEvents(selectedTokenUuid);

  const { wallets, actionWallets, walletAddresses } = useUserTradingWallets();
  const latestWallets = useRef(wallets);
  latestWallets.current = wallets;
  useEffect(() => {
    if (settlements.active && !settlements.active.isCurrent()) settlements.close();
  }, [settlements.active, settlements.close, wallets]);
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
    closeSwapSigning();
    actions.close();
    const signingWallet = wallets.find((w) => w.uuid === data.walletUuid);
    return submissions.begin(data, signingWallet ?? null);
  };

  const handleCancelOrder = (uuid: string) => {
    signingGeneration.current++;
    closeSwapSigning();
    submissions.close();
    actions.open(uuid, 'cancel');
  };

  const handleEditOrder = (order: TransferOrder) => {
    signingGeneration.current++;
    closeSwapSigning();
    submissions.close();
    actions.open(order.uuid, 'modify');
  };

  const closeSwapSigning = () => {
    settlements.close();
    setSelectedSwap(null);
    setIsSwapSigningOpen(false);
    setSwapSelectionError(null);
  };

  const walletCurrent = (walletUuid: string) => {
    const selected = latestWallets.current.find((candidate) => candidate.uuid === walletUuid) ?? null;
    const key = settlementWalletKey(selected);
    return () =>
      key === settlementWalletKey(latestWallets.current.find((candidate) => candidate.uuid === walletUuid) ?? null);
  };

  const handleSignSwap = (swap: SwapOrder) => {
    signingGeneration.current++;
    submissions.close();
    actions.close();
    closeSwapSigning();
    if (swap.settlementProtocolVersion === 0) {
      setSelectedSwap(swap);
      setIsSwapSigningOpen(true);
      return;
    }
    if (!hasSwapSettlementContext(swap) || !settlements.owner) {
      setSwapSelectionError('The saved trade details are incomplete. Refresh the trade before signing.');
      return;
    }
    try {
      const choices = (['seller', 'buyer'] as const).flatMap((role) => {
        const party = swap.settlementContext[role];
        const wallet = wallets.find(
          (candidate) =>
            candidate.uuid === party.walletUuid &&
            candidate.userAccount === settlements.owner!.ownerAccountUuid &&
            candidate.userAccount === party.ownerAccountUuid &&
            candidate.address.toLowerCase() === party.address.toLowerCase(),
        );
        return wallet
          ? [{ wallet, party, signed: role === 'seller' ? swap.sellerHasSigned : swap.buyerHasSigned }]
          : [];
      });
      const choice = choices.find((candidate) => !candidate.signed) ?? choices[0];
      if (!choice) {
        setSwapSelectionError('This trade has no matching verified wallet in the current account.');
        return;
      }
      const selection = selectSwapSettlementLookup(swap, settlements.owner, choice.wallet, choice.party.orderUuid);
      settlements.open(selection, walletCurrent(choice.wallet.uuid));
    } catch {
      setSwapSelectionError('The trade details did not match the selected account and wallet.');
    }
  };

  const getSwapSigningWalletAddress = (swap: SwapOrder | null): string | undefined => {
    if (!swap) return undefined;
    return (
      (!swap.sellerHasSigned && walletAddresses.find((a) => a.toLowerCase() === swap.sellerAddress.toLowerCase())) ||
      (!swap.buyerHasSigned && walletAddresses.find((a) => a.toLowerCase() === swap.buyerAddress.toLowerCase())) ||
      walletAddresses.find((a) => a.toLowerCase() === swap.sellerAddress.toLowerCase()) ||
      walletAddresses.find((a) => a.toLowerCase() === swap.buyerAddress.toLowerCase())
    );
  };

  const getSwapSigningWallet = (swap: SwapOrder | null): Wallet | null => {
    const address = getSwapSigningWalletAddress(swap);
    if (!address) return null;
    return wallets.find((w) => w.address.toLowerCase() === address.toLowerCase()) || null;
  };

  const handleCloseOrderSigningFlow = () => {
    signingGeneration.current++;
    submissions.close();
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
                  closeSwapSigning();
                  actions.close();
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

          <section
            className="space-y-2 rounded-lg bg-surface-tertiary p-4"
            aria-label="Saved cancellations and changes"
          >
            <h2 className="font-semibold">Saved cancellations and changes</h2>
            {actions.error && <p role="alert">{actions.error}</p>}
            {actions.pending.map((record, index) => (
              <button
                key={record.actionId}
                className="block text-brand-light"
                onClick={() => {
                  signingGeneration.current++;
                  closeSwapSigning();
                  submissions.close();
                  actions.recover(record);
                }}
              >
                Check {record.purpose === 'cancel' ? 'cancellation' : 'change'} {index + 1}
              </button>
            ))}
            <button
              className="text-sm text-brand-light"
              disabled={actions.isLoading}
              onClick={() => void actions.refresh()}
            >
              Refresh saved actions
            </button>
          </section>

          <section className="space-y-2 rounded-lg bg-surface-tertiary p-4" aria-label="Saved trade signatures">
            <h2 className="font-semibold">Saved trade signatures and approvals</h2>
            <p className="text-sm text-text-muted">
              Check the original trade after a lost connection or interrupted signing.
            </p>
            {swapSelectionError && <p role="alert">{swapSelectionError}</p>}
            {settlements.error && <p role="alert">{settlements.error}</p>}
            {settlements.pending.map((record, index) => (
              <button
                key={`${record.orderUuid}/${record.swapUuid}/${record.walletUuid}/${record.settlementDigest}/${record.kind}/${record.kind === 'approval' ? record.txHash : record.signerAddress}`}
                className="block text-brand-light"
                onClick={() => {
                  signingGeneration.current++;
                  submissions.close();
                  actions.close();
                  closeSwapSigning();
                  settlements.recover(record, walletCurrent(record.walletUuid));
                }}
              >
                Check saved {record.kind === 'approval' ? 'approval' : 'trade signature'} {index + 1}
              </button>
            ))}
            <button
              className="text-sm text-brand-light"
              disabled={settlements.isLoading}
              onClick={() => void settlements.refresh()}
            >
              Refresh saved trades
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

      {isSwapSigningOpen && selectedSwap && (
        <SwapSigningFlow
          isOpen
          onClose={closeSwapSigning}
          swap={selectedSwap}
          walletAddress={getSwapSigningWalletAddress(selectedSwap) || ''}
          wallet={getSwapSigningWallet(selectedSwap)}
          orderUuid={
            getSwapSigningWalletAddress(selectedSwap)?.toLowerCase() === selectedSwap.sellerAddress.toLowerCase()
              ? selectedSwap.sellOrderUuid
              : selectedSwap.buyOrderUuid
          }
        />
      )}
      {settlements.active && (
        <SwapSettlementFlow settlement={settlements.active} wallets={wallets} onClose={settlements.close} />
      )}

      <OrderSigningFlow
        isOpen={!!submissions.active}
        onClose={handleCloseOrderSigningFlow}
        submission={submissions.active}
        tokens={tokens ?? []}
        wallet={wallets.find((wallet) => wallet.uuid === submissions.active?.record.walletUuid) ?? null}
        onSuccess={handleOrderSigningSuccess}
      />
      {actions.active && (
        <OrderActionFlow
          key={actions.active.record?.actionId ?? `${actions.active.orderUuid}/${actions.active.purpose}`}
          action={actions.active}
          wallets={actionWallets}
          onClose={actions.close}
        />
      )}
    </main>
  );
}

export default TradingPage;
