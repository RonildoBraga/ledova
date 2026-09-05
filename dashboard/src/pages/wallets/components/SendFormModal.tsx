import { useState, useEffect } from 'react';
import {
  CurrencyEthIcon,
  CurrencyBtcIcon,
  QrCodeIcon,
  ArrowsClockwiseIcon,
  CertificateIcon,
  CurrencyCircleDollarIcon,
  CoinsIcon,
  ShieldWarningIcon,
  ShieldCheckIcon,
} from '@phosphor-icons/react';
import {
  getChainShortCode,
  BLOCKCHAIN,
  DESIGN_TOKENS,
  getAddressPlaceholder,
  getBlockchainDisplayName,
  getEstimatedFee,
  formatWalletAddressShort,
  validateWalletAddress,
} from '@ledova/shared';
import { useCurrency } from '@hooks/useCurrency';
import type { Wallet, WhitelistStatus } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { useQRScanner, QRScannerView } from '@components/qr';
import type { UnifiedAsset } from '../hooks/useTransferFlow';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;

interface SendFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  wallet: Wallet;
  assets: UnifiedAsset[];
  isLoadingAssets: boolean;
  hasShareTokens: boolean;
  isSenderWhitelisted: boolean;
  isRecipientWhitelisted: boolean;
  isCheckingRecipientWhitelist: boolean;
  senderWhitelistStatus?: WhitelistStatus;
  recipientWhitelistStatus?: WhitelistStatus;
  onBack: () => void;
  onTransfer: (asset: UnifiedAsset, toAddress: string, amount: string) => void;
  onAddressChange?: (address: string) => void;
}

