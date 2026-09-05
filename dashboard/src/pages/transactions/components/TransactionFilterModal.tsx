import { CurrencyEthIcon, CurrencyBtcIcon, FunnelIcon } from '@phosphor-icons/react';
import { BLOCKCHAIN, DESIGN_TOKENS } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';
import { Modal } from '@components/Modal';
import type { TransactionFilters } from '../useTransactions';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

interface TransactionFilterModalProps {
  isOpen: boolean;
  filters: TransactionFilters;
  wallets: Wallet[];
  onClose: () => void;
  onFilterChange: (field: string, value: string) => void;
  onApply: () => void;
  onClear: () => void;
  updateFilters: (filters: TransactionFilters) => void;
}

const directionOptions = [
  { value: '', label: 'All' },
  { value: 'incoming', label: 'In' },
  { value: 'outgoing', label: 'Out' },
];

const chainOptions = [
  { value: '', label: 'All', icon: null },
  { value: BLOCKCHAIN.ETHEREUM, label: 'ETH', icon: <CurrencyEthIcon size={ICON_SM} /> },
  { value: BLOCKCHAIN.BITCOIN, label: 'BTC', icon: <CurrencyBtcIcon size={ICON_SM} /> },
  { value: BLOCKCHAIN.BASE, label: 'BASE', icon: <CurrencyEthIcon size={ICON_SM} /> },
];

export function TransactionFilterModal({
  isOpen,
  filters,
  wallets,
  onClose,
  onFilterChange,
  onApply,
  onClear,
  updateFilters,
}: TransactionFilterModalProps) {
  const ethWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.ETHEREUM);
  const btcWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.BITCOIN);
  const baseWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.BASE);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      showFooter
      cancelLabel="Clear"
      confirmLabel="Apply"
      onConfirm={onApply}
      onCancel={onClear}
      size="sm"
    >
      <div className="flex flex-col items-center pb-3">
        <FunnelIcon size={ICON_LG} className="text-brand-mid mb-1" />
        <h3 className="text-lg font-semibold text-text-primary">Filter Transactions</h3>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Direction</p>
          <div className="grid grid-cols-3 gap-2">
            {directionOptions.map((option) => {
              const isSelected = (filters.direction || '') === option.value;
              return (
                <button
                  key={option.value || 'all'}
                  type="button"
                  onClick={() => onFilterChange('direction', option.value)}
                  className={`px-3 py-2 text-xs font-medium rounded-lg border-2 transition-colors ${
                    isSelected
                      ? 'border-brand-mid bg-surface-disabled text-brand-light'
                      : 'border-transparent bg-surface-tertiary text-text-secondary hover:bg-surface-disabled'
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Chain</p>
          <div className="grid grid-cols-4 gap-2">
            {chainOptions.map((option) => {
              const isSelected = (filters.chain || '') === option.value;
              return (
                <button
                  key={option.value || 'all'}
                  type="button"
                  onClick={() => onFilterChange('chain', option.value)}
                  className={`flex items-center justify-center gap-1 px-3 py-2 text-xs font-medium rounded-lg border-2 transition-colors ${
                    isSelected
                      ? 'border-brand-mid bg-surface-disabled text-brand-light'
                      : 'border-transparent bg-surface-tertiary text-text-secondary hover:bg-surface-disabled'
                  }`}
                >
                  {option.icon}
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Wallet</p>
          <select
            value={(filters.wallet as string) || ''}
            onChange={(e) => onFilterChange('wallet', e.target.value)}
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
          >
            <option value="">All wallets</option>
            {ethWallets.length > 0 && (
              <optgroup label="Ethereum">
                {ethWallets.map((wallet) => (
                  <option key={wallet.uuid} value={wallet.uuid}>
                    {wallet.name || `${wallet.address.slice(0, 8)}...${wallet.address.slice(-6)}`}
                  </option>
                ))}
              </optgroup>
            )}
            {btcWallets.length > 0 && (
              <optgroup label="Bitcoin">
                {btcWallets.map((wallet) => (
                  <option key={wallet.uuid} value={wallet.uuid}>
                    {wallet.name || `${wallet.address.slice(0, 8)}...${wallet.address.slice(-6)}`}
                  </option>
                ))}
              </optgroup>
            )}
            {baseWallets.length > 0 && (
              <optgroup label="Base">
                {baseWallets.map((wallet) => (
                  <option key={wallet.uuid} value={wallet.uuid}>
                    {wallet.name || `${wallet.address.slice(0, 8)}...${wallet.address.slice(-6)}`}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Date Range</p>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="date"
              value={(filters.start_date as string) || ''}
              onChange={(e) => onFilterChange('start_date', e.target.value)}
              className="w-full bg-surface-tertiary border border-border rounded-lg px-2 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
              placeholder="Start"
            />
            <input
              type="date"
              value={(filters.end_date as string) || ''}
              onChange={(e) => onFilterChange('end_date', e.target.value)}
              className="w-full bg-surface-tertiary border border-border rounded-lg px-2 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
              placeholder="End"
            />
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Amount Range</p>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="number"
              value={filters.min_amount ?? ''}
              onChange={(e) =>
                updateFilters({ ...filters, min_amount: e.target.value ? Number(e.target.value) : undefined })
              }
              className="w-full bg-surface-tertiary border border-border rounded-lg px-2 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
              placeholder="Min"
              min="0"
            />
            <input
              type="number"
              value={filters.max_amount ?? ''}
              onChange={(e) =>
                updateFilters({ ...filters, max_amount: e.target.value ? Number(e.target.value) : undefined })
              }
              className="w-full bg-surface-tertiary border border-border rounded-lg px-2 py-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
              placeholder="Max"
              min="0"
            />
          </div>
        </div>
      </div>
    </Modal>
  );
}
