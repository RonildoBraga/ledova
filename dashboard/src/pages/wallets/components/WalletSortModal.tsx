import { useEffect, useState } from 'react';
import {
  FunnelIcon,
  ListBulletsIcon,
  ShieldCheckIcon,
  SortAscendingIcon,
  TagIcon,
  CurrencyCircleDollarIcon,
  CoinsIcon,
  CheckIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { Modal } from '@components/Modal';
import type { WalletSortOption } from '../hooks/useWalletSort';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

interface WalletSortModalProps {
  isOpen: boolean;
  selectedSort: WalletSortOption;
  onClose: () => void;
  onApply: (sort: WalletSortOption) => void;
}

const sortOptions: Array<{ id: WalletSortOption; label: string; icon: React.ReactNode; description: string }> = [
  {
    id: 'default',
    label: 'Default',
    icon: <ListBulletsIcon size={ICON_SM} className="text-text-primary" />,
    description: 'Hardware wallets first',
  },
  {
    id: 'verified',
    label: 'Verified First',
    icon: <ShieldCheckIcon size={ICON_SM} className="text-success-light" />,
    description: 'Show verified wallets first',
  },
  {
    id: 'name',
    label: 'Alphabetical',
    icon: <SortAscendingIcon size={ICON_SM} className="text-text-primary" />,
    description: 'Sort by name (A-Z)',
  },
  {
    id: 'namedFirst',
    label: 'Named First',
    icon: <TagIcon size={ICON_SM} className="text-text-primary" />,
    description: 'Wallets with names before unnamed',
  },
  {
    id: 'highestValue',
    label: 'Highest Value',
    icon: <CurrencyCircleDollarIcon size={ICON_SM} className="text-text-primary" />,
    description: 'Sort by market value (highest first)',
  },
  {
    id: 'highestBalance',
    label: 'Most Coins',
    icon: <CoinsIcon size={ICON_SM} className="text-text-primary" />,
    description: 'Sort by native balance (highest first)',
  },
];

export function WalletSortModal({ isOpen, selectedSort, onClose, onApply }: WalletSortModalProps) {
  const [localSort, setLocalSort] = useState<WalletSortOption>(selectedSort);

  useEffect(() => {
    if (isOpen) {
      setLocalSort(selectedSort);
    }
  }, [isOpen, selectedSort]);

  const handleApply = () => {
    onApply(localSort);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      showFooter
      cancelLabel="Close"
      confirmLabel="Apply"
      onConfirm={handleApply}
      size="sm"
    >
      {/* Header */}
      <div className="flex flex-col items-center pb-3">
        <FunnelIcon size={ICON_LG} className="text-brand-mid mb-1" />
        <h3 className="text-lg font-semibold text-text-primary">Sort Wallets</h3>
      </div>

      {/* Sort Options */}
      <p className="text-xs font-medium text-text-subtle uppercase tracking-wide mb-2">Sort By</p>
      <div className="space-y-1.5">
        {sortOptions.map((option) => {
          const isSelected = localSort === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setLocalSort(option.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg border-2 transition-colors ${
                isSelected
                  ? 'border-brand-mid bg-surface-disabled'
                  : 'border-transparent bg-surface-tertiary hover:bg-surface-disabled'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-surface-raised flex items-center justify-center flex-shrink-0">
                  {option.icon}
                </div>
                <div className="text-left">
                  <p className={`text-sm font-medium ${isSelected ? 'text-brand-light' : 'text-text-primary'}`}>
                    {option.label}
                  </p>
                  <p className="text-[11px] text-text-muted">{option.description}</p>
                </div>
              </div>
              {isSelected && <CheckIcon size={ICON_SM} className="text-brand-mid flex-shrink-0" weight="bold" />}
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
