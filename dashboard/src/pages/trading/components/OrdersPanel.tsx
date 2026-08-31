import { useState, useMemo } from 'react';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  ArrowsLeftRightIcon,
  ArrowsDownUpIcon,
  ClockIcon,
  PencilSimpleIcon,
  TrashIcon,
  QrCodeIcon,
  SpinnerGapIcon,
} from '@phosphor-icons/react';
import type { TransferOrder, SwapOrder, OrderBook as OrderBookType, OrderBookEntry } from '@ledova/shared-types';
import { formatCurrency } from '@ledova/shared-utils';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

function getTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return 'now';
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatSwapTimeRemaining(expiresAt: string): string {
  const expiry = new Date(expiresAt);
  const now = new Date();
  const ms = expiry.getTime() - now.getTime();
  if (ms <= 0) return 'Expired';
  const hours = Math.floor(ms / (1000 * 60 * 60));
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

// --- Order Book Section ---

function OrderBookRow({
  entry,
  maxQuantity,
  side,
}: {
  entry: OrderBookEntry;
  maxQuantity: number;
  side: 'ask' | 'bid';
}) {
  const depthPercent = maxQuantity > 0 ? (entry.quantity / maxQuantity) * 100 : 0;
  const total = parseFloat(entry.price) * entry.quantity;
  const isAsk = side === 'ask';

  return (
    <div className="relative flex items-center justify-between px-4 py-1.5 text-sm">
      <div
        className={`absolute inset-y-0 ${isAsk ? 'right-0' : 'left-0'} opacity-[0.06] ${isAsk ? 'bg-error' : 'bg-success'}`}
        style={{ width: `${Math.min(depthPercent, 100)}%` }}
      />
      <span className={`relative font-mono text-xs ${isAsk ? 'text-error-light' : 'text-success-light'}`}>
        {formatCurrency(parseFloat(entry.price))}
      </span>
      <span className="relative text-xs text-text-secondary">{entry.quantity.toLocaleString()}</span>
      <span className="relative text-xs text-text-muted">{formatCurrency(total)}</span>
    </div>
  );
}

function OrderBookSide({
  entries,
  maxQuantity,
  side,
  emptyLabel,
}: {
  entries: OrderBookEntry[];
  maxQuantity: number;
  side: 'ask' | 'bid';
  emptyLabel: string;
}) {
  const isAsk = side === 'ask';
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-border-subtle/30">
        <span className={`text-xs font-medium ${isAsk ? 'text-error-light' : 'text-success-light'}`}>Price</span>
        <span className="text-xs text-text-muted">Qty</span>
        <span className="text-xs text-text-muted">Total</span>
      </div>
      {entries.length === 0 ? (
        <div className="text-center py-4 text-xs text-text-subtle">{emptyLabel}</div>
      ) : (
        <div className="max-h-[200px] overflow-y-auto">
          {entries.map((entry, i) => (
            <OrderBookRow key={`${side}-${i}`} entry={entry} maxQuantity={maxQuantity} side={side} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- Combined Panel ---

interface OrdersPanelProps {
  tokenSymbol: string;
  orderBook: OrderBookType | null;
  isLoadingOrderBook: boolean;
  userOrders: TransferOrder[];
  isLoadingUserOrders: boolean;
  onCancelOrder: (uuid: string) => void;
  onEditOrder: (order: TransferOrder) => void;
  swaps: SwapOrder[] | undefined;
  isLoadingSwaps: boolean;
  walletAddresses: string[];
  onSignSwap: (swap: SwapOrder) => void;
}

export function OrdersPanel({
  tokenSymbol,
  orderBook,
  isLoadingOrderBook,
  userOrders,
  isLoadingUserOrders,
  onCancelOrder,
  onEditOrder,
  swaps,
  isLoadingSwaps,
  walletAddresses,
  onSignSwap,
}: OrdersPanelProps) {
  const [confirmingOrderId, setConfirmingOrderId] = useState<string | null>(null);

  const normalizedAddresses = useMemo(() => walletAddresses.map((a) => a.toLowerCase()), [walletAddresses]);

  // Order book data
  const { asks, bids, maxQuantity, spread } = useMemo(() => {
    if (!orderBook)
      return {
        asks: [] as OrderBookEntry[],
        bids: [] as OrderBookEntry[],
        maxQuantity: 0,
        spread: null as string | null,
      };
    const asksSorted = [...orderBook.sellOrders].sort((a, b) => parseFloat(a.price) - parseFloat(b.price));
    const bidsSorted = [...orderBook.buyOrders].sort((a, b) => parseFloat(b.price) - parseFloat(a.price));
    const allQuantities = [...asksSorted, ...bidsSorted].map((e) => e.quantity);
    const max = allQuantities.length > 0 ? Math.max(...allQuantities) : 0;
    const bestAsk = asksSorted.length > 0 ? parseFloat(asksSorted[0].price) : null;
    const bestBid = bidsSorted.length > 0 ? parseFloat(bidsSorted[0].price) : null;
    const spreadVal = bestAsk !== null && bestBid !== null ? (bestAsk - bestBid).toFixed(2) : null;
    return { asks: asksSorted, bids: bidsSorted, maxQuantity: max, spread: spreadVal };
  }, [orderBook]);

  // User orders
  const openOrders = userOrders.filter(
    (o) => (o.status === 'open' || o.status === 'partially_filled') && o.tokenSymbol === tokenSymbol,
  );

  const pendingSwaps = useMemo(() => {
    if (!swaps || walletAddresses.length === 0) return [];
    return swaps.filter((s) => {
      const isSeller = normalizedAddresses.includes(s.sellerAddress.toLowerCase());
      const isBuyer = normalizedAddresses.includes(s.buyerAddress.toLowerCase());
      if (!isSeller && !isBuyer) return false;
      const hasSigned = isSeller ? s.sellerHasSigned : s.buyerHasSigned;
      return !hasSigned && ['created', 'seller_signed', 'buyer_signed'].includes(s.status);
    });
  }, [swaps, walletAddresses, normalizedAddresses]);

  const handleConfirmCancel = (uuid: string) => {
    onCancelOrder(uuid);
    setConfirmingOrderId(null);
  };

  const hasMarketOrders = asks.length > 0 || bids.length > 0;
  const hasUserActivity = openOrders.length > 0 || pendingSwaps.length > 0;

  return (
    <div className="bg-surface-raised rounded-xl border border-border-subtle overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-border-subtle">
        <div>
          <h2 className="text-base font-semibold text-text-primary">{tokenSymbol} Orders</h2>
          <p className="text-xs text-text-muted">Market orders and your activity</p>
        </div>
        {spread !== null && (
          <div className="text-right">
            <span className="text-xs text-text-muted">Spread </span>
            <span className="text-xs font-medium text-text-secondary">{formatCurrency(parseFloat(spread))}</span>
          </div>
        )}
      </div>

      {/* Market Order Book */}
      {isLoadingOrderBook ? (
        <div className="flex items-center justify-center py-8">
          <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
        </div>
      ) : !hasMarketOrders ? (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <ArrowsDownUpIcon size={ICON_XL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">No open orders for {tokenSymbol}</p>
          <p className="text-xs text-text-subtle">Place the first order to start trading</p>
        </div>
      ) : (
        <div className="flex divide-x divide-border-subtle">
          <OrderBookSide entries={bids} maxQuantity={maxQuantity} side="bid" emptyLabel="No bids" />
          <OrderBookSide entries={asks} maxQuantity={maxQuantity} side="ask" emptyLabel="No asks" />
        </div>
      )}

      {/* Your Orders Section */}
      {(isLoadingUserOrders || isLoadingSwaps || hasUserActivity) && (
        <>
          <div className="flex items-center gap-2 px-4 py-2 bg-surface-tertiary/50 border-t border-border-subtle">
            <span className="text-xs font-semibold text-text-secondary">Your Orders</span>
            {(isLoadingUserOrders || isLoadingSwaps) && (
              <SpinnerGapIcon size={ICON_XS} className="text-text-muted animate-spin" />
            )}
          </div>

          {openOrders.map((order) => {
            const isBuy = order.orderType === 'buy';
            const qty = order.remainingQuantity ?? order.quantity;
            const totalValue = (parseFloat(order.pricePerShare) * qty).toFixed(2);
            const timeAgo = getTimeAgo(new Date(order.createdAt));
            const isConfirming = confirmingOrderId === order.uuid;

            return (
              <div
                key={order.uuid}
                className="flex items-center justify-between py-2.5 px-4 border-b border-border-subtle/30 last:border-b-0"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span
                    className={`p-1 rounded ${isBuy ? 'bg-success/[0.06] text-success-light' : 'bg-error/[0.06] text-error-light'}`}
                  >
                    {isBuy ? (
                      <ArrowUpIcon size={ICON_XS} weight="bold" />
                    ) : (
                      <ArrowDownIcon size={ICON_XS} weight="bold" />
                    )}
                  </span>
                  <span className="text-sm font-medium text-text-primary">{order.tokenSymbol}</span>
                  <span className="text-xs text-text-muted">•</span>
                  <span className="text-sm text-text-primary">
                    {qty}@${order.pricePerShare}
                  </span>
                  <span className="text-xs text-text-subtle">= ${totalValue}</span>
                  <span className="text-xs text-text-subtle">{timeAgo}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 ml-3">
                  {isConfirming ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-muted">Cancel?</span>
                      <button
                        onClick={() => handleConfirmCancel(order.uuid)}
                        className="text-xs font-medium text-error-light"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => setConfirmingOrderId(null)}
                        className="text-xs font-medium text-text-muted hover:text-text-primary"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => onEditOrder(order)}
                        className="p-1 text-brand-light hover:text-brand-subtle"
                        title="Modify"
                      >
                        <PencilSimpleIcon size={ICON_SM} />
                      </button>
                      <button
                        onClick={() => setConfirmingOrderId(order.uuid)}
                        className="p-1 text-error-light"
                        title="Cancel"
                      >
                        <TrashIcon size={ICON_SM} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}

          {pendingSwaps.map((swap) => {
            const isSeller = normalizedAddresses.includes(swap.sellerAddress.toLowerCase());
            const userRole = isSeller ? 'Seller' : 'Buyer';
            const timeRemaining = formatSwapTimeRemaining(swap.expiresAt);
            const paymentDisplay = (swap.paymentAmount / 100).toFixed(2);

            return (
              <div
                key={swap.uuid}
                className="flex items-center justify-between py-2.5 px-4 border-b border-border-subtle/30 last:border-b-0 bg-warning-light/5"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="p-1 rounded bg-brand-mid/10 text-brand-light">
                    <ArrowsLeftRightIcon size={ICON_XS} weight="bold" />
                  </span>
                  <span className="text-sm font-medium text-text-primary">{swap.shareTokenSymbol}</span>
                  <span className="text-xs text-text-muted">•</span>
                  <span className="text-sm text-text-primary">
                    {swap.shareAmount}@${paymentDisplay}
                  </span>
                  <span
                    className={`text-xs font-medium px-1.5 py-0.5 rounded ${isSeller ? 'bg-error-light/10 text-error-light' : 'bg-success-light/10 text-success-light'}`}
                  >
                    {userRole}
                  </span>
                  <span className="text-xs text-text-subtle flex items-center gap-0.5">
                    <ClockIcon size={ICON_XS} />
                    {timeRemaining}
                  </span>
                </div>
                <button
                  onClick={() => onSignSwap(swap)}
                  className="p-1.5 rounded-lg bg-brand-mid hover:bg-brand text-white"
                  title="Sign swap"
                >
                  <QrCodeIcon size={ICON_SM} weight="bold" />
                </button>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
