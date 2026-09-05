import { LinkIcon, ArrowUpIcon, ArrowDownIcon } from '@phosphor-icons/react';
import {
  DESIGN_TOKENS,
  formatShortDate,
  formatTime,
  getBlockchainShortName,
  formatCryptoBalance,
} from '@ledova/shared';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
import { useCurrency } from '@hooks/useCurrency';
import type { Transaction } from '@ledova/shared';
import { Accordion } from '@components/Accordion';

interface TransactionsCardProps {
  transactions: Transaction[];
  totalCount: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasNextPage: boolean;
  onLoadMore: () => void;
}

export function TransactionsCard({
  transactions,
  totalCount,
  isLoading,
  isLoadingMore,
  hasNextPage,
  onLoadMore,
}: TransactionsCardProps) {
  const { formatDisplayCurrency } = useCurrency();
  const isIncoming = (transaction: Transaction): boolean => {
    const walletAddr = transaction.walletAddress?.toLowerCase() || '';
    const toAddress = transaction.toAddress?.toLowerCase() || '';
    return toAddress === walletAddr;
  };

  if (isLoading) {
    return (
      <Accordion title="Transactions" icon={<LinkIcon size={ICON_MD} />}>
        <div className="flex items-center justify-center gap-2 py-6">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-mid"></div>
          <span className="text-sm text-text-muted">Loading transactions...</span>
        </div>
      </Accordion>
    );
  }

  if (transactions.length === 0) {
    return (
      <Accordion title="Transactions" icon={<LinkIcon size={ICON_MD} />}>
        <div className="flex items-center justify-center py-6">
          <span className="text-sm text-text-muted">No transactions found</span>
        </div>
      </Accordion>
    );
  }

  return (
    <Accordion title="Transactions" icon={<LinkIcon size={ICON_MD} />}>
      <div className="flex flex-col">
        <div className="max-h-[300px] overflow-y-auto space-y-1">
          {transactions.map((transaction, index) => {
            const incoming = isIncoming(transaction);
            const amount = parseFloat(transaction.amount || '0');
            const marketValue = transaction.marketValue ? parseFloat(transaction.marketValue) : null;
            const chainShortName = getBlockchainShortName(transaction.assetSymbol || '');

            return (
              <div
                key={transaction.uuid || index}
                className="flex items-center justify-between gap-2 py-2 overflow-hidden"
              >
                <div className="flex items-center gap-1.5 min-w-0 overflow-hidden">
                  {incoming ? (
                    <ArrowDownIcon size={ICON_SM} className="text-success-light flex-shrink-0" weight="light" />
                  ) : (
                    <ArrowUpIcon size={ICON_SM} className="text-error-light flex-shrink-0" weight="light" />
                  )}
                  <span className="text-xs font-semibold text-text-secondary flex-shrink-0">{chainShortName}</span>
                  <span className="text-xs text-text-subtle flex-shrink-0">•</span>
                  <span className="text-xs text-text-subtle truncate">
                    {formatShortDate(transaction.blockTimestamp)} {formatTime(transaction.blockTimestamp)}
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-sm text-text-muted whitespace-nowrap">
                    {formatCryptoBalance(amount, chainShortName)}
                  </span>
                  {marketValue !== null && (
                    <span className="text-sm font-semibold text-text-primary whitespace-nowrap">
                      {formatDisplayCurrency(marketValue)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-end pt-3 mt-2 border-t border-border-subtle text-xs text-text-subtle">
          <span className="inline-flex items-center gap-1">
            {transactions.length} of {totalCount} transaction{totalCount !== 1 ? 's' : ''}
            {hasNextPage && (
              <>
                <span>&middot;</span>
                <button
                  type="button"
                  onClick={onLoadMore}
                  disabled={isLoadingMore}
                  className="text-brand-mid hover:text-brand-light transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? 'Loading...' : 'Load More'}
                </button>
              </>
            )}
          </span>
        </div>
      </div>
    </Accordion>
  );
}