export function SendFormModal({
  isOpen,
  onClose,
  wallet,
  assets,
  isLoadingAssets,
  hasShareTokens,
  isSenderWhitelisted,
  isRecipientWhitelisted,
  isCheckingRecipientWhitelist,
  senderWhitelistStatus,
  recipientWhitelistStatus,
  onBack,
  onTransfer,
  onAddressChange,
}: SendFormModalProps) {
  const { formatDisplayCurrency } = useCurrency();
  const [selectedAsset, setSelectedAsset] = useState<UnifiedAsset | null>(null);
  const [toAddress, setToAddress] = useState('');
  const [amount, setAmount] = useState('');
  const [showAddressScanner, setShowAddressScanner] = useState(false);

  const chainShortCode = getChainShortCode(wallet.chain);
  const isBitcoin = wallet.chain === BLOCKCHAIN.BITCOIN;
  const ChainIcon = isBitcoin ? CurrencyBtcIcon : CurrencyEthIcon;
  const displayAddress = formatWalletAddressShort(wallet.address);

  useEffect(() => {
    if (assets.length > 0 && !selectedAsset) {
      setSelectedAsset(assets[0]);
    }
  }, [assets, selectedAsset]);

  useEffect(() => {
    if (isOpen) {
      setSelectedAsset(null);
      setToAddress('');
      setAmount('');
      setShowAddressScanner(false);
      onAddressChange?.('');
    }
  }, [isOpen, onAddressChange]);

  const handleAddressChange = (address: string) => {
    setToAddress(address);
    onAddressChange?.(address);
  };

  const { error: scannerError } = useQRScanner({
    scannerId: 'send-form-address-scanner',
    onScanSuccess: (text) => {
      let address = text;
      if (address.startsWith('ethereum:')) {
        address = address.replace('ethereum:', '').split('@')[0];
      } else if (address.startsWith('bitcoin:')) {
        address = address.replace('bitcoin:', '').split('?')[0];
      }
      handleAddressChange(address);
      setShowAddressScanner(false);
    },
    enabled: showAddressScanner && isOpen,
    qrboxSize: 200,
  });

  const isSenderWhitelistUnknown = senderWhitelistStatus?.status === 'unknown';
  const isRecipientWhitelistUnknown = recipientWhitelistStatus?.status === 'unknown';

  const isShareToken = selectedAsset?.type === 'share_token';
  const isCrypto = selectedAsset?.type === 'crypto';

  const isValidAddress = isBitcoin
    ? validateWalletAddress(toAddress, wallet.chain)
    : toAddress.length === 42 && toAddress.startsWith('0x');

  const parsedAmount = parseFloat(amount);
  const parsedBalance = parseFloat(selectedAsset?.displayBalance.replace(/,/g, '') || '0');
  const isValidAmount = !isNaN(parsedAmount) && parsedAmount > 0 && parsedAmount <= parsedBalance;

  const whitelistValid = isShareToken ? isSenderWhitelisted && isRecipientWhitelisted : true;
  const canTransfer = !!selectedAsset && isValidAddress && isValidAmount && whitelistValid;

  const handleUseMax = () => {
    if (!selectedAsset) return;
    if (isCrypto) {
      const balance = parseFloat(wallet.nativeBalance);
      const estimatedFee = getEstimatedFee(chainShortCode);
      const maxAmount = Math.max(0, balance - estimatedFee);
      setAmount(maxAmount.toString());
    } else {
      setAmount(selectedAsset.displayBalance.replace(/,/g, ''));
    }
  };

  const handleAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isShareToken) {
      setAmount(e.target.value.replace(/[^0-9]/g, ''));
    } else {
      setAmount(e.target.value.replace(/[^0-9.]/g, ''));
    }
  };

  const handleConfirm = () => {
    if (canTransfer && selectedAsset) {
      onTransfer(selectedAsset, toAddress, amount);
    }
  };

  const getAssetIcon = (asset: UnifiedAsset, selected: boolean) => {
    const colorClass = selected ? 'text-brand-light' : 'text-text-muted';
    switch (asset.type) {
      case 'share_token':
        return <CertificateIcon size={ICON_MD} className={colorClass} weight={selected ? 'duotone' : 'regular'} />;
      case 'stablecoin':
        return (
          <CurrencyCircleDollarIcon size={ICON_MD} className={colorClass} weight={selected ? 'duotone' : 'regular'} />
        );
      case 'crypto':
        return isBitcoin ? (
          <CurrencyBtcIcon size={ICON_MD} className={colorClass} weight={selected ? 'duotone' : 'regular'} />
        ) : (
          <CurrencyEthIcon size={ICON_MD} className={colorClass} weight={selected ? 'duotone' : 'regular'} />
        );
    }
  };

  const amountPlaceholder = isShareToken ? '0' : '0.00';
  const addressPlaceholder = getAddressPlaceholder(chainShortCode);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="md"
      showFooter
      showCancelButton
      cancelLabel="Back"
      onCancel={onBack}
      confirmLabel="Continue"
      confirmDisabled={!canTransfer}
      onConfirm={handleConfirm}
    >
      <div className="space-y-4">
        <div className="flex flex-col items-center gap-2 pt-2 pb-6">
          <ChainIcon size={ICON_XXL} className="text-info-light" weight="light" />
          <span className="text-sm font-medium text-text-primary font-mono">{displayAddress}</span>
        </div>

        {isLoadingAssets ? (
          <div className="flex items-center justify-center py-4">
            <ArrowsClockwiseIcon size={ICON_LG} className="animate-spin text-text-muted" />
            <span className="ml-2 text-sm text-text-muted">Loading assets...</span>
          </div>
        ) : assets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-4 gap-2">
            <CoinsIcon size={ICON_XXL} className="text-text-subtle" />
            <p className="text-sm text-text-muted">No assets in this wallet</p>
          </div>
        ) : (
          <div className="space-y-0 rounded-lg border border-border overflow-hidden">
            {hasShareTokens && !isSenderWhitelisted && senderWhitelistStatus !== undefined && (
              <div className="p-3 bg-warning-light/10 border-b border-warning-light/20">
                <div className="flex items-center gap-2">
                  <ShieldWarningIcon size={ICON_SM} className="text-warning-light" />
                  <p className="text-xs text-warning-light">
                    {isSenderWhitelistUnknown
                      ? 'We could not reach the network to check your allowlist status. Transfers of tokenized assets are held until the check succeeds - please try again shortly.'
                      : 'Your wallet is not whitelisted. The operator must whitelist it before you can transfer tokenized assets.'}
                  </p>
                </div>
              </div>
            )}

            {assets.map((asset, index) => {
              const isSelected = selectedAsset?.id === asset.id;
              return (
                <button
                  key={asset.id}
                  type="button"
                  onClick={() => {
                    setSelectedAsset(asset);
                    setAmount('');
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors ${
                    isSelected ? 'bg-brand-mid/10' : 'hover:bg-surface-tertiary'
                  } ${index < assets.length - 1 ? 'border-b border-border-subtle' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    {getAssetIcon(asset, isSelected)}
                    <span className={`text-sm font-medium ${isSelected ? 'text-brand-light' : 'text-text-primary'}`}>
                      {asset.symbol}
                    </span>
                  </div>
                  <span className="flex items-center gap-1.5">
                    {asset.type === 'crypto' && (
                      <>
                        <span className="text-xs text-text-muted">{asset.displayBalance}</span>
                        <span className="text-xs text-text-subtle">&middot;</span>
                      </>
                    )}
                    <span className={`text-sm font-medium ${isSelected ? 'text-brand-light' : 'text-text-primary'}`}>
                      {formatDisplayCurrency(parseFloat(asset.marketValue))}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-text-primary">Destination Address</label>
            <button
              type="button"
              onClick={() => setShowAddressScanner(!showAddressScanner)}
              className="flex items-center gap-1 text-xs text-brand-mid hover:text-brand-light transition-colors"
            >
              <QrCodeIcon size={ICON_SM} />
              <span>{showAddressScanner ? 'Hide' : 'Scan QR'}</span>
            </button>
          </div>
          {showAddressScanner ? (
            <div className="space-y-2">
              <QRScannerView
                scannerId="send-form-address-scanner"
                error={scannerError}
                className="relative overflow-hidden rounded-lg bg-black mx-auto [&_video]:!object-cover [&_video]:!h-full [&_video]:!w-full"
                style={{ width: 220, height: 220 }}
              />
              <p className="text-xs text-text-muted text-center">Scan address QR code</p>
            </div>
          ) : (
            <input
              type="text"
              value={toAddress}
              onChange={(e) => handleAddressChange(e.target.value)}
              placeholder={addressPlaceholder}
              className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
            />
          )}
          {toAddress && !isValidAddress && (
            <p className="text-xs text-warning-light">
              Please enter a valid {getBlockchainDisplayName(chainShortCode)} address
            </p>
          )}
        </div>

        {isShareToken && isValidAddress && (
          <div className="flex items-center gap-2">
            {isCheckingRecipientWhitelist ? (
              <span className="flex items-center gap-1 text-xs text-text-muted">
                <ArrowsClockwiseIcon size={ICON_XS} className="animate-spin" />
                Checking whitelist...
              </span>
            ) : isRecipientWhitelisted ? (
              <span className="flex items-center gap-1 text-xs text-text-muted">
                <ShieldCheckIcon size={ICON_SM} />
                Recipient is whitelisted
              </span>
            ) : isRecipientWhitelistUnknown ? (
              <span className="flex items-center gap-1 text-xs text-warning-light">
                <ShieldWarningIcon size={ICON_SM} />
                Allowlist status unavailable
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-error-light">
                <ShieldWarningIcon size={ICON_SM} />
                Recipient is not whitelisted
              </span>
            )}
          </div>
        )}

        {isShareToken && isValidAddress && !isRecipientWhitelisted && recipientWhitelistStatus !== undefined && (
          <div
            className={
              isRecipientWhitelistUnknown
                ? 'p-3 rounded-lg bg-warning-light/10 border border-warning-light/20'
                : 'p-3 rounded-lg bg-error-light/10 border border-error-light/20'
            }
          >
            <p className={isRecipientWhitelistUnknown ? 'text-sm text-warning-light' : 'text-sm text-error-light'}>
              {isRecipientWhitelistUnknown
                ? 'We could not reach the network to check the recipient allowlist status. The transfer is held until the check succeeds - please try again shortly.'
                : 'The recipient address is not whitelisted. The operator must whitelist it before it can receive tokenized assets.'}
            </p>
          </div>
        )}

        {selectedAsset && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-text-primary">Amount ({selectedAsset.symbol})</label>
            <input
              type="text"
              value={amount}
              onChange={handleAmountChange}
              placeholder={amountPlaceholder}
              className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
            />
            <div className="flex items-center justify-between">
              <p className="text-xs text-text-muted">
                Max: {selectedAsset.displayBalance} {selectedAsset.symbol}
                {isShareToken && ' (whole numbers only)'}
              </p>
              <button
                type="button"
                onClick={handleUseMax}
                className="text-xs text-brand-mid hover:text-brand-light font-medium"
              >
                Use Max
              </button>
            </div>
            {amount && !isValidAmount && parsedAmount > parsedBalance && (
              <p className="text-xs text-error-light">Amount exceeds available balance</p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
