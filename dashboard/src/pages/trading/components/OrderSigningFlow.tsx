import type { OrderSubmission, ShareToken, TransferOrder, Wallet } from '@ledova/shared';
import { CreateOrderSigningFlow } from './CreateOrderSigningFlow';

interface Props {
  isOpen: boolean;
  submission?: OrderSubmission | null;
  tokens?: ShareToken[];
  wallet?: Wallet | null;
  onClose: () => void;
  onSuccess?: (order: TransferOrder, recovered?: boolean) => void;
}

export function OrderSigningFlow({ isOpen, submission, tokens = [], wallet = null, onClose, onSuccess }: Props) {
  if (!isOpen || !submission) return null;
  return (
    <CreateOrderSigningFlow
      submission={submission}
      tokens={tokens}
      wallet={wallet}
      onClose={onClose}
      onSuccess={onSuccess}
    />
  );
}
