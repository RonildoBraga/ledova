import type { Asset } from '@ledova/shared';
import { AssetTypeIcon } from '@components/AssetTypeIcon';
import { useCurrency } from '@hooks/useCurrency';

interface AssetListItemProps {
  asset: Asset;
  onPress: (asset: Asset) => void;
}

export function AssetListItem({ asset, onPress }: AssetListItemProps) {
  const { formatDisplayCurrency } = useCurrency();
  const currentPrice = asset.currentPrice ? parseFloat(asset.currentPrice) : null;

  return (
    <button
      type="button"
      className="w-full flex items-center justify-between py-4 border-b border-border hover:bg-surface-tertiary/30 transition-colors text-left"
      onClick={() => onPress(asset)}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} className="text-text-muted flex-shrink-0" />
        <span className="text-xs font-semibold text-text-secondary">{asset.symbol}</span>
        <span className="text-xs text-text-subtle">•</span>
        <span className="text-xs text-text-subtle truncate">{asset.name}</span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-sm font-semibold text-text-primary">
          {currentPrice !== null ? formatDisplayCurrency(currentPrice) : 'N/A'}
        </span>
      </div>
    </button>
  );
}
