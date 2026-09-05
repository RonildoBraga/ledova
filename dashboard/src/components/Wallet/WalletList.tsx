import type { Wallet } from '@ledova/shared';
import { WalletItem } from './WalletItem';

interface WalletListProps {
  wallets: Wallet[];
  selectedWalletUuid: string | null;
  onSelectWallet: (wallet: Wallet) => void;
  onEditWallet?: (wallet: Wallet) => void;
}

export function WalletList({ wallets, selectedWalletUuid, onSelectWallet, onEditWallet }: WalletListProps) {
  return (
    <div className="space-y-1">
      {wallets.map((wallet) => (
        <WalletItem
          key={wallet.uuid}
          wallet={wallet}
          isSelected={selectedWalletUuid === wallet.uuid}
          onSelect={() => onSelectWallet(wallet)}
          onEdit={onEditWallet ? () => onEditWallet(wallet) : undefined}
        />
      ))}
    </div>
  );
}
