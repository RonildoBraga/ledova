import { HardDriveIcon, CloudIcon, ClockIcon } from '@phosphor-icons/react';
import { formatCryptoBalance, formatWalletAddressShort, formatSyncAge } from '@ledova/shared-utils';
import { useCurrency } from '@hooks/useCurrency';
import { WALLET_TYPE, DESIGN_TOKENS } from '@ledova/shared-constants';
import type { Wallet } from '@ledova/shared-types';
import { WalletBadge } from './WalletBadge';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;

interface WalletItemProps {
  wallet: Wallet;
  isSelected: boolean;
  onSelect: () => void;
  onEdit?: () => void;
}

export function WalletItem({ wallet, isSelected, onSelect, onEdit }: WalletItemProps) {
  const { formatDisplayCurrency } = useCurrency();
  const secondaryLabel = wallet.name || formatWalletAddressShort(wallet.address);
  const isHardware = wallet.walletType === WALLET_TYPE.HARDWARE;
  const TypeIcon = isHardware ? HardDriveIcon : CloudIcon;
  const syncAge = formatSyncAge(wallet.lastSyncedAt);

  return (
    <button
      type="button"
      onClick={onSelect}
      onDoubleClick={onEdit}
      aria-pressed={isSelected}
      className={`w-full flex items-center gap-3 py-2.5 rounded-lg transition-colors text-left ${
        isSelected ? 'bg-brand-mid/10 hover:bg-brand-mid/15' : 'hover:bg-surface-tertiary'
      }`}
    >
      <WalletBadge verificationStatus={wallet.verificationStatus} />
      <span className="text-xs text-text-muted truncate">{secondaryLabel}</span>
      <span className="inline-flex items-center justify-center p-1">
        <TypeIcon size={ICON_XS} weight="bold" className="text-text-secondary" />
      </span>
      <div className="flex-1" />
      {syncAge && (
        <span
          className="inline-flex items-center gap-0.5 text-xs text-text-subtle flex-shrink-0"
          title={`Last synced: ${wallet.lastSyncedAt}`}
        >
          <ClockIcon size={ICON_XS} />
          {syncAge}
        </span>
      )}
      <span className="text-xs text-text-muted flex-shrink-0">
        {formatCryptoBalance(wallet.nativeBalance, '').trimEnd()}
      </span>
      <span className="text-xs text-text-muted flex-shrink-0">
        {formatDisplayCurrency(parseFloat(wallet.marketValue) || 0)}
      </span>
    </button>
  );
}
