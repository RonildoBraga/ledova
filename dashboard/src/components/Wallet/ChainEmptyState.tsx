import { WalletIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

interface ChainEmptyStateProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function ChainEmptyState({ message, actionLabel = '+ Add wallet', onAction }: ChainEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-3">
      <WalletIcon size={ICON_XL} className="text-text-subtle" />
      <p className="text-sm text-text-muted">{message}</p>
      {onAction && (
        <button
          type="button"
          onClick={onAction}
          className="text-sm text-brand-light hover:text-brand-subtle transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
