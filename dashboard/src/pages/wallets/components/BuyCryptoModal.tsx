import { useState, useEffect, useCallback } from 'react';
import {
  CurrencyEthIcon,
  CurrencyBtcIcon,
  CurrencyCircleDollarIcon,
  WalletIcon,
  HardDriveIcon,
  CloudIcon,
  ClockIcon,
  SpinnerGapIcon,
} from '@phosphor-icons/react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { BUYABLE_ASSETS, WALLET_TYPE, DESIGN_TOKENS } from '@ledova/shared-constants';
import type { BuyableAssetConfig } from '@ledova/shared-constants';
import { getWallets, getOnRampWidgetUrl } from '@ledova/shared-services';
import { formatWalletAddressShort, formatCryptoBalance, formatSyncAge } from '@ledova/shared-utils';
import { useCurrency } from '@hooks/useCurrency';
import type { Wallet } from '@ledova/shared-types';
import { Modal } from '@components/Modal';
import { WalletBadge } from '@components/Wallet';
import apiClient from '@services/apiClient';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;

const ASSET_ICONS: Record<string, React.ReactNode> = {
  BTC: <CurrencyBtcIcon size={ICON_MD} className="text-text-primary" />,
  ETH: <CurrencyEthIcon size={ICON_MD} className="text-text-primary" />,
  USDC: <CurrencyCircleDollarIcon size={ICON_MD} className="text-text-primary" />,
  USDT: <CurrencyCircleDollarIcon size={ICON_MD} className="text-text-primary" />,
};

interface BuyCryptoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateToWidget: (url: string) => void;
  userAccountUuid?: string;
  initialAsset?: string;
}

