import { ArrowUpIcon, ArrowDownIcon } from '@phosphor-icons/react';
import {
  formatCryptoBalance,
  formatShortDate,
  formatTime,
  getBlockchainShortName,
  DESIGN_TOKENS,
} from '@ledova/shared';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
import type { Transaction } from '@ledova/shared';

interface TransactionListItemProps {
  transaction: Transaction;
  onClick: (transaction: Transaction) => void;
}

export function TransactionListItem({ transaction, onClick }: TransactionListItemProps) {
  const walletAddr = transaction.walletAddress?.toLowerCase() || '';
  const toAddress = transaction.toAddress?.toLowerCase() || '';
  const incoming = toAddress === walletAddr;
  const amount = parseFloat(transaction.amount || '0');

  const displaySymbol = getBlockchainShortName(transaction.assetSymbol || '');
  const displayAmount = formatCryptoBalance(amount, displaySymbol);

  return (
    <button
      type="button"
      onClick={() => onClick(transaction)}
      className="w-full flex items-center justify-between py-3 px-2 hover:bg-surface-tertiary transition-colors text-left"
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {incoming ? (
          <ArrowDownIcon size={ICON_SM} className="text-success-light flex-shrink-0" weight="light" />
        ) : (
          <ArrowUpIcon size={ICON_SM} className="text-error-light flex-shrink-0" weight="light" />
        )}
        <span className="text-xs font-semibold text-text-secondary">{displaySymbol}</span>
        <span className="text-xs text-text-subtle">•</span>
        <span className="text-xs text-text-subtle truncate">
          {formatShortDate(transaction.blockTimestamp)} {formatTime(transaction.blockTimestamp)}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-xs text-text-muted">{displayAmount}</span>
      </div>
    </button>
  );
}
