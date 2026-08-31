import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSelectedPortfolio } from './useSelectedPortfolio';
import { BuyCryptoModal } from '@pages/wallets/components/BuyCryptoModal';
import { BuyCryptoWidgetModal } from '@pages/wallets/components/BuyCryptoWidgetModal';

interface BuyCryptoContextValue {
  openBuyCrypto: (initialAsset?: string) => void;
}

const BuyCryptoContext = createContext<BuyCryptoContextValue | null>(null);

export function BuyCryptoProvider({ children }: { children: ReactNode }) {
  const { selectedAccount } = useSelectedPortfolio();
  const queryClient = useQueryClient();
  const userAccountUuid = selectedAccount?.uuid;

  const [buyModalOpen, setBuyModalOpen] = useState(false);
  const [buyInitialAsset, setBuyInitialAsset] = useState<string | undefined>();
  const [widgetModalOpen, setWidgetModalOpen] = useState(false);
  const [widgetUrl, setWidgetUrl] = useState<string | null>(null);

  const openBuyCrypto = useCallback((initialAsset?: string) => {
    setBuyInitialAsset(initialAsset);
    setBuyModalOpen(true);
  }, []);

  const handleBuyModalClose = useCallback(() => {
    setBuyModalOpen(false);
    setBuyInitialAsset(undefined);
  }, []);

  const handleNavigateToWidget = useCallback((url: string) => {
    setBuyModalOpen(false);
    setWidgetUrl(url);
    setWidgetModalOpen(true);
  }, []);

  const handleWidgetClose = useCallback(() => {
    setWidgetModalOpen(false);
    setWidgetUrl(null);
  }, []);

  const handleWidgetComplete = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['wallets'] });
  }, [queryClient]);

  return (
    <BuyCryptoContext.Provider value={{ openBuyCrypto }}>
      {children}

      <BuyCryptoModal
        isOpen={buyModalOpen}
        onClose={handleBuyModalClose}
        onNavigateToWidget={handleNavigateToWidget}
        userAccountUuid={userAccountUuid}
        initialAsset={buyInitialAsset}
      />

      <BuyCryptoWidgetModal
        isOpen={widgetModalOpen}
        onClose={handleWidgetClose}
        onComplete={handleWidgetComplete}
        widgetUrl={widgetUrl}
      />
    </BuyCryptoContext.Provider>
  );
}

export function useBuyCrypto(): BuyCryptoContextValue {
  const context = useContext(BuyCryptoContext);
  if (!context) {
    throw new Error('useBuyCrypto must be used within a BuyCryptoProvider');
  }
  return context;
}
