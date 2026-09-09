import { HOLDING_ASSET_TYPE, calculateAssetAllocation, calculateHoldingsSummary, type TimeRange } from '@ledova/shared';
import type { HoldingWithWallet, PortfolioSnapshotDataPoint, PortfolioSnapshotHolding } from '@ledova/shared';
import { MOCK_ASSETS, MOCK_ASSET_VALUES, MOCK_WALLETS } from '../../../_mock/mockConfig';

export const generateMockHoldingsData = () => {
  const mockAssets = MOCK_ASSETS.map((asset) => ({
    uuid: asset.uuid,
    symbol: asset.symbol,
    name: asset.name,
    assetType: HOLDING_ASSET_TYPE.ERC20_TOKEN,
    value: MOCK_ASSET_VALUES[asset.symbol as keyof typeof MOCK_ASSET_VALUES],
  }));

  const mockWallets = MOCK_WALLETS.map((w) => ({ ...w }));

  const holdings: HoldingWithWallet[] = mockAssets.flatMap((asset, assetIndex) => {
    const walletsForAsset = assetIndex % 2 === 0 ? [mockWallets[0]] : [mockWallets[1]];

    return walletsForAsset.map((wallet) => ({
      uuid: `holding-${asset.uuid}-${wallet.uuid}`,
      chain: wallet.chain,
      assetSymbol: asset.symbol,
      assetName: asset.name,
      quantity: (asset.value / (assetIndex + 1) / 100).toString(),
      marketValue: asset.value.toString(),
      valueSource: 'market' as const,
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
        currentPrice: ((assetIndex + 1) * 100).toString(),
        valueSource: 'market' as const,
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
      walletUuid: wallet.uuid,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }));
  });

  const summary = calculateHoldingsSummary(holdings, mockWallets.length);
  const assetAllocation = calculateAssetAllocation(holdings, summary.totalValue);

  return {
    holdings,
    summary,
    assetAllocation,
    isLoading: false,
    hasError: false,
  };
};

export const generateMockPortfolioChartData = (timeRange: TimeRange): PortfolioSnapshotDataPoint[] => {
  const dataPointsMap: Record<TimeRange, number> = {
    '3M': 90,
    '6M': 180,
    '1Y': 365,
    '2Y': 730,
    '3Y': 1095,
    ALL: 1460,
  };

  const dataPoints = dataPointsMap[timeRange];
  const today = new Date();

  const currentHoldings = generateMockHoldingsData();
  const { assetAllocation, summary } = currentHoldings;

  const currentAssetValues: Record<string, number> = {};
  const snapshotHoldings: Record<string, PortfolioSnapshotHolding> = {};

  assetAllocation.forEach((asset) => {
    currentAssetValues[asset.symbol] = asset.totalValue;

    snapshotHoldings[asset.symbol] = {
      assetUuid: asset.assetUuid,
      quantity: String(asset.totalQuantity),
      marketValue: String(asset.totalValue),
      wallets: [],
    };
  });

  const assets = assetAllocation.map((a) => a.symbol);

  return Array.from({ length: dataPoints }, (_, i) => {
    const date = new Date(today);
    date.setDate(date.getDate() - (dataPoints - i - 1));

    const isLastDataPoint = i === dataPoints - 1;

    if (isLastDataPoint) {
      const sortedAssets = assets.slice().sort((a, b) => currentAssetValues[b] - currentAssetValues[a]);

      return {
        dayIndex: i,
        date: date.toISOString().split('T')[0],
        totalMarketValue: summary.totalValue,
        assetValues: currentAssetValues,
        assetHoldings: snapshotHoldings,
        assetSymbols: sortedAssets,
      };
    }

    const dayProgress = i / dataPoints;
    const trend = 0.0003;

    const assetValues: Record<string, number> = {};
    const assetHoldings: Record<string, PortfolioSnapshotHolding> = {};
    let totalMarketValue = 0;

    assets.forEach((symbol) => {
      const assetVolatility = symbol === 'BTC' ? 0.015 : symbol === 'ETH' ? 0.02 : symbol === 'SOL' ? 0.035 : 0.045;

      const assetTrend =
        symbol === 'BTC' ? trend : symbol === 'ETH' ? trend * 1.2 : symbol === 'SOL' ? trend * 1.5 : trend * 0.8;

      const cyclicalFactor = 1 + 0.1 * Math.sin(dayProgress * Math.PI * 4);

      const randomWalk = 1 + (Math.random() - 0.5) * 2 * assetVolatility;
      const trendFactor = 1 + assetTrend * i;

      const currentValue = currentAssetValues[symbol];
      const historicalValue = currentValue / trendFactor / cyclicalFactor / randomWalk;

      assetValues[symbol] = historicalValue;
      assetHoldings[symbol] = { ...snapshotHoldings[symbol], marketValue: String(historicalValue) };
      totalMarketValue += historicalValue;
    });

    const sortedAssets = assets.slice().sort((a, b) => assetValues[b] - assetValues[a]);

    return {
      dayIndex: i,
      date: date.toISOString().split('T')[0],
      totalMarketValue,
      assetValues,
      assetHoldings,
      assetSymbols: sortedAssets,
    };
  });
};
