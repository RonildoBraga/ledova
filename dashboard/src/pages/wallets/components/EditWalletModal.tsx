import { useEffect, useState } from 'react';
import {
  ShieldCheckIcon,
  ShieldIcon,
  HardDriveIcon,
  CloudIcon,
  CurrencyEthIcon,
  CurrencyBtcIcon,
} from '@phosphor-icons/react';
import { formatCryptoBalance, formatWalletAddressMedium, formatDate } from '@ledova/shared-utils';
import { useCurrency } from '@hooks/useCurrency';
import {
  getChainShortCode,
  isBitcoinChain,
  WALLET_VERIFICATION_STATUS,
  WALLET_TYPE,
  DESIGN_TOKENS,
} from '@ledova/shared-constants';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
import type { Wallet as WalletType } from '@ledova/shared-types';
import { Modal } from '@components/Modal';

interface EditWalletModalProps {
  wallet: WalletType | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (uuid: string, name: string) => void;
  isUpdating: boolean;
}

export function EditWalletModal({ wallet, isOpen, onClose, onSave, isUpdating }: EditWalletModalProps) {
  const { formatDisplayCurrency } = useCurrency();
  const [name, setName] = useState('');

  useEffect(() => {
    if (wallet) {
      setName(wallet.name || '');
    }
  }, [wallet]);

  if (!wallet) return null;

  const chainShortName = getChainShortCode(wallet.chain);
  const marketValue = parseFloat(wallet.nativeMarketValue) || 0;
  const isHardware = !wallet.walletType || wallet.walletType === WALLET_TYPE.HARDWARE;
  const isVerified = wallet.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;
  const isBtc = isBitcoinChain(chainShortName);
  const ChainIcon = isBtc ? CurrencyBtcIcon : CurrencyEthIcon;

  const handleSave = () => {
    onSave(wallet.uuid, name.trim());
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Wallet"
      showFooter
      confirmLabel={isUpdating ? 'Saving...' : 'Save'}
      confirmLoading={isUpdating}
      onConfirm={handleSave}
    >
      <div className="space-y-5">
        {/* 1. Hero: Chain icon + Market Value */}
        <div className="flex flex-col items-center gap-2 py-2">
          <ChainIcon size={48} className="text-info-light" weight="light" />
          <span className="text-xl font-semibold text-text-primary">{formatDisplayCurrency(marketValue)}</span>
        </div>

        {/* 2-6. Detail rows (unified order) */}
        <div className="space-y-0">
          {/* 2. Address */}
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Address</span>
            <span className="text-sm font-medium text-text-primary">{formatWalletAddressMedium(wallet.address)}</span>
          </div>

          {/* 3. Balance */}
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Balance</span>
            <span className="text-sm font-medium text-text-primary">
              {formatCryptoBalance(wallet.nativeBalance, chainShortName)}
            </span>
          </div>

          {/* 4. Type */}
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Type</span>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-text-primary">{isHardware ? 'Hardware' : 'Software'}</span>
              <span className="inline-flex items-center justify-center rounded bg-surface-tertiary p-1">
                {isHardware ? (
                  <HardDriveIcon size={ICON_SM} weight="bold" className="text-text-secondary" />
                ) : (
                  <CloudIcon size={ICON_SM} weight="bold" className="text-text-secondary" />
                )}
              </span>
            </div>
          </div>

          {/* 5. Last Sync */}
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Last Sync</span>
            <span className="text-sm font-medium text-text-primary">{formatDate(wallet.lastSyncedAt)}</span>
          </div>

          {/* 6. Verification */}
          <div className="flex items-center justify-between py-2.5">
            <span className="text-sm text-text-muted">Verification</span>
            <div className="flex items-center gap-1.5">
              <span className={`text-sm font-medium ${isVerified ? 'text-success-light' : 'text-warning-light'}`}>
                {isVerified ? 'Verified' : 'Pending'}
              </span>
              {isVerified ? (
                <ShieldCheckIcon size={ICON_SM} className="text-success-light" />
              ) : (
                <ShieldIcon size={ICON_SM} className="text-warning-light" />
              )}
            </div>
          </div>
        </div>

        {/* 7. Name (editable, at bottom) */}
        <div className="space-y-2 pt-2">
          <label className="text-sm font-medium text-text-primary">Wallet Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
            placeholder="Enter wallet name (optional)"
          />
          <p className="text-xs text-text-muted">Give your wallet a memorable name</p>
        </div>
      </div>
    </Modal>
  );
}
