import type { OrderSubmission, ShareToken, TransferOrder, Wallet } from '@ledova/shared';
import { CreateOrderSigningModal } from './CreateOrderSigningModal';

interface Props {
  visible: boolean;
  submission?: OrderSubmission | null;
  tokens?: ShareToken[];
  wallet?: Wallet | null;
  onClose: () => void;
  onSuccess?: (order: TransferOrder, recovered?: boolean) => void;
}

export function OrderSigningModal({ visible, submission, tokens = [], wallet = null, onClose, onSuccess }: Props) {
  if (!visible || !submission) return null;
  return (
    <CreateOrderSigningModal
      submission={submission}
      tokens={tokens}
      wallet={wallet}
      onClose={onClose}
      onSuccess={onSuccess}
    />
  );
}
