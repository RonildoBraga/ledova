import { HOLDING_ASSET_TYPE, getChartColor, getHoldingAssetTypeLabel, type TimeRange } from '@ledova/shared';
import type { HoldingWithWallet, HoldingsSummary, AssetAllocationItem } from '@ledova/shared';
import { MOCK_ASSETS, MOCK_ASSET_VALUES, MOCK_WALLETS } from '../../../_mock/mockConfig';

/**
 * Chart data point interface
 */
interface MockPortfolioSnapshot {
  dayIndex: number;
  date: string;
  totalMarketValue: number;
  assetValues: Record<string, number>;
  assetQuantities: Record<string, number>;
  assetSymbols: string[];
}

/**
 * Helper functions for calculating summaries and allocation
 */
function calculateSummary(holdings: HoldingWithWallet[], walletsCount: number): HoldingsSummary {
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

  const byAssetType = Array.from(assetTypeMap.entries())
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

function calculateAssetAllocation(holdings: HoldingWithWallet[], totalValue: number): AssetAllocationItem[] {
  if (totalValue === 0) return [];

  const assetMap = new Map<string, { symbol: string; name: string; totalValue: number }>();

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
    }))
    .sort((a, b) => b.totalValue - a.totalValue)
    .map((item, index) => ({
      ...item,
      color: getChartColor(index), // Re-assign colors after sorting
    }));
}

/**
 * Generates mock holdings data with realistic asset distribution
 * Uses shared mock configuration to ensure consistency
 */
export const generateMockHoldingsData = () => {
  const mockAssets = MOCK_ASSETS.map((asset) => ({
    uuid: asset.uuid,
    symbol: asset.symbol,
    name: asset.name,
    assetType: HOLDING_ASSET_TYPE.ERC20_TOKEN,
    value: MOCK_ASSET_VALUES[asset.symbol as keyof typeof MOCK_ASSET_VALUES],
  }));

  const mockWallets = MOCK_WALLETS.map((w) => ({ ...w }));

  // Create holdings distributed across wallets
  const holdings: HoldingWithWallet[] = mockAssets.flatMap((asset, assetIndex) => {
    const walletsForAsset = assetIndex % 2 === 0 ? [mockWallets[0]] : [mockWallets[1]];

    return walletsForAsset.map((wallet) => ({
      uuid: `holding-${asset.uuid}-${wallet.uuid}`,
      assetSymbol: asset.symbol,
      assetName: asset.name,
      quantity: (asset.value / (assetIndex + 1) / 100).toString(),
      marketValue: asset.value.toString(),
      walletAddress: wallet.address,
      lastSyncedAt: new Date().toISOString(),
      asset: {
        uuid: asset.uuid,
        symbol: asset.symbol,
        name: asset.name,
        assetType: asset.assetType,
        decimals: 18,
        contractAddress: `0x${asset.uuid}`,
        chain: wallet.chain,
        iconUrl: null,
        currentPrice: null,
        priceCurrency: 'USD',
        isActive: true,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      walletInfo: {
        uuid: wallet.uuid,
        name: wallet.name,
        address: wallet.address,
        chain: wallet.chain,
      },
      wallet: wallet.uuid,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }));
  });

  const summary = calculateSummary(holdings, mockWallets.length);
  const assetAllocation = calculateAssetAllocation(holdings, summary.totalValue);

  return {
    holdings,
    summary,
    assetAllocation,
    isLoading: false,
    hasError: false,
  };
};

/**
 * Generates mock portfolio performance chart data for a given time range
 * Uses the same asset values from holdings to ensure consistency
 */
export const generateMockPortfolioChartData = (timeRange: TimeRange): MockPortfolioSnapshot[] => {
  // Map time ranges to data points (days)
  const dataPointsMap: Record<TimeRange, number> = {
    '3M': 90,
    '6M': 180,
    '1Y': 365,
    '2Y': 730,
    '3Y': 1095,
    ALL: 1460, // ~4 years
  };

  const dataPoints = dataPointsMap[timeRange];
  const today = new Date();

  // Get current holdings data to use as the baseline
  const currentHoldings = generateMockHoldingsData();
  const { assetAllocation, summary } = currentHoldings;

  // Create a map of current asset values and calculate quantities based on mock asset values
  const currentAssetValues: Record<string, number> = {};
  const currentAssetQuantities: Record<string, number> = {};

  assetAllocation.forEach((asset) => {
    currentAssetValues[asset.symbol] = asset.totalValue;
    // Calculate quantity from total value and mock asset price
    const assetPrice = MOCK_ASSET_VALUES[asset.symbol as keyof typeof MOCK_ASSET_VALUES];
    currentAssetQuantities[asset.symbol] = asset.totalValue / assetPrice;
  });

  const assets = assetAllocation.map((a) => a.symbol);

  return Array.from({ length: dataPoints }, (_, i) => {
    const date = new Date(today);
    date.setDate(date.getDate() - (dataPoints - i - 1));

    const isLastDataPoint = i === dataPoints - 1;

    // For the last data point (today), use exact values from current holdings
    if (isLastDataPoint) {
      const sortedAssets = assets.slice().sort((a, b) => currentAssetValues[b] - currentAssetValues[a]);

      return {
        dayIndex: i,
        date: date.toISOString().split('T')[0],
        totalMarketValue: summary.totalValue,
        assetValues: currentAssetValues,
        assetQuantities: currentAssetQuantities,
        assetSymbols: sortedAssets,
      };
    }

    // Generate realistic price fluctuations with different trends for historical data
    const dayProgress = i / dataPoints;
    const trend = 0.0003; // 0.03% daily upward trend

    const assetValues: Record<string, number> = {};
    const assetQuantities: Record<string, number> = {};
    let totalMarketValue = 0;

    assets.forEach((symbol) => {
      // Different volatility and trends for each asset
      const assetVolatility = symbol === 'BTC' ? 0.015 : symbol === 'ETH' ? 0.02 : symbol === 'SOL' ? 0.035 : 0.045;

      const assetTrend =
        symbol === 'BTC' ? trend : symbol === 'ETH' ? trend * 1.2 : symbol === 'SOL' ? trend * 1.5 : trend * 0.8;

      // Add some cyclical patterns for realism
      const cyclicalFactor = 1 + 0.1 * Math.sin(dayProgress * Math.PI * 4);

      const randomWalk = 1 + (Math.random() - 0.5) * 2 * assetVolatility;
      const trendFactor = 1 + assetTrend * i;

      // Calculate historical value based on current value and trends
      const currentValue = currentAssetValues[symbol];
      const historicalValue = currentValue / trendFactor / cyclicalFactor / randomWalk;

      assetValues[symbol] = historicalValue;
      assetQuantities[symbol] = currentAssetQuantities[symbol]; // Quantities remain constant
      totalMarketValue += historicalValue;
    });

    // Sort assets by value (highest first) to ensure consistent color mapping
    const sortedAssets = assets.slice().sort((a, b) => assetValues[b] - assetValues[a]);

    return {
      dayIndex: i,
      date: date.toISOString().split('T')[0],
      totalMarketValue,
      assetValues,
      assetQuantities,
      assetSymbols: sortedAssets,
    };
  });
};
