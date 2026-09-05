import { WalletIcon, ArrowsClockwiseIcon, PaperPlaneTiltIcon } from '@phosphor-icons/react';
import { useQuery } from '@tanstack/react-query';
import {
  BLOCKCHAIN,
  DESIGN_TOKENS,
  getWallets,
  formatCryptoBalance,
  formatWalletAddressShort,
  formatSyncAge,
  WALLET_TYPE,
} from '@ledova/shared';
import { useCurrency } from '@hooks/useCurrency';
import type { Wallet } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { WalletBadge } from '@components/Wallet';
import apiClient from '@services/apiClient';
import { HardDriveIcon, CloudIcon, ClockIcon } from '@phosphor-icons/react';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;

interface WalletSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectWallet: (wallet: Wallet) => void;
  userAccountUuid?: string;
}

export function WalletSelectionModal({ isOpen, onClose, onSelectWallet, userAccountUuid }: WalletSelectionModalProps) {
  const { formatDisplayCurrency } = useCurrency();
  const walletsQuery = useQuery({
    queryKey: ['wallets', userAccountUuid, { verification_status: 'VERIFIED', order_by: 'wallet_type' }],
    queryFn: () =>
      getWallets(apiClient, {
        user_account: userAccountUuid!,
        verification_status: 'VERIFIED',
        order_by: 'wallet_type',
      }),
    enabled: !!userAccountUuid && isOpen,
  });

  const wallets = walletsQuery.data?.data.results || [];
  const ethWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.ETHEREUM);
  const btcWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.BITCOIN);
  const baseWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.BASE);

  const renderWallet = (wallet: Wallet) => {
    const walletLabel = wallet.name || formatWalletAddressShort(wallet.address);
    const isHardware = wallet.walletType === WALLET_TYPE.HARDWARE;
    const TypeIcon = isHardware ? HardDriveIcon : CloudIcon;
    const syncAge = formatSyncAge(wallet.lastSyncedAt);
    const marketValue = parseFloat(wallet.marketValue) || 0;

    return (
      <button
        key={wallet.uuid}
        type="button"
        onClick={() => onSelectWallet(wallet)}
        className="w-full flex items-center gap-3 py-2.5 rounded-lg hover:bg-surface-tertiary transition-colors text-left"
      >
        <WalletBadge verificationStatus={wallet.verificationStatus} />
        <span className="text-xs text-text-muted truncate">{walletLabel}</span>
        <span className="inline-flex items-center justify-center p-1">
          <TypeIcon size={ICON_XS} weight="bold" className="text-text-secondary" />
        </span>
        <div className="flex-1" />
        {syncAge && (
          <span className="inline-flex items-center gap-0.5 text-xs text-text-subtle flex-shrink-0">
            <ClockIcon size={ICON_XS} />
            {syncAge}
          </span>
        )}
        <span className="text-xs text-text-muted flex-shrink-0">
          {formatCryptoBalance(wallet.nativeBalance, '').trimEnd()}
        </span>
        <span className="text-xs text-text-muted flex-shrink-0">{formatDisplayCurrency(marketValue)}</span>
      </button>
    );
  };

  const renderContent = () => {
    if (walletsQuery.isLoading) {
      return (
        <div className="flex items-center justify-center py-8">
          <ArrowsClockwiseIcon size={ICON_LG} className="animate-spin text-text-muted" />
          <span className="ml-2 text-sm text-text-muted">Loading wallets...</span>
        </div>
      );
    }

    if (wallets.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <WalletIcon size={ICON_XXL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">No verified wallets found</p>
          <p className="text-xs text-text-subtle">Create and verify a wallet to send crypto</p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        {ethWallets.length > 0 && (
          <div className="space-y-1">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">Ethereum</span>
            {ethWallets.map(renderWallet)}
          </div>
        )}
        {btcWallets.length > 0 && (
          <div className="space-y-1">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">Bitcoin</span>
            {btcWallets.map(renderWallet)}
          </div>
        )}
        {baseWallets.length > 0 && (
          <div className="space-y-1">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">Base</span>
            {baseWallets.map(renderWallet)}
          </div>
        )}
      </div>
    );
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} showFooter showCancelButton onCancel={onClose}>
      <div className="flex flex-col items-center gap-2 pt-2 pb-6">
        <PaperPlaneTiltIcon size={ICON_XXL} className="text-info-light" weight="light" />
        <p className="text-sm font-semibold text-text-muted">Select your wallet</p>
      </div>
      {renderContent()}
    </Modal>
  );
}
