import { fireEvent, render } from '@testing-library/react-native';
import type { PortfolioSnapshotDataPoint } from '@ledova/shared';
import { PerformanceCard } from './PerformanceCard';

jest.mock('../../../hooks/useCurrency', () => ({
  useCurrency: () => ({ formatDisplayCurrency: (value: number) => `$${value.toFixed(2)}` }),
}));
jest.mock('./PortfolioLineChart', () => ({ PortfolioLineChart: () => null }));
jest.mock('./AssetLineChart', () => ({
  AssetLineChart: ({ onActivePointChange }: { onActivePointChange: (index: number) => void }) => {
    const { Text } = jest.requireActual<typeof import('react-native')>('react-native');
    return <Text onPress={() => onActivePointChange(0)}>Earlier date</Text>;
  },
}));

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

async function show(chartData: PortfolioSnapshotDataPoint[]) {
  const view = await render(
    <PerformanceCard
      chartData={chartData}
      timeRanges={[]}
      selectedTimeRange="3M"
      onTimeRangeChange={() => {}}
      isLoading={false}
      error={null}
      assetColorMap={{ ETH: '#112233' }}
    />,
  );
  await fireEvent.press(view.getByText('Holdings'));
  return view;
}

it('expands one asset and follows the selected historical point', async () => {
  const view = await show([point(0, '1'), point(1, '3')]);
  expect(view.queryByText('base')).toBeNull();
  await fireEvent.press(view.getByLabelText('Show ETH by network'));
  expect(view.getByText('3 ETH')).toBeTruthy();
  expect(view.getByText('$300.00')).toBeTruthy();
  await fireEvent.press(view.getByText('Earlier date'));
  expect(view.getByText('1 ETH')).toBeTruthy();
  expect(view.getByText('$100.00')).toBeTruthy();
  expect(view.queryByText('3 ETH')).toBeNull();
  await fireEvent.press(view.getByLabelText('Hide ETH by network'));
  expect(view.queryByText('base')).toBeNull();
});

it('keeps an unpriced slice distinct from a real zero', async () => {
  const snapshot = point(0, '0');
  delete snapshot.assetHoldings.ETH.perChain![1].marketValue;
  const view = await show([snapshot]);
  await fireEvent.press(view.getByLabelText('Show ETH by network'));
  expect(view.getByText('$0.00')).toBeTruthy();
  expect(view.getByText('Unpriced')).toBeTruthy();
});

it.each([undefined, [point(0, '1').assetHoldings.ETH.perChain![0]]])(
  'does not invent a split for older or single-network data',
  async (perChain) => {
    const snapshot = point(0, '1');
    snapshot.assetHoldings.ETH.perChain = perChain;
    const view = await show([snapshot]);
    expect(view.queryByLabelText('Show ETH by network')).toBeNull();
  },
);