export function BuyCryptoModal({
  isOpen,
  onClose,
  onNavigateToWidget,
  userAccountUuid,
  initialAsset,
}: BuyCryptoModalProps) {
  const { formatDisplayCurrency } = useCurrency();
  const [selectedAsset, setSelectedAsset] = useState<BuyableAssetConfig | null>(null);
  const [showWalletStep, setShowWalletStep] = useState(false);

  useEffect(() => {
    if (isOpen && initialAsset && !selectedAsset) {
      const asset = BUYABLE_ASSETS.find((a) => a.symbol === initialAsset);
      if (asset) {
        setSelectedAsset(asset);
      }
    }
  }, [isOpen, initialAsset, selectedAsset]);

  const walletsQuery = useQuery({
    queryKey: [
      'wallets',
      userAccountUuid,
      { chain: selectedAsset?.chain, verification_status: 'VERIFIED', order_by: 'wallet_type' },
    ],
    queryFn: () =>
      getWallets(apiClient, {
        user_account: userAccountUuid!,
        chain: selectedAsset!.chain,
        verification_status: 'VERIFIED',
        order_by: 'wallet_type',
      }),
    enabled: !!userAccountUuid && !!selectedAsset,
  });

  const matchingWallets = walletsQuery.data?.data.results || [];
  const isLoadingWallets = walletsQuery.isLoading;

  const widgetMutation = useMutation({
    mutationFn: (wallet: Wallet) =>
      getOnRampWidgetUrl(apiClient, {
        walletUuid: wallet.uuid,
        cryptoCurrency: selectedAsset!.symbol,
      }),
    onSuccess: (response) => {
      resetAndClose();
      onNavigateToWidget(response.data.url);
    },
  });

  useEffect(() => {
    if (!selectedAsset || isLoadingWallets) return;

    if (matchingWallets.length === 1 && widgetMutation.isIdle) {
      widgetMutation.mutate(matchingWallets[0]);
    } else if (matchingWallets.length !== 1) {
      setShowWalletStep(true);
    }
  }, [selectedAsset, isLoadingWallets, matchingWallets, widgetMutation]);

  const resetAndClose = useCallback(() => {
    setSelectedAsset(null);
    setShowWalletStep(false);
    widgetMutation.reset();
  }, [widgetMutation]);

  const handleClose = useCallback(() => {
    resetAndClose();
    onClose();
  }, [resetAndClose, onClose]);

  const handleBack = useCallback(() => {
    if (initialAsset) {
      handleClose();
    } else {
      resetAndClose();
    }
  }, [initialAsset, handleClose, resetAndClose]);

  const handleSelectAsset = (asset: BuyableAssetConfig) => {
    setSelectedAsset(asset);
  };

  const handleSelectWallet = (wallet: Wallet) => {
    widgetMutation.mutate(wallet);
  };

  const isOnAssetStep = !showWalletStep;
  const isProcessingAsset = !!selectedAsset && isOnAssetStep;
  const isLoading = widgetMutation.isPending;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      showFooter
      showCancelButton
      cancelLabel={isOnAssetStep ? 'Cancel' : 'Back'}
      onCancel={isOnAssetStep ? handleClose : handleBack}
    >
      {isOnAssetStep && (
        <>
          <div className="flex flex-col items-center gap-2 pt-2 pb-6">
            <CurrencyCircleDollarIcon size={ICON_XXL} className="text-info-light" weight="light" />
            <p className="text-sm text-text-muted">Select an asset to purchase</p>
          </div>

          <div className="flex flex-col gap-2">
            {BUYABLE_ASSETS.map((asset) => {
              const isAssetProcessing = isProcessingAsset && selectedAsset?.symbol === asset.symbol;

              return (
                <button
                  key={asset.symbol}
                  type="button"
                  className="flex items-center justify-between p-4 rounded-lg bg-surface-tertiary hover:bg-surface-disabled transition-colors disabled:opacity-50"
                  onClick={() => handleSelectAsset(asset)}
                  disabled={isProcessingAsset}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-surface-raised flex items-center justify-center">
                      {ASSET_ICONS[asset.symbol]}
                    </div>
                    <span className="text-base font-medium text-text-primary">{asset.name}</span>
                  </div>
                  {isAssetProcessing && <SpinnerGapIcon size={ICON_SM} className="animate-spin text-brand-mid" />}
                </button>
              );
            })}
          </div>
        </>
      )}

      {!isOnAssetStep && matchingWallets.length === 0 && (
        <div className="flex flex-col items-center gap-2 pt-2 pb-6">
          <WalletIcon size={ICON_XXL} className="text-text-subtle" weight="light" />
          <p className="text-sm text-text-muted">
            No verified wallets for {selectedAsset!.name}. Create one in Wallets.
          </p>
        </div>
      )}

      {!isOnAssetStep && matchingWallets.length > 1 && (
        <>
          <div className="flex flex-col items-center gap-2 pt-2 pb-6">
            <WalletIcon size={ICON_XXL} className="text-info-light" weight="light" />
            <p className="text-sm text-text-muted">Choose a wallet to receive {selectedAsset!.name}</p>
          </div>

          <div className="space-y-1">
            {matchingWallets.map((wallet) => {
              const walletLabel = wallet.name || formatWalletAddressShort(wallet.address);
              const isHardware = wallet.walletType === WALLET_TYPE.HARDWARE;
              const TypeIcon = isHardware ? HardDriveIcon : CloudIcon;
              const marketValue = parseFloat(wallet.marketValue) || 0;
              const syncAge = formatSyncAge(wallet.lastSyncedAt);
              const isSelected = isLoading && widgetMutation.variables?.uuid === wallet.uuid;

              return (
                <button
                  key={wallet.uuid}
                  type="button"
                  className="w-full flex items-center gap-3 py-2.5 rounded-lg hover:bg-surface-tertiary transition-colors text-left disabled:opacity-50"
                  onClick={() => handleSelectWallet(wallet)}
                  disabled={isLoading}
                >
                  <WalletBadge verificationStatus={wallet.verificationStatus} />
                  <span className="text-xs text-text-muted truncate">{walletLabel}</span>
                  <span className="inline-flex items-center justify-center p-1">
                    <TypeIcon size={ICON_XS} weight="bold" className="text-text-secondary" />
                  </span>
                  <div className="flex-1" />
                  {isSelected ? (
                    <SpinnerGapIcon size={ICON_SM} className="animate-spin text-brand-mid" />
                  ) : (
                    <>
                      {syncAge && (
                        <span className="inline-flex items-center gap-0.5 text-xs text-text-subtle flex-shrink-0">
                          <ClockIcon size={ICON_XS} />
                          {syncAge}
                        </span>
                      )}
                      <span className="text-xs text-text-muted flex-shrink-0">
                        {formatCryptoBalance(wallet.nativeBalance, '').trimEnd()}
                      </span>
                      <span className="text-xs text-text-muted flex-shrink-0">
                        {formatDisplayCurrency(marketValue)}
                      </span>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}

      {(widgetMutation.isError || walletsQuery.isError) && (
        <p className="text-sm text-error-light text-center mt-4">
          {widgetMutation.error instanceof Error
            ? widgetMutation.error.message
            : walletsQuery.error instanceof Error
              ? walletsQuery.error.message
              : 'Something went wrong'}
        </p>
      )}
    </Modal>
  );
}
