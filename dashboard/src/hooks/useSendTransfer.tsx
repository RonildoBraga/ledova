import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSelectedPortfolio } from './useSelectedPortfolio';
import { useTransferFlow } from '@pages/wallets/hooks/useTransferFlow';
import { WalletSelectionModal } from '@pages/wallets/components/WalletSelectionModal';
import { SendFormModal } from '@pages/wallets/components/SendFormModal';
import { TransferSigningFlow } from '@pages/wallets/components/TransferSigningFlow';
import type { Wallet } from '@ledova/shared-types';

interface SendTransferContextValue {
  openSendTransfer: () => void;
}

const SendTransferContext = createContext<SendTransferContextValue | null>(null);

export function SendTransferProvider({ children }: { children: ReactNode }) {
  const { selectedAccount } = useSelectedPortfolio();
  const queryClient = useQueryClient();
  const userAccountUuid = selectedAccount?.uuid;

  const [walletModalOpen, setWalletModalOpen] = useState(false);
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [sendFormOpen, setSendFormOpen] = useState(false);

  const transferFlow = useTransferFlow(selectedWallet);
  const { handleTransferSuccess: resetTransferFlow } = transferFlow;

  const openSendTransfer = useCallback(() => {
    resetTransferFlow();
    setSelectedWallet(null);
    setSendFormOpen(false);
    setWalletModalOpen(true);
  }, [resetTransferFlow]);

  const resetAll = useCallback(() => {
    setWalletModalOpen(false);
    setSelectedWallet(null);
    setSendFormOpen(false);
    resetTransferFlow();
  }, [resetTransferFlow]);

  const handleWalletSelected = useCallback((wallet: Wallet) => {
    setSelectedWallet(wallet);
    setWalletModalOpen(false);
    setSendFormOpen(true);
  }, []);

  const handleBackToWalletSelection = useCallback(() => {
    setSendFormOpen(false);
    setSelectedWallet(null);
    resetTransferFlow();
    setWalletModalOpen(true);
  }, [resetTransferFlow]);

  const handleTransferSuccess = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['wallets'] });
    setSendFormOpen(false);
    resetTransferFlow();
  }, [queryClient, resetTransferFlow]);

  return (
    <SendTransferContext.Provider value={{ openSendTransfer }}>
      {children}

      <WalletSelectionModal
        isOpen={walletModalOpen}
        onClose={resetAll}
        onSelectWallet={handleWalletSelected}
        userAccountUuid={userAccountUuid}
      />

      {selectedWallet && (
        <SendFormModal
          isOpen={sendFormOpen && !transferFlow.isSigningModalOpen}
          onClose={resetAll}
          wallet={selectedWallet}
          assets={transferFlow.assets}
          isLoadingAssets={transferFlow.isLoadingAssets}
          hasShareTokens={transferFlow.hasShareTokens}
          isSenderWhitelisted={transferFlow.isSenderWhitelisted}
          isRecipientWhitelisted={transferFlow.isRecipientWhitelisted}
          isCheckingRecipientWhitelist={transferFlow.isCheckingRecipientWhitelist}
          senderWhitelistStatus={transferFlow.senderWhitelistStatus}
          recipientWhitelistStatus={transferFlow.recipientWhitelistStatus}
          onBack={handleBackToWalletSelection}
          onTransfer={transferFlow.handleCombinedTransfer}
          onAddressChange={transferFlow.setToAddress}
        />
      )}

      {selectedWallet && transferFlow.selectedAsset && transferFlow.pendingTransfer && (
        <TransferSigningFlow
          isOpen={transferFlow.isSigningModalOpen}
          onClose={transferFlow.handleCloseSigningModal}
          transferType={transferFlow.getTransferType()}
          wallet={selectedWallet}
          token={
            transferFlow.selectedAsset?.tokenAddress
              ? {
                  token: transferFlow.selectedAsset.tokenAddress,
                  symbol: transferFlow.selectedAsset.symbol,
                  name: transferFlow.selectedAsset.name,
                  balance: transferFlow.selectedAsset.balance,
                  contractAddress: transferFlow.selectedAsset.tokenAddress,
                  decimals: transferFlow.selectedAsset.decimals,
                }
              : undefined
          }
          toAddress={transferFlow.pendingTransfer.toAddress}
          amount={transferFlow.pendingTransfer.amount}
          chainType={transferFlow.getChainType()}
          preparedTransaction={transferFlow.signing.preparedTransaction}
          isPreparing={transferFlow.signing.isPreparing}
          prepareError={transferFlow.signing.prepareError}
          onPrepare={transferFlow.signing.prepare}
          onBroadcast={transferFlow.signing.broadcast}
          onSuccess={handleTransferSuccess}
        />
      )}
    </SendTransferContext.Provider>
  );
}

export function useSendTransfer(): SendTransferContextValue {
  const context = useContext(SendTransferContext);
  if (!context) {
    throw new Error('useSendTransfer must be used within a SendTransferProvider');
  }
  return context;
}
