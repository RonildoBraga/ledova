import { getHoldingAssetTypeLabel, HOLDING_ASSET_TYPE, getChartColor } from '../constants';
import type {
  AllocationBasis,
  AssetAllocationItem,
  AssetChainSlice,
  AssetTypeSummary,
  HoldingsSummary,
  HoldingWithWallet,
} from '../types';

function priceCameBack(holding: HoldingWithWallet): boolean {
  return holding.marketValue !== null && holding.marketValue !== undefined && holding.marketValue !== '';
}

function chainOf(holding: HoldingWithWallet): string {
  return holding.chain || holding.walletInfo?.chain || '';
}

function foldedByChain(chains: Map<string, AssetChainSlice>): AssetChainSlice[] {
  return Array.from(chains.values()).sort((a, b) => b.totalValue - a.totalValue || b.quantity - a.quantity);
}

export function calculateHoldingsSummary(holdings: HoldingWithWallet[], walletsCount: number): HoldingsSummary {
  const assetTypeMap = new Map<string, { totalValue: number; holdingsCount: number }>();
  let totalValue = 0;

  for (const holding of holdings) {
    const value = parseFloat(holding.marketValue ?? '') || 0;
    const assetType = holding.asset?.assetType || HOLDING_ASSET_TYPE.ERC20_TOKEN;

    totalValue += value;

    const existing = assetTypeMap.get(assetType) || { totalValue: 0, holdingsCount: 0 };
    assetTypeMap.set(assetType, {
      totalValue: existing.totalValue + value,
      holdingsCount: existing.holdingsCount + 1,
    });
  }

  const byAssetType: AssetTypeSummary[] = Array.from(assetTypeMap.entries())
    .map(([assetType, data]) => ({
      assetType,
      label: getHoldingAssetTypeLabel(assetType),
      totalValue: data.totalValue,
      holdingsCount: data.holdingsCount,
    }))
    .sort((a, b) => b.totalValue - a.totalValue);

  return {
    totalValue,
    holdingsCount: holdings.length,
    walletsCount,
    byAssetType,
  };
}

export function calculateAssetAllocation(holdings: HoldingWithWallet[], totalValue: number): AssetAllocationItem[] {
  const assetMap = new Map<
    string,
    {
      symbol: string;
      name: string;
      totalValue: number;
      totalQuantity: number;
      priced: boolean;
      chains: Map<string, AssetChainSlice>;
      navPerToken?: string | null;
      isYieldToken?: boolean;
    }
  >();

  for (const holding of holdings) {
    const assetUuid = holding.asset?.uuid || holding.assetSymbol;
    const value = parseFloat(holding.marketValue ?? '') || 0;
    const quantity = parseFloat(holding.quantity) || 0;
    const priced = priceCameBack(holding);

    let existing = assetMap.get(assetUuid);
    if (existing) {
      existing.totalValue += value;
      existing.totalQuantity += quantity;
      existing.priced = existing.priced && priced;
    } else {
      existing = {
        symbol: holding.assetSymbol || holding.asset?.symbol || 'Unknown',
        name: holding.assetName || holding.asset?.name || 'Unknown Asset',
        totalValue: value,
        totalQuantity: quantity,
        priced,
        chains: new Map<string, AssetChainSlice>(),
        navPerToken: holding.asset?.navPerToken,
        isYieldToken: holding.asset?.isYieldToken,
      };
      assetMap.set(assetUuid, existing);
    }

    const chain = chainOf(holding);
    const slice = existing.chains.get(chain);
    if (slice) {
      slice.quantity += quantity;
      slice.totalValue += value;
      slice.priced = slice.priced && priced;
    } else {
      existing.chains.set(chain, { chain, quantity, totalValue: value, priced });
    }
  }

  const totalQuantity = Array.from(assetMap.values()).reduce((sum, data) => sum + data.totalQuantity, 0);
  const weighByQuantity = totalValue === 0;
  const basisTotal = weighByQuantity ? totalQuantity : totalValue;

  if (basisTotal === 0) return [];

  return Array.from(assetMap.entries())
    .map(([assetUuid, data], index) => ({
      assetUuid,
      symbol: data.symbol,
      name: data.name,
      totalValue: data.totalValue,
      percentage: ((weighByQuantity ? data.totalQuantity : data.totalValue) / basisTotal) * 100,
      basis: (weighByQuantity ? 'quantity' : data.priced ? 'value' : 'unpriced') as AllocationBasis,
      color: getChartColor(index),
      totalQuantity: data.totalQuantity,
      perChain: foldedByChain(data.chains),
      navPerToken: data.navPerToken,
      isYieldToken: data.isYieldToken,
    }))
    .sort((a, b) => b.percentage - a.percentage)
    .map((item, index) => ({
      ...item,
      color: getChartColor(index),
    }));
}
