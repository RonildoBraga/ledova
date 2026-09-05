import { ChartBarIcon, StarIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { useColors } from '@hooks/useColors';
import { useCurrency } from '@hooks/useCurrency';
import type { Asset } from '@ledova/shared';
import { Accordion } from '@components/Accordion';
import { AssetTypeIcon } from '@components/AssetTypeIcon';

interface MarketCardProps {
  assets: Asset[];
  favouriteAssetUuids: Set<string>;
  isLoading: boolean;
  onAssetPress: (asset: Asset) => void;
}

export function MarketCard({ assets, favouriteAssetUuids, isLoading, onAssetPress }: MarketCardProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  if (isLoading) {
    return (
      <Accordion title="Market" icon={<ChartBarIcon />}>
        <div className="flex items-center justify-center gap-2 py-6">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-mid" />
          <span className="text-sm text-text-muted">Loading market data...</span>
        </div>
      </Accordion>
    );
  }

  if (assets.length === 0) {
    return (
      <Accordion title="Market" icon={<ChartBarIcon />}>
        <div className="flex items-center justify-center py-6">
          <span className="text-sm text-text-muted">No assets available</span>
        </div>
      </Accordion>
    );
  }

  return (
    <Accordion title="Market" icon={<ChartBarIcon />}>
      <div className="flex flex-col gap-1 px-2">
        {assets.map((asset) => {
          const currentPrice = asset.currentPrice ? parseFloat(asset.currentPrice) : null;
          const isFavourite = favouriteAssetUuids.has(asset.uuid);

          return (
            <button
              key={asset.uuid}
              type="button"
              className="flex items-center justify-between py-1 hover:bg-surface-tertiary/30 transition-colors rounded text-left"
              onClick={() => onAssetPress(asset)}
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <StarIcon
                  size={DESIGN_TOKENS.icon.sizes.sm}
                  color={isFavourite ? colors.status.warning.icon : colors.text.subtle}
                  weight={isFavourite ? 'fill' : 'regular'}
                />
                <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} />
                <span className="text-sm font-semibold text-text-secondary">{asset.symbol}</span>
                <span className="text-xs text-text-subtle">•</span>
                <span className="text-xs text-text-subtle truncate">{asset.name}</span>
              </div>
              <span className="text-sm font-semibold text-text-primary">
                {currentPrice !== null
                  ? formatDisplayCurrency(currentPrice, asset.isYieldToken ? 6 : undefined)
                  : 'N/A'}
              </span>
            </button>
          );
        })}
      </div>
    </Accordion>
  );
}
