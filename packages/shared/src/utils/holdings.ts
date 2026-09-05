import { getHoldingAssetTypeLabel, HOLDING_ASSET_TYPE, getChartColor } from '../constants';
import type { HoldingWithWallet, HoldingsSummary, AssetTypeSummary, AssetAllocationItem } from '../types';

export function calculateHoldingsSummary(holdings: HoldingWithWallet[], walletsCount: number): HoldingsSummary {
  const assetTypeMap = new Map<string, { totalValue: number; holdingsCount: number }>();
  let totalValue = 0;

  for (const holding of holdings) {
    const value = parseFloat(holding.marketValue) || 0;
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
  if (totalValue === 0) return [];

  const assetMap = new Map<
    string,
    { symbol: string; name: string; totalValue: number; navPerToken?: string | null; isYieldToken?: boolean }
  >();

  for (const holding of holdings) {
    const assetUuid = holding.asset?.uuid || holding.assetSymbol;
    const value = parseFloat(holding.marketValue) || 0;

    const existing = assetMap.get(assetUuid);
    if (existing) {
      existing.totalValue += value;
    } else {
      assetMap.set(assetUuid, {
        symbol: holding.assetSymbol || holding.asset?.symbol || 'Unknown',
        name: holding.assetName || holding.asset?.name || 'Unknown Asset',
        totalValue: value,
        navPerToken: holding.asset?.navPerToken,
        isYieldToken: holding.asset?.isYieldToken,
      });
    }
  }

  return Array.from(assetMap.entries())
    .map(([assetUuid, data], index) => ({
      assetUuid,
      symbol: data.symbol,
      name: data.name,
      totalValue: data.totalValue,
      percentage: (data.totalValue / totalValue) * 100,
      color: getChartColor(index),
      navPerToken: data.navPerToken,
      isYieldToken: data.isYieldToken,
    }))
    .sort((a, b) => b.totalValue - a.totalValue)
    .map((item, index) => ({
      ...item,
      color: getChartColor(index),
    }));
}
