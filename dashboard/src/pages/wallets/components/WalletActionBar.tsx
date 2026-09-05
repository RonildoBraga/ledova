import {
  PlusIcon,
  PencilSimpleIcon,
  ShieldCheckIcon,
  TreeStructureIcon,
  ArrowsClockwiseIcon,
  TrashIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

interface ActionButtonProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}

function ActionButton({ icon, label, onClick, disabled = false, danger = false }: ActionButtonProps) {
  if (disabled) {
    return (
      <button
        type="button"
        disabled
        className="flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg text-text-subtle/40 cursor-not-allowed"
      >
        {icon}
        <span className="text-xs leading-tight">{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg transition-colors ${
        danger
          ? 'text-error-light hover:bg-error-light/10'
          : 'text-text-muted hover:text-brand-light hover:bg-brand-light/10'
      }`}
    >
      {icon}
      <span className="text-xs leading-tight">{label}</span>
    </button>
  );
}

interface WalletActionBarProps {
  selectedWallet: Wallet | null;
  canVerify: boolean;
  canDerive: boolean;
  isSyncing: boolean;
  onAdd: () => void;
  onEdit: () => void;
  onVerify: () => void;
  onDerive: () => void;
  onSync: () => void;
  onDelete: () => void;
}

export function WalletActionBar({
  selectedWallet,
  canVerify,
  canDerive,
  isSyncing,
  onAdd,
  onEdit,
  onVerify,
  onDerive,
  onSync,
  onDelete,
}: WalletActionBarProps) {
  const hasSelection = !!selectedWallet;

  return (
    <div className="flex items-center justify-center gap-1 pt-2 mt-1">
      <ActionButton icon={<PlusIcon size={ICON_MD} />} label="Add" onClick={onAdd} />
      <ActionButton icon={<PencilSimpleIcon size={ICON_MD} />} label="Edit" onClick={onEdit} disabled={!hasSelection} />
      <ActionButton
        icon={<ShieldCheckIcon size={ICON_MD} />}
        label="Verify"
        onClick={onVerify}
        disabled={!hasSelection || !canVerify}
      />
      <ActionButton
        icon={<TreeStructureIcon size={ICON_MD} />}
        label="Derive"
        onClick={onDerive}
        disabled={!hasSelection || !canDerive}
      />
      <ActionButton
        icon={<ArrowsClockwiseIcon size={ICON_MD} className={isSyncing ? 'animate-spin' : ''} />}
        label="Sync"
        onClick={onSync}
        disabled={!hasSelection || isSyncing}
      />
      <div className="w-px h-8 bg-border-subtle mx-1" />
      <ActionButton
        icon={<TrashIcon size={ICON_MD} />}
        label="Delete"
        onClick={onDelete}
        disabled={!hasSelection}
        danger
      />
    </div>
  );
}
