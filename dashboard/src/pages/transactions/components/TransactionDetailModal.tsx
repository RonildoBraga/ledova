import { ArrowUpIcon, ArrowDownIcon } from '@phosphor-icons/react';
import { formatCryptoBalance, formatShortDate, formatTime } from '@ledova/shared-utils';
import { getChainShortCode, DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;
import type { Transaction } from '@ledova/shared-types';
import { Modal } from '@components/Modal';

interface TransactionDetailModalProps {
  isOpen: boolean;
  transaction: Transaction | null;
  onClose: () => void;
  onViewExplorer: () => void;
}

function DetailRow({
  label,
  value,
  valueClassName = '',
  mono = false,
}: {
  label: string;
  value: string;
  valueClassName?: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-3">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-sm font-medium text-text-primary ${valueClassName} ${mono ? 'font-mono' : ''}`}>
        {value}
      </span>
    </div>
  );
}

export function TransactionDetailModal({ isOpen, transaction, onClose, onViewExplorer }: TransactionDetailModalProps) {
  if (!transaction) return null;

  const walletAddr = transaction.walletAddress?.toLowerCase() || '';
  const toAddress = transaction.toAddress?.toLowerCase() || '';
  const incoming = toAddress === walletAddr;
  const amount = parseFloat(transaction.amount || '0');

  const displayAmount = `${incoming ? '+' : '-'}${formatCryptoBalance(amount, transaction.assetSymbol || '')}`;

  const showExplorerButton = !!transaction.txHash;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title=""
      showFooter={true}
      cancelLabel="Close"
      confirmLabel="View on Explorer"
      onConfirm={showExplorerButton ? onViewExplorer : undefined}
      confirmDisabled={!showExplorerButton}
    >
      <div className="flex flex-col items-center py-4">
        {incoming ? (
          <ArrowDownIcon size={ICON_XXL} className="text-success-light mb-3" weight="light" />
        ) : (
          <ArrowUpIcon size={ICON_XXL} className="text-error-light mb-3" weight="light" />
        )}
        <h3 className="text-xl font-semibold text-text-primary">{incoming ? 'Received' : 'Sent'}</h3>
      </div>

      <div className="space-y-0 divide-y divide-border-subtle">
        <DetailRow label="Asset" value={transaction.assetName || transaction.assetSymbol || 'Unknown Asset'} />
        <DetailRow
          label="Amount"
          value={displayAmount}
          valueClassName={incoming ? 'text-success-light' : 'text-error-light'}
        />
        <DetailRow label="Chain" value={transaction.chain ? getChainShortCode(transaction.chain) : 'Unknown'} />
        <DetailRow
          label="Timestamp"
          value={`${formatShortDate(transaction.blockTimestamp)} ${formatTime(transaction.blockTimestamp)}`}
        />
        {transaction.status && (
          <DetailRow
            label="Status"
            value={transaction.status === 'success' ? '✓ Success' : '✗ Failed'}
            valueClassName={transaction.status === 'success' ? 'text-success-light' : 'text-error-light'}
          />
        )}
        {transaction.transactionFee && (
          <DetailRow
            label="Fee"
            value={formatCryptoBalance(parseFloat(transaction.transactionFee), transaction.assetSymbol || '')}
          />
        )}
        {transaction.txHash && (
          <DetailRow
            label="Tx Hash"
            value={`${transaction.txHash.slice(0, 10)}...${transaction.txHash.slice(-8)}`}
            mono
          />
        )}
      </div>
    </Modal>
  );
}
