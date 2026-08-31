import { useEffect, useState } from 'react';
import { QrCodeIcon, CheckIcon, WalletIcon, HardDrivesIcon } from '@phosphor-icons/react';
import { getBlockchainDisplayName, isEthereumChain, isBitcoinChain, DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;
import { fetchBatchBalances } from '@ledova/shared-services';
import type { CreateWallet, DerivedAddress, HardwareWalletImport } from '@ledova/shared-types';
import { Modal } from '@components/Modal';
import apiClient from '@services/apiClient';
import { useWalletForm } from '../hooks/useWalletForm';
import { extractFromKeystoneQR } from '@utils/keystone/bcurDecoder';

interface AddWalletModalProps {
  isOpen: boolean;
  isLoading: boolean;
  userAccountUuid: string | undefined;
  onClose: () => void;
  onSubmit: (data: CreateWallet) => void;
  onBatchSubmit: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
}

export function AddWalletModal({
  isOpen,
  isLoading,
  userAccountUuid,
  onClose,
  onSubmit,
  onBatchSubmit,
}: AddWalletModalProps) {
  const form = useWalletForm({
    userAccountUuid,
    onSubmit,
    onBatchSubmit,
  });

  useEffect(() => {
    if (isOpen) {
      form.reset();
    }
  }, [isOpen]);

  const handleClose = () => {
    form.stopScanner();
    form.reset();
    onClose();
  };

  if (form.isSelectingAddresses && form.scannedURString) {
    return (
      <Modal isOpen={isOpen} onClose={handleClose} showFooter={false}>
        <AccountSelector
          urString={form.scannedURString}
          onSelectAccounts={form.handleAddressSelection}
          onCancel={form.handleBackToInput}
          isLoading={isLoading}
        />
      </Modal>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      showFooter={!form.showScanner}
      confirmLabel={isLoading ? 'Adding...' : 'Add Wallet'}
      confirmLoading={isLoading}
      confirmDisabled={isLoading || !form.address.trim()}
      onConfirm={form.handleSubmit}
    >
      <div className="space-y-4">
        <div className="flex flex-col items-center gap-2 pt-2 pb-4">
          <WalletIcon size={ICON_XXL} weight="light" className="text-info-light" />
          <p className="text-sm text-text-muted text-center">
            {form.showScanner ? 'Scan your wallet QR code' : 'Enter wallet details or scan a QR code'}
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs text-text-muted">Wallet Address</label>
            <button
              type="button"
              onClick={form.toggleScanner}
              disabled={isLoading}
              className="flex items-center gap-1 text-sm text-brand-mid hover:text-brand-light transition-colors"
            >
              <QrCodeIcon size={ICON_SM} />
              <span>{form.showScanner ? 'Hide Scanner' : 'Scan QR'}</span>
            </button>
          </div>

          {form.showScanner ? (
            <div className="space-y-3">
              <div className="relative overflow-hidden rounded-lg bg-black mx-auto" style={{ width: 280, height: 280 }}>
                <div id="wallet-qr-scanner" className="w-full h-full" />
              </div>

              {form.scanProgress && (
                <div className="flex items-center justify-center">
                  <span className="text-xs bg-brand-mid text-white px-3 py-1 rounded-full">
                    Scanning: {form.scanProgress.received}/{form.scanProgress.total > 0 ? form.scanProgress.total : '?'}{' '}
                    parts
                  </span>
                </div>
              )}

              {form.scannerError && (
                <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                  <p className="text-sm text-error-light text-center">{form.scannerError}</p>
                </div>
              )}
            </div>
          ) : (
            <>
              <input
                type="text"
                value={form.address}
                onChange={(e) => form.handleAddressChange(e.target.value)}
                className={`w-full bg-surface-tertiary border rounded-lg px-3 py-2.5 text-sm text-text-primary font-mono focus:outline-none focus:ring-2 focus:ring-brand-mid ${
                  form.errors.address ? 'border-error-light' : 'border-border'
                }`}
                placeholder="0x... or tb1..."
                disabled={isLoading}
              />
              {form.errors.address && <p className="text-xs text-error-light">{form.errors.address}</p>}
            </>
          )}
        </div>

        {!form.showScanner && (
          <div className="space-y-2">
            <label className="text-xs text-text-muted">Wallet Name (Optional)</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => form.setName(e.target.value)}
              className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
              placeholder="e.g., Savings, Trading, Cold Storage"
              disabled={isLoading}
              maxLength={100}
            />
          </div>
        )}

        {!userAccountUuid && !form.showScanner && (
          <p className="text-xs text-error-light">Select a portfolio first to add wallets.</p>
        )}
      </div>
    </Modal>
  );
}

interface AccountSelectorProps {
  urString: string;
  onSelectAccounts: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
  onCancel: () => void;
  isLoading: boolean;
}

function AccountSelector({ urString, onSelectAccounts, onCancel, isLoading: isImporting }: AccountSelectorProps) {
  const [selectedAddresses, setSelectedAddresses] = useState<Set<string>>(new Set());
  const [addresses, setAddresses] = useState<DerivedAddress[]>([]);
  const [importData, setImportData] = useState<HardwareWalletImport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [balances, setBalances] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    setIsLoading(true);
    try {
      const result = extractFromKeystoneQR(urString);
      if (result) {
        setAddresses(result.addresses);
        setImportData(result);
        setSelectedAddresses(new Set(result.addresses.map((a) => a.address)));
        fetchBalances(result.addresses);
      }
    } catch (error) {
      console.error('Failed to extract QR data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [urString]);

  const fetchBalances = async (addressList: DerivedAddress[]) => {
    const ethAddresses = addressList.filter((a) => isEthereumChain(a.networkType));
    const btcAddresses = addressList.filter((a) => isBitcoinChain(a.networkType));

    const newBalances = new Map<string, string>();

    if (ethAddresses.length > 0) {
      try {
        const ethAddrs = ethAddresses.map((a) => a.address);
        const ethResponse = await fetchBatchBalances(apiClient, ethAddrs, 'ETH');
        ethAddresses.forEach((addr) => {
          const balance = ethResponse.balances[addr.address] || '0';
          newBalances.set(addr.address, `${balance} ETH`);
        });
      } catch {
        ethAddresses.forEach((addr) => newBalances.set(addr.address, '0 ETH'));
      }
    }

    if (btcAddresses.length > 0) {
      try {
        const btcAddrs = btcAddresses.map((a) => a.address);
        const btcResponse = await fetchBatchBalances(apiClient, btcAddrs, 'BTC');
        btcAddresses.forEach((addr) => {
          const balance = btcResponse.balances[addr.address] || '0';
          newBalances.set(addr.address, `${balance} BTC`);
        });
      } catch {
        btcAddresses.forEach((addr) => newBalances.set(addr.address, '0 BTC'));
      }
    }

    setBalances(newBalances);
  };

  const toggleSelection = (address: string) => {
    const newSelected = new Set(selectedAddresses);
    if (newSelected.has(address)) {
      newSelected.delete(address);
    } else {
      newSelected.add(address);
    }
    setSelectedAddresses(newSelected);
  };

  const handleImport = () => {
    if (!importData) return;
    const selected = addresses.filter((addr) => selectedAddresses.has(addr.address));
    onSelectAccounts(selected, importData);
  };

  if (isLoading) {
    return (
      <div className="py-12 flex flex-col items-center justify-center gap-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-mid"></div>
        <p className="text-sm text-text-muted">Loading accounts...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center gap-2 pt-2 pb-4">
        <HardDrivesIcon size={ICON_XXL} weight="light" className="text-info-light" />
        <p className="text-sm text-text-muted text-center">Review the accounts to import</p>
      </div>

      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {addresses.map((derivedAddress) => {
          const isSelected = selectedAddresses.has(derivedAddress.address);
          const balance = balances.get(derivedAddress.address) || 'Loading...';
          const networkName = getBlockchainDisplayName(derivedAddress.networkType);

          return (
            <button
              key={derivedAddress.address}
              type="button"
              onClick={() => toggleSelection(derivedAddress.address)}
              className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-colors text-left ${
                isSelected
                  ? 'border-brand-mid bg-brand-mid/5'
                  : 'border-border bg-surface-tertiary hover:bg-surface-raised'
              }`}
            >
              <div
                className={`flex-shrink-0 w-5 h-5 rounded border-2 flex items-center justify-center ${
                  isSelected ? 'bg-brand-mid border-brand-mid' : 'border-border-strong'
                }`}
              >
                {isSelected && <CheckIcon size={ICON_XS} weight="bold" className="text-white" />}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-text-primary">{networkName}</span>
                  <span className="text-sm font-semibold text-text-primary">{balance}</span>
                </div>
                <p className="text-xs font-mono text-text-muted truncate">
                  {derivedAddress.address.slice(0, 10)}...{derivedAddress.address.slice(-8)}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 px-4 py-2.5 border border-border rounded-lg text-sm font-medium text-text-secondary hover:bg-surface-tertiary transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleImport}
          disabled={selectedAddresses.size === 0 || isImporting}
          className="flex-1 px-4 py-2.5 bg-brand-mid text-white rounded-lg text-sm font-medium hover:bg-brand transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isImporting
            ? 'Importing...'
            : `Import ${selectedAddresses.size} Wallet${selectedAddresses.size !== 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  );
}
