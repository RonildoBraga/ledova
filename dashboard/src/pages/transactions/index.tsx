import { useEffect, useState } from 'react';
import { FunnelIcon, PackageIcon } from '@phosphor-icons/react';
import { getBlockExplorerTxUrl, DESIGN_TOKENS } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;
import { useHeaderActions } from '@hooks/useHeaderActions';
import type { Transaction } from '@ledova/shared';
import { Panel } from '@components/Panel';
import { useTransactions } from './useTransactions';
import { TransactionFilterModal } from './components/TransactionFilterModal';
import { TransactionListItem } from './components/TransactionListItem';
import { TransactionDetailModal } from './components/TransactionDetailModal';

export const TransactionsPage = () => {
  const {
    transactions,
    wallets,
    isLoading,
    isLoadingMore,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage,
    applyFilters,
    updateFilters,
    clearFilters,
    loadMore,
  } = useTransactions();

  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showFiltersModal, setShowFiltersModal] = useState(false);

  const { setActions } = useHeaderActions();

  useEffect(() => {
    setActions(
      <button
        type="button"
        onClick={() => setShowFiltersModal(true)}
        className={`p-1.5 rounded-lg transition-colors ${
          hasActiveFilters
            ? 'text-brand-mid hover:text-brand-light'
            : 'text-text-muted hover:text-text-primary hover:bg-surface-tertiary'
        }`}
        title="Filter transactions"
      >
        <FunnelIcon size={ICON_SM} weight={hasActiveFilters ? 'fill' : 'regular'} />
      </button>,
    );
    return () => setActions(null);
  }, [setActions, hasActiveFilters]);

  const handleTransactionClick = (transaction: Transaction) => {
    setSelectedTransaction(transaction);
    setShowDetailModal(true);
  };

  const handleCloseDetailModal = () => {
    setShowDetailModal(false);
    setSelectedTransaction(null);
  };

  const handleFilterChange = (field: string, value: string) => {
    updateFilters({ ...filters, [field]: value || undefined });
  };

  const handleApplyFilters = () => {
    applyFilters();
    setShowFiltersModal(false);
  };

  const handleClearFilters = () => {
    clearFilters();
    setShowFiltersModal(false);
  };

  const handleViewOnExplorer = () => {
    if (selectedTransaction?.txHash && selectedTransaction?.chain) {
      const url = getBlockExplorerTxUrl(selectedTransaction.chain, selectedTransaction.txHash);
      window.open(url, '_blank');
    }
  };

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel title="Transactions" icon={<PackageIcon size={ICON_MD} />}>
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-mid"></div>
              <p className="text-sm text-text-muted">Loading transactions...</p>
            </div>
          ) : transactions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <PackageIcon size={ICON_XXL} className="text-text-subtle" />
              <p className="text-sm text-text-muted">No transactions found</p>
              <p className="text-xs text-text-subtle text-center max-w-[250px]">
                {hasActiveFilters
                  ? 'Try adjusting your filters to see more results'
                  : 'Transactions will appear here once confirmed on the blockchain'}
              </p>
            </div>
          ) : (
            <div className="space-y-0">
              <div className="divide-y divide-border-subtle max-h-[500px] overflow-y-auto">
                {transactions.map((tx) => (
                  <TransactionListItem key={tx.uuid} transaction={tx} onClick={handleTransactionClick} />
                ))}
              </div>

              <div className="flex items-center justify-end pt-4 mt-4 border-t border-border-subtle text-xs text-text-subtle">
                <span className="inline-flex items-center gap-1">
                  {totalCount > 0
                    ? `${transactions.length} of ${totalCount} transaction${totalCount !== 1 ? 's' : ''}`
                    : `${transactions.length} transaction${transactions.length !== 1 ? 's' : ''}`}
                  {hasNextPage && (
                    <>
                      <span>&middot;</span>
                      <button
                        type="button"
                        onClick={loadMore}
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
          )}
        </Panel>
      </div>

      <TransactionFilterModal
        isOpen={showFiltersModal}
        filters={filters}
        wallets={wallets}
        onClose={() => setShowFiltersModal(false)}
        onFilterChange={handleFilterChange}
        onApply={handleApplyFilters}
        onClear={handleClearFilters}
        updateFilters={updateFilters}
      />

      <TransactionDetailModal
        isOpen={showDetailModal}
        transaction={selectedTransaction}
        onClose={handleCloseDetailModal}
        onViewExplorer={handleViewOnExplorer}
      />
    </main>
  );
};

export default TransactionsPage;
