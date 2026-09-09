// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
import type { PortfolioSnapshotDataPoint } from '@ledova/shared';
import { PerformanceSection } from './PerformanceSection';

vi.mock('@hooks/useCurrency', () => ({
  useCurrency: () => ({ formatDisplayCurrency: (value: number) => `$${value.toFixed(2)}` }),
}));
vi.mock('@hooks/useColors', () => ({ useColors: () => ({ chart: ['#112233'] }) }));
vi.mock('./performance/PortfolioValueChart', () => ({ PortfolioValueChart: () => null }));
vi.mock('./performance/HoldingsChart', () => ({
  HoldingsChart: ({ onActivePointChange }: { onActivePointChange: (index: number) => void }) => (
    <button onClick={() => onActivePointChange(0)}>Earlier date</button>
  ),
}));

afterEach(cleanup);

function point(dayIndex: number, baseQuantity: string): PortfolioSnapshotDataPoint {
  return {
    dayIndex,
    date: `2026-09-0${dayIndex + 1}`,
    totalMarketValue: 200 + Number(baseQuantity) * 100,
    assetValues: { ETH: 200 + Number(baseQuantity) * 100 },
    assetSymbols: ['ETH'],
    assetHoldings: {
      ETH: {
        assetUuid: 'eth',
        quantity: String(2 + Number(baseQuantity)),
        wallets: ['base-wallet', 'ethereum-wallet'],
        marketValue: String(200 + Number(baseQuantity) * 100),
        perChain: [
          {
            chain: 'base',
            quantity: baseQuantity,
            marketValue: String(Number(baseQuantity) * 100),
            wallets: ['base-wallet'],
          },
          { chain: 'ethereum', quantity: '2', marketValue: '200', wallets: ['ethereum-wallet'] },
        ],
      },
    },
  };
}

function show(snapshotData: PortfolioSnapshotDataPoint[]) {
  const view = render(
    <PerformanceSection
      snapshotData={snapshotData}
      timeRanges={[]}
      selectedTimeRange="3M"
      onTimeRangeChange={() => {}}
      isLoading={false}
      error={null}
    />,
  );
  fireEvent.click(view.getByText('Holdings'));
  return view;
}

describe('the historical network breakdown', () => {
  it('expands one asset and follows the selected historical point', () => {
    const view = show([point(0, '1'), point(1, '3')]);
    expect(view.queryByText('base')).toBeNull();
    fireEvent.click(view.getByLabelText('Show ETH by network'));
    expect(view.getByText('3 ETH')).toBeTruthy();
    expect(view.getByText('$300.00')).toBeTruthy();
    fireEvent.click(view.getByText('Earlier date'));
    expect(view.getByText('1 ETH')).toBeTruthy();
    expect(view.getByText('$100.00')).toBeTruthy();
    expect(view.queryByText('3 ETH')).toBeNull();
    fireEvent.click(view.getByLabelText('Hide ETH by network'));
    expect(view.queryByText('base')).toBeNull();
  });

  it('keeps an unpriced slice distinct from a real zero', () => {
    const snapshot = point(0, '0');
    delete snapshot.assetHoldings.ETH.perChain![1].marketValue;
    const view = show([snapshot]);
    fireEvent.click(view.getByLabelText('Show ETH by network'));
    expect(view.getByText('$0.00')).toBeTruthy();
    expect(view.getByText('Unpriced')).toBeTruthy();
  });

  it.each([undefined, [point(0, '1').assetHoldings.ETH.perChain![0]]])(
    'does not invent a split for older or single-network data',
    (perChain) => {
      const snapshot = point(0, '1');
      snapshot.assetHoldings.ETH.perChain = perChain;
      const view = show([snapshot]);
      expect(view.queryByLabelText('Show ETH by network')).toBeNull();
    },
  );
});
