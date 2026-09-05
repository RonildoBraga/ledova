import { useEffect, useState } from 'react';
import { getBlockchainDisplayName } from '@ledova/shared';
import type { Wallet, DerivedAddress } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { deriveAddressFromParentKey } from '@utils/keystone/bcurDecoder';

interface DeriveAddressModalProps {
  isOpen: boolean;
  wallet: Wallet | null;
  onConfirm: (derivedAddress: DerivedAddress) => void;
  onClose: () => void;
  isCreating?: boolean;
}

export function DeriveAddressModal({
  isOpen,
  wallet,
  onConfirm,
  onClose,
  isCreating = false,
}: DeriveAddressModalProps) {
  const [derivedAddress, setDerivedAddress] = useState<DerivedAddress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && wallet?.parentPublicKey && wallet?.parentChainCode && wallet?.parentDerivationPath) {
      try {
        const nextIndex = (wallet.addressIndex ?? 0) + 1;
        const newAddress = deriveAddressFromParentKey(
          wallet.parentPublicKey,
          wallet.parentChainCode,
          wallet.parentDerivationPath,
          nextIndex,
        );
        setDerivedAddress(newAddress);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to derive address');
        setDerivedAddress(null);
      }
    } else {
      setDerivedAddress(null);
      setError(null);
    }
  }, [isOpen, wallet]);

  const handleConfirm = () => {
    if (derivedAddress) {
      onConfirm(derivedAddress);
    }
  };

  if (!wallet) return null;

  const networkName = getBlockchainDisplayName(derivedAddress?.networkType || 'ETH');

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Derive New Address"
      showFooter
      confirmLabel={isCreating ? 'Adding...' : 'Add Address'}
      confirmDisabled={!derivedAddress || isCreating}
      confirmLoading={isCreating}
      onConfirm={handleConfirm}
    >
      <div className="space-y-5">
        <div className="text-center">
          <p className="text-sm text-text-muted">Add another address from your hardware wallet</p>
        </div>

        {error ? (
          <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
            <p className="text-sm text-error-light text-center">{error}</p>
          </div>
        ) : derivedAddress ? (
          <div className="space-y-0">
            <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
              <span className="text-sm text-text-muted">Network</span>
              <span className="text-sm font-medium text-text-primary">{networkName}</span>
            </div>

            <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
              <span className="text-sm text-text-muted">Address Index</span>
              <span className="text-sm font-medium text-text-primary">{derivedAddress.addressIndex}</span>
            </div>

            <div className="py-2.5 border-b border-border-subtle">
              <span className="text-sm text-text-muted">New Address</span>
              <p className="text-sm font-mono text-text-primary mt-1 break-all">{derivedAddress.address}</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand-mid"></div>
            <p className="text-sm text-text-muted">Deriving address...</p>
          </div>
        )}
      </div>
    </Modal>
  );
}
