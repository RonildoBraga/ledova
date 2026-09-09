import { portfolioSnapshotPoints } from '../../src/utils/portfolio-snapshots';
import type { PortfolioSnapshot } from '../../src/types';

const snapshot = (overrides: Partial<PortfolioSnapshot> = {}): PortfolioSnapshot => ({
  uuid: 'portfolio:2026-09-09',
  portfolio: 'portfolio',
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: '2026-09-09T00:00:00Z',
  snapshotDate: '2026-09-09',
  snapshotReason: 'DAILY',
  holdingsData: {
    ETH: {
      assetUuid: 'eth',
      quantity: '3.000000000000000001',
      marketValue: '6000',
      wallets: ['base-wallet', 'ethereum-wallet'],
      perChain: [
        { chain: 'base', quantity: '1.000000000000000001', marketValue: '2000', wallets: ['base-wallet'] },
        { chain: 'ethereum', quantity: '2', marketValue: '4000', wallets: ['ethereum-wallet'] },
      ],
    },
  },
  totalMarketValue: '6000',
  ...overrides,
});

it('keeps one plotted asset while preserving exact network quantities and wallet identity', () => {
  const input = snapshot();
  const before = JSON.stringify(input);
  const point = portfolioSnapshotPoints([input])[0]!;

  expect(point.assetSymbols).toEqual(['ETH']);
  expect(point.assetValues).toEqual({ ETH: 6000 });
  expect(point.totalMarketValue).toBe(6000);
  expect(point.assetHoldings.ETH).toEqual(input.holdingsData.ETH);
  expect(point.assetHoldings.ETH!.perChain?.[0]?.quantity).toBe('1.000000000000000001');
  expect(JSON.stringify(input)).toBe(before);
});

it('preserves each dated breakdown when the network quantities change', () => {
  const second = snapshot({
    snapshotDate: '2026-09-10',
    holdingsData: {
      ETH: {
        assetUuid: 'eth',
        quantity: '0',
        marketValue: '0',
        wallets: ['base-wallet'],
        perChain: [{ chain: 'base', quantity: '0', marketValue: '0', wallets: ['base-wallet'] }],
      },
    },
    totalMarketValue: '0',
  });
  const points = portfolioSnapshotPoints([snapshot(), second]);

  expect(points.map(({ dayIndex, date }) => [dayIndex, date])).toEqual([
    [0, '2026-09-09'],
    [1, '2026-09-10'],
  ]);
  expect(points[0]!.assetHoldings.ETH!.perChain).toHaveLength(2);
  expect(points[1]!.assetHoldings.ETH!.perChain).toEqual(second.holdingsData.ETH!.perChain);
  expect(points[1]!.totalMarketValue).toBe(0);
});

it('retains an unpriced holding without inventing a price or legacy network history', () => {
  const input = snapshot({
    totalMarketValue: null,
    hasValueData: false,
    holdingsData: { ORD: { assetUuid: 'shares', quantity: '250', wallets: ['wallet'] } },
  });
  const point = portfolioSnapshotPoints([input])[0]!;

  expect(point.assetSymbols).toEqual(['ORD']);
  expect(point.assetHoldings.ORD!.quantity).toBe('250');
  expect(point.assetHoldings.ORD!.marketValue).toBeUndefined();
  expect(point.assetHoldings.ORD!.perChain).toBeUndefined();
});

it('keeps the existing total fallback when older responses omit it', () => {
  const point = portfolioSnapshotPoints([snapshot({ totalMarketValue: undefined })])[0]!;
  expect(point.totalMarketValue).toBe(6000);
  expect(portfolioSnapshotPoints([])).toEqual([]);
});
