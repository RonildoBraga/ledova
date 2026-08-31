import { formatWalletAddressShort } from '@ledova/shared-utils';
import type { Wallet } from '@ledova/shared-types';
import { Modal } from '@components/Modal';

interface DeleteWalletModalProps {
  isOpen: boolean;
  wallet: Wallet | null;
  onConfirm: () => void;
  onClose: () => void;
}

export function DeleteWalletModal({ isOpen, wallet, onConfirm, onClose }: DeleteWalletModalProps) {
  if (!wallet) return null;

  const walletDisplayName = wallet.name || formatWalletAddressShort(wallet.address);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Delete Wallet"
      showFooter
      confirmLabel="Delete"
      onConfirm={onConfirm}
    >
      <div className="text-center py-4">
        <p className="text-sm text-text-secondary mb-2">Are you sure you want to delete this wallet?</p>
        <p className="text-sm font-medium text-text-primary">{walletDisplayName}</p>
        <p className="text-xs text-text-muted mt-2">This action cannot be undone.</p>
      </div>
    </Modal>
  );
}
