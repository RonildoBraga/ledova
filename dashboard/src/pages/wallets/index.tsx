import { useCallback, useEffect, useState } from 'react';
import { CurrencyBtcIcon, CurrencyEthIcon, FunnelIcon } from '@phosphor-icons/react';
import { BLOCKCHAIN, WALLET_VERIFICATION_STATUS, DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
import { useHeaderActions } from '@hooks/useHeaderActions';
import type { Wallet as WalletType, DerivedAddress, HardwareWalletImport } from '@ledova/shared-types';
import { formatCryptoBalance } from '@ledova/shared-utils';
import { useCurrency } from '@hooks/useCurrency';
import { Panel } from '@components/Panel';
import { WalletList, ChainEmptyState } from '@components/Wallet';
import { useWallets } from './hooks/useWallets';
import { useWalletSort } from './hooks/useWalletSort';
import { WalletActionBar } from './components/WalletActionBar';
import { WalletSortModal } from './components/WalletSortModal';
import { EditWalletModal } from './components/EditWalletModal';
import { DeleteWalletModal } from './components/DeleteWalletModal';
import { WalletVerificationModal } from './components/WalletVerificationModal';
import { DeriveAddressModal } from './components/DeriveAddressModal';
import { AddWalletModal } from './components/AddWalletModal';

export function WalletsPage() {
  const { formatDisplayCurrency } = useCurrency();
  const {
    wallets,
    userAccountUuid,
    handleCreateWallet,
    handleBatchCreateWallets,
    handleUpdateWalletName,
    handleDeleteWallet,
    handleSyncWallet,
    derivingWallet,
    openDeriveModal,
    closeDeriveModal,
    handleDeriveAddress,
    canDeriveAddress,
    isLoading,
    isCreating,
    isUpdating,
    isSyncing,
  } = useWallets();

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingWallet, setEditingWallet] = useState<WalletType | null>(null);
  const [deletingWallet, setDeletingWallet] = useState<WalletType | null>(null);
  const [verifyingWallet, setVerifyingWallet] = useState<WalletType | null>(null);
  const [selectedWalletUuid, setSelectedWalletUuid] = useState<string | null>(null);

  const { sortedWallets, sortOption, isFiltered, showSortModal, setShowSortModal, handleApply } =
    useWalletSort(wallets);

  const { setActions } = useHeaderActions();

  useEffect(() => {
    setActions(
      <button
        type="button"
        onClick={() => setShowSortModal(true)}
        className={`p-1.5 rounded-lg transition-colors ${
          isFiltered
            ? 'text-brand-mid hover:text-brand-light'
            : 'text-text-muted hover:text-text-primary hover:bg-surface-tertiary'
        }`}
        title="Filter wallets"
      >
        <FunnelIcon size={ICON_SM} weight={isFiltered ? 'fill' : 'regular'} />
      </button>,
    );
    return () => setActions(null);
  }, [setActions, setShowSortModal, isFiltered]);

  const ethWallets = sortedWallets.filter((w) => w.chain === BLOCKCHAIN.ETHEREUM);
  const btcWallets = sortedWallets.filter((w) => w.chain === BLOCKCHAIN.BITCOIN);

  const selectedWallet = wallets.find((w) => w.uuid === selectedWalletUuid) ?? null;

  const ethTotals = ethWallets.reduce(
    (acc, wallet) => ({
      balance: acc.balance + (parseFloat(wallet.nativeBalance) || 0),
      marketValue: acc.marketValue + (parseFloat(wallet.marketValue) || 0),
    }),
    { balance: 0, marketValue: 0 },
  );

  const btcTotals = btcWallets.reduce(
    (acc, wallet) => ({
      balance: acc.balance + (parseFloat(wallet.nativeBalance) || 0),
      marketValue: acc.marketValue + (parseFloat(wallet.marketValue) || 0),
    }),
    { balance: 0, marketValue: 0 },
  );

  const handleSelectWallet = useCallback((wallet: WalletType) => {
    setSelectedWalletUuid((prev) => (prev === wallet.uuid ? null : wallet.uuid));
  }, []);

  const handleAddWalletSubmit = (data: Parameters<typeof handleCreateWallet>[0]) => {
    handleCreateWallet(data);
    setShowAddModal(false);
  };

  const handleBatchSubmit = (addresses: DerivedAddress[], importData: HardwareWalletImport) => {
    handleBatchCreateWallets(addresses, importData);
    setShowAddModal(false);
  };

  const handleSaveWallet = (uuid: string, name: string) => {
    handleUpdateWalletName(uuid, name);
  };

  const handleConfirmDelete = () => {
    if (deletingWallet) {
      handleDeleteWallet(deletingWallet.uuid);
      if (selectedWalletUuid === deletingWallet.uuid) setSelectedWalletUuid(null);
      setDeletingWallet(null);
    }
  };

  const buildActionBarProps = (chain: string) => {
    const walletForChain = selectedWallet?.chain === chain ? selectedWallet : null;
    const isPending = walletForChain
      ? walletForChain.verificationStatus !== WALLET_VERIFICATION_STATUS.VERIFIED
      : false;
    const canDerive = walletForChain ? canDeriveAddress(walletForChain) : false;

    return {
      selectedWallet: walletForChain,
      canVerify: isPending,
      canDerive,
      isSyncing,
      onAdd: () => setShowAddModal(true),
      onEdit: () => walletForChain && setEditingWallet(walletForChain),
      onVerify: () => walletForChain && setVerifyingWallet(walletForChain),
      onDerive: () => walletForChain && openDeriveModal(walletForChain),
      onSync: () => walletForChain && handleSyncWallet(walletForChain.uuid),
      onDelete: () => walletForChain && setDeletingWallet(walletForChain),
    };
  };

  if (isLoading) {
    return (
      <main className="text-text-primary">
        <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-mid"></div>
            <p className="text-sm text-text-muted">Loading wallets...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="text-text-primary">
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 md:gap-6 items-start">
            <Panel
              title="Ethereum"
              icon={<CurrencyEthIcon size={ICON_MD} />}
              actions={
                ethWallets.length > 0 ? (
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs text-text-muted">
                      {formatCryptoBalance(ethTotals.balance, '').trimEnd()}
                    </span>
                    <span className="text-sm font-semibold text-text-primary">
                      {formatDisplayCurrency(ethTotals.marketValue)}
                    </span>
                  </div>
                ) : undefined
              }
            >
              {ethWallets.length === 0 ? (
                <ChainEmptyState message="No Ethereum wallets" onAction={() => setShowAddModal(true)} />
              ) : (
                <>
                  <WalletList
                    wallets={ethWallets}
                    selectedWalletUuid={selectedWalletUuid}
                    onSelectWallet={handleSelectWallet}
                    onEditWallet={(wallet) => setEditingWallet(wallet)}
                  />
                  <WalletActionBar {...buildActionBarProps(BLOCKCHAIN.ETHEREUM)} />
                </>
              )}
            </Panel>

            <Panel
              title="Bitcoin"
              icon={<CurrencyBtcIcon size={ICON_MD} />}
              actions={
                btcWallets.length > 0 ? (
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs text-text-muted">
                      {formatCryptoBalance(btcTotals.balance, '').trimEnd()}
                    </span>
                    <span className="text-sm font-semibold text-text-primary">
                      {formatDisplayCurrency(btcTotals.marketValue)}
                    </span>
                  </div>
                ) : undefined
              }
            >
              {btcWallets.length === 0 ? (
                <ChainEmptyState message="No Bitcoin wallets" onAction={() => setShowAddModal(true)} />
              ) : (
                <>
                  <WalletList
                    wallets={btcWallets}
                    selectedWalletUuid={selectedWalletUuid}
                    onSelectWallet={handleSelectWallet}
                    onEditWallet={(wallet) => setEditingWallet(wallet)}
                  />
                  <WalletActionBar {...buildActionBarProps(BLOCKCHAIN.BITCOIN)} />
                </>
              )}
            </Panel>
          </div>
        </div>
      </div>

      <AddWalletModal
        isOpen={showAddModal}
        isLoading={isCreating}
        userAccountUuid={userAccountUuid}
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAddWalletSubmit}
        onBatchSubmit={handleBatchSubmit}
      />

      <EditWalletModal
        wallet={editingWallet}
        isOpen={!!editingWallet}
        onClose={() => setEditingWallet(null)}
        onSave={handleSaveWallet}
        isUpdating={isUpdating}
      />

      <DeleteWalletModal
        isOpen={!!deletingWallet}
        wallet={deletingWallet}
        onConfirm={handleConfirmDelete}
        onClose={() => setDeletingWallet(null)}
      />

      <WalletVerificationModal
        isOpen={!!verifyingWallet}
        wallet={verifyingWallet}
        onClose={() => setVerifyingWallet(null)}
      />

      <DeriveAddressModal
        isOpen={!!derivingWallet}
        wallet={derivingWallet}
        onConfirm={handleDeriveAddress}
        onClose={closeDeriveModal}
        isCreating={isCreating}
      />

      <WalletSortModal
        isOpen={showSortModal}
        selectedSort={sortOption}
        onClose={() => setShowSortModal(false)}
        onApply={handleApply}
      />
    </main>
  );
}

export default WalletsPage;
