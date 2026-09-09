import { fireEvent, render } from '@testing-library/react-native';
import type { AssetAllocationItem, HoldingsSummary } from '@ledova/shared';

jest.mock('react-native-gifted-charts', () => ({ PieChart: () => null }));

jest.mock('../../../hooks/useCurrency', () => ({
  useCurrency: () => ({
    displayCurrency: 'AUD',
    exchangeRate: 1,
    formatDisplayCurrency: (value?: number) => (value === undefined ? '—' : `$${value.toFixed(2)}`),
    isLoading: false,
  }),
}));

import { AssetAllocationCard } from './AssetAllocationCard';

const SUMMARY: HoldingsSummary = { totalValue: 400, holdingsCount: 2, walletsCount: 2, byAssetType: [] };

function item(overrides: Partial<AssetAllocationItem> = {}): AssetAllocationItem {
  return {
    assetUuid: 'asset-usdc',
    symbol: 'USDC',
    name: 'USD Coin',
    totalValue: 400,
    percentage: 100,
    basis: 'value',
    source: 'market',
    color: '#112233',
    totalQuantity: 400,
    perChain: [
      { chain: 'ethereum', quantity: 300, totalValue: 300, priced: true },
      { chain: 'base', quantity: 100, totalValue: 100, priced: true },
    ],
    ...overrides,
  };
}

function show(allocation: AssetAllocationItem[]) {
  return render(
    <AssetAllocationCard
      assetAllocation={allocation}
      totalValue={400}
      summary={SUMMARY}
      isLoading={false}
      hasError={false}
      onAssetClick={() => {}}
    />,
  );
}

describe('one coin held on two chains, on the mobile card', () => {
  it('lists one line, whatever it is spread over', async () => {
    const view = await show([item()]);

    expect(view.getAllByText('USD Coin')).toHaveLength(1);
  });

  it('offers the split, and does not open it until it is asked to', async () => {
    const view = await show([item()]);

    expect(view.queryByText('ethereum')).toBeNull();
    await fireEvent.press(view.getByLabelText('Show USDC by chain'));

    expect(view.getByText('ethereum')).toBeTruthy();
    expect(view.getByText('base')).toBeTruthy();
  });

  it('splits the quantity and the value the line summed', async () => {
    const view = await show([item()]);
    await fireEvent.press(view.getByLabelText('Show USDC by chain'));

    expect(view.getByText('$300.00')).toBeTruthy();
    expect(view.getByText('$100.00')).toBeTruthy();
  });

  it('closes again, so the row is a toggle', async () => {
    const view = await show([item()]);
    await fireEvent.press(view.getByLabelText('Show USDC by chain'));
    await fireEvent.press(view.getByLabelText('Hide USDC by chain'));

    expect(view.queryByText('ethereum')).toBeNull();
  });

  it('says which chain could not be priced', async () => {
    const view = await show([
      item({
        perChain: [
          { chain: 'ethereum', quantity: 300, totalValue: 300, priced: true },
          { chain: 'base', quantity: 100, totalValue: 0, priced: false },
        ],
      }),
    ]);
    await fireEvent.press(view.getByLabelText('Show USDC by chain'));

    expect(view.getByText('unpriced')).toBeTruthy();
  });
});

describe('a coin held on one chain, on the mobile card', () => {
  it('offers no expansion, so most rows look exactly as they did', async () => {
    const view = await show([item({ perChain: [{ chain: 'base', quantity: 400, totalValue: 400, priced: true }] })]);

    expect(view.queryByLabelText('Show USDC by chain')).toBeNull();
    expect(view.queryByText('base')).toBeNull();
  });
});

describe('the source of each mobile list valuation', () => {
  it.each([
    ['market', 'Market price'],
    ['nav', 'NAV'],
    ['par', 'Par value'],
  ] as const)('shows %s with its actual value', async (source, label) => {
    const view = await show([item({ source })]);
    expect(view.getByText(label)).toBeTruthy();
    expect(view.getByText('$400.00')).toBeTruthy();
  });

  it('shows unpriced provenance beside a real quantity percentage', async () => {
    const view = await show([item({ source: 'unpriced', basis: 'quantity', totalValue: 0 })]);
    expect(view.getByText('Unpriced')).toBeTruthy();
    expect(view.getByText('100.0%')).toBeTruthy();
    expect(view.queryByText('$0.00')).toBeNull();
  });
});
