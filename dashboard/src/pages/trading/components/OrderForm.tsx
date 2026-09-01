import { useState, useEffect, useMemo, useImperativeHandle, forwardRef } from 'react';
import { WalletIcon } from '@phosphor-icons/react';
import { formatWalletAddressShort, formatCurrency } from '@ledova/shared-utils';
import type { ShareToken, CreateOrderRequest, Wallet as WalletType } from '@ledova/shared-types';
import type { OrderType } from '@ledova/shared-constants';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;

interface OrderFormProps {
  token: ShareToken;
  orderType: OrderType;
  wallets: WalletType[];
  defaultWalletUuid?: string;
  getWalletBalance?: (address: string) => string | undefined;
  onSubmit: (data: CreateOrderRequest) => void;
  onValidationChange?: (isValid: boolean) => void;
}

export interface OrderFormRef {
  submit: () => void;
  isValid: boolean;
}

export const OrderForm = forwardRef<OrderFormRef, OrderFormProps>(function OrderForm(
  { token, orderType, wallets, defaultWalletUuid, getWalletBalance, onSubmit, onValidationChange },
  ref,
) {
  const [quantity, setQuantity] = useState('');
  const [minQuantity, setMinQuantity] = useState('');
  const [pricePerShare, setPricePerShare] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [selectedWalletUuid, setSelectedWalletUuid] = useState(defaultWalletUuid ?? '');

  // Update selected wallet when default changes
  useEffect(() => {
    if (defaultWalletUuid && !selectedWalletUuid) {
      setSelectedWalletUuid(defaultWalletUuid);
    }
  }, [defaultWalletUuid, selectedWalletUuid]);

  // Set default price to last traded price
  useEffect(() => {
    if (token.lastPrice && !pricePerShare) {
      setPricePerShare(token.lastPrice);
    }
  }, [token.lastPrice, pricePerShare]);

  const totalValue = useMemo(() => {
    const qty = parseFloat(quantity) || 0;
    const price = parseFloat(pricePerShare) || 0;
    return qty * price;
  }, [quantity, pricePerShare]);

  const selectedWallet = useMemo(
    () => wallets.find((wallet) => wallet.uuid === selectedWalletUuid),
    [wallets, selectedWalletUuid],
  );

  // Get current wallet's balance for sell orders
  const currentWalletBalance =
    selectedWallet && getWalletBalance ? getWalletBalance(selectedWallet.address) : undefined;

  const isValid = useMemo(() => {
    const qty = parseFloat(quantity) || 0;
    const minQty = parseFloat(minQuantity) || 0;
    const price = parseFloat(pricePerShare) || 0;

    // Basic validation
    if (qty <= 0 || price <= 0 || !selectedWallet) return false;

    // Min quantity cannot exceed quantity
    if (minQty > qty) return false;

    // For sell orders, check if quantity exceeds balance
    if (orderType === 'sell' && currentWalletBalance) {
      const balance = parseInt(currentWalletBalance, 10);
      if (qty > balance) return false;
    }

    return true;
  }, [quantity, minQuantity, pricePerShare, selectedWallet, orderType, currentWalletBalance]);

  // Notify parent of validation changes
  useEffect(() => {
    onValidationChange?.(isValid);
  }, [isValid, onValidationChange]);

  const handleSubmit = () => {
    if (!isValid) return;

    const minQty = parseFloat(minQuantity) || 0;
    if (!selectedWallet) return;

    onSubmit({
      token: token.uuid,
      orderType,
      walletUuid: selectedWallet.uuid,
      walletAddress: selectedWallet.address,
      quantity: parseFloat(quantity),
      minQuantity: minQty > 0 ? minQty : undefined,
      pricePerShare,
    });
  };

  // Expose submit method and validation state to parent
  useImperativeHandle(ref, () => ({
    submit: handleSubmit,
    isValid,
  }));

  const isBuy = orderType === 'buy';

  return (
    <div className="space-y-4">
      {/* Order Details */}
      <div className="space-y-0">
        {/* Last Price */}
        {token.lastPrice && (
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Last Price:</span>
            <span className="text-sm font-medium text-text-primary">{formatCurrency(parseFloat(token.lastPrice))}</span>
          </div>
        )}

        {/* Wallet Selection */}
        <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
          <span className="text-sm text-text-muted">{isBuy ? 'Delivery Wallet:' : 'Source Wallet:'}</span>
          {wallets.length === 1 ? (
            <div className="flex items-center gap-2">
              <WalletIcon size={ICON_SM} className="text-brand-mid" />
              <span className="text-sm font-medium text-text-primary font-mono">
                {formatWalletAddressShort(wallets[0].address)}
              </span>
            </div>
          ) : (
            <select
              value={selectedWalletUuid}
              onChange={(e) => setSelectedWalletUuid(e.target.value)}
              className="text-sm font-medium text-text-primary bg-transparent border-none focus:outline-none focus:ring-0 text-right cursor-pointer"
            >
              {wallets.map((wallet) => (
                <option key={wallet.uuid} value={wallet.uuid}>
                  {wallet.name || formatWalletAddressShort(wallet.address)}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Available Balance (for sell orders) */}
        {!isBuy && currentWalletBalance && (
          <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
            <span className="text-sm text-text-muted">Available:</span>
            <span className="text-sm font-medium text-brand-light">{currentWalletBalance} shares</span>
          </div>
        )}

        {/* Total Value */}
        <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
          <span className="text-sm text-text-muted">Total Value:</span>
          <span className={`text-sm font-semibold ${totalValue > 0 ? 'text-text-primary' : 'text-text-muted'}`}>
            {formatCurrency(totalValue)}
          </span>
        </div>
      </div>

      {/* Form Inputs */}
      <div className="space-y-4 pt-2">
        {/* Quantity */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-text-primary">Quantity (shares)</label>
          <input
            type="number"
            min="1"
            step="1"
            max={!isBuy && currentWalletBalance ? currentWalletBalance : undefined}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="Enter number of shares"
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
          />
          {!isBuy && currentWalletBalance && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-text-muted">Max: {currentWalletBalance} shares</p>
              <button
                type="button"
                onClick={() => setQuantity(currentWalletBalance)}
                className="text-xs text-brand-light hover:text-brand-subtle"
              >
                Use Max
              </button>
            </div>
          )}
        </div>

        {/* Advanced Options */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-brand-light hover:text-brand-subtle font-medium"
          >
            {showAdvanced ? 'Hide advanced options' : 'Advanced options'}
          </button>

          {showAdvanced && (
            <div className="space-y-2 mt-3">
              <label className="text-sm font-medium text-text-primary">Minimum Fill Quantity (optional)</label>
              <input
                type="number"
                min="0"
                step="1"
                max={quantity || undefined}
                value={minQuantity}
                onChange={(e) => setMinQuantity(e.target.value)}
                placeholder="0 = accept any partial fill"
                className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
              />
              <p className="text-xs text-text-muted">Hint: Leave empty or 0 to accept any partial fill</p>
              {minQuantity && parseFloat(minQuantity) > (parseFloat(quantity) || 0) && (
                <p className="text-xs text-error-light">Minimum quantity cannot exceed total quantity.</p>
              )}
            </div>
          )}
        </div>

        {/* Price per Share */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-text-primary">Price per Share (AUD)</label>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={pricePerShare}
            onChange={(e) => setPricePerShare(e.target.value)}
            placeholder="Enter price per share"
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
          />
          {token.lastPrice && (
            <p className="text-xs text-text-muted">
              Hint: Last traded at {formatCurrency(parseFloat(token.lastPrice))}
            </p>
          )}
        </div>
      </div>
    </div>
  );
});
