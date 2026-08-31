import { WalletIcon, CheckCircleIcon, ClockIcon } from '@phosphor-icons/react';
import { WALLET_VERIFICATION_STATUS, DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;

interface WalletBadgeProps {
  verificationStatus: string;
}

export function WalletBadge({ verificationStatus }: WalletBadgeProps) {
  const isVerified = verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;

  return (
    <span className="relative inline-flex">
      <WalletIcon size={ICON_SM} className={isVerified ? 'text-success-light' : 'text-text-muted'} />
      {isVerified ? (
        <CheckCircleIcon size={ICON_XS} weight="fill" className="absolute -bottom-0.5 -right-0.5 text-success-light" />
      ) : (
        <ClockIcon size={ICON_XS} weight="fill" className="absolute -bottom-0.5 -right-0.5 text-warning-light" />
      )}
    </span>
  );
}
