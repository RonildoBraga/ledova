import { useRef, useState, useCallback } from 'react';
import type { ShareToken, CreateOrderRequest, Wallet, OrderType } from '@ledova/shared';
import { ShieldWarningIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { OrderForm } from './OrderForm';
import type { OrderFormRef } from './OrderForm';

const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

interface PlaceOrderPanelProps {
  token: ShareToken;
  wallets: Wallet[];
  walletsWithHoldings: { walletAddress: string; balance: string }[];
  onSubmit: (data: CreateOrderRequest) => Promise<boolean>;
  onNewOrder: () => void;
  onDismiss: () => void;
  submissionError: string | null;
  isWalletWhitelisted: boolean;
  isWhitelistStatusUnknown: boolean;
  isLoadingWhitelistStatus: boolean;
}

export function PlaceOrderPanel({
  token,
  wallets,
  walletsWithHoldings,
  onSubmit,
  onNewOrder,
  onDismiss,
  submissionError,
  isWalletWhitelisted,
  isWhitelistStatusUnknown,
  isLoadingWhitelistStatus,
}: PlaceOrderPanelProps) {
  const [orderType, setOrderType] = useState<OrderType | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isFormValid, setIsFormValid] = useState(false);
  const formRef = useRef<OrderFormRef>(null);
  const transition = useRef({ generation: 0, pending: false });

  const isOpen = orderType !== null;
  const isBuy = orderType === 'buy';

  const sellWallets = wallets.filter((w) =>
    walletsWithHoldings.some((h) => h.walletAddress.toLowerCase() === w.address.toLowerCase()),
  );
  const availableWallets = isBuy ? wallets : sellWallets;

  const handleOpen = (type: OrderType) => {
    transition.current.generation++;
    transition.current.pending = false;
    onNewOrder();
    setIsSubmitting(false);
    setOrderType(type);
    setIsFormValid(false);
  };

  const handleClose = () => {
    transition.current.generation++;
    transition.current.pending = false;
    onDismiss();
    setIsSubmitting(false);
    setOrderType(null);
    setIsFormValid(false);
  };

  const handleSubmit = useCallback(
    async (data: CreateOrderRequest) => {
      if (transition.current.pending) return;
      transition.current.pending = true;
      const generation = transition.current.generation;
      setIsSubmitting(true);
      try {
        const accepted = await onSubmit(data);
        if (accepted && transition.current.generation === generation) {
          setOrderType(null);
          setIsFormValid(false);
        }
      } finally {
        if (transition.current.generation === generation) {
          transition.current.pending = false;
          setIsSubmitting(false);
        }
      }
    },
    [onSubmit],
  );

  const isConfirmDisabled = !isFormValid || isSubmitting || isLoadingWhitelistStatus || !isWalletWhitelisted;

  return (
    <>
      <div className="flex gap-4">
        <button
          onClick={() => handleOpen('sell')}
          disabled={wallets.length === 0}
          className="flex-1 py-2.5 px-6 rounded-lg font-semibold text-white bg-surface-tertiary hover:bg-surface-secondary border border-border-subtle disabled:bg-surface-disabled disabled:cursor-not-allowed transition-colors"
        >
          New sell order — {token.symbol}
        </button>
        <button
          onClick={() => handleOpen('buy')}
          disabled={wallets.length === 0}
          className="flex-1 py-2.5 px-6 rounded-lg font-semibold text-white bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed transition-colors"
        >
          New buy order — {token.symbol}
        </button>
      </div>

      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title={`${isBuy ? 'Buy' : 'Sell'} ${token.symbol}`}
        size="md"
        showFooter
        confirmLabel={isSubmitting ? 'Placing...' : `Place ${isBuy ? 'Buy' : 'Sell'} Order`}
        confirmDisabled={isConfirmDisabled}
        confirmLoading={isSubmitting}
        onConfirm={() => formRef.current?.submit()}
      >
        <div className="space-y-4">
          {submissionError && <p role="alert">{submissionError}</p>}
          {!isWalletWhitelisted && !isLoadingWhitelistStatus && (
            <div className="p-4 rounded-lg bg-warning-light/10 border border-warning-light/20">
              <div className="flex items-start gap-3">
                <ShieldWarningIcon size={ICON_LG} className="text-warning-light flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-semibold text-warning-light">
                    {isWhitelistStatusUnknown ? 'Allowlist Status Unavailable' : 'Wallet Not Allowlisted'}
                  </h4>
                  <p className="text-sm text-text-muted mt-1">
                    {isWhitelistStatusUnknown
                      ? 'We could not reach the network to check your allowlist status. Orders are held until the check succeeds - please try again shortly.'
                      : 'The operator must add your wallet to the allowlist before you can place orders.'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {orderType && (
            <OrderForm
              ref={formRef}
              token={token}
              orderType={orderType}
              wallets={availableWallets}
              defaultWalletUuid={availableWallets[0]?.uuid}
              onSubmit={handleSubmit}
              onValidationChange={setIsFormValid}
            />
          )}
        </div>
      </Modal>
    </>
  );
}
