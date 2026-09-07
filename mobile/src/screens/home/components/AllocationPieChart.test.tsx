import type React from 'react';
import { render } from '@testing-library/react-native';
import type { AssetAllocationItem } from '@ledova/shared';

const drawn: { data: { value: number; color: string; text: string }[] }[] = [];

jest.mock('react-native-gifted-charts', () => ({
  PieChart: (props: {
    data: { value: number; color: string; text: string }[];
    centerLabelComponent?: () => React.ReactNode;
  }) => {
    drawn.push({ data: props.data });
    return props.centerLabelComponent ? props.centerLabelComponent() : null;
  },
}));

jest.mock('../../../hooks/useCurrency', () => ({
  useCurrency: () => ({
    displayCurrency: 'AUD',
    exchangeRate: 1,
    formatDisplayCurrency: (value?: number) => (value === undefined ? '—' : `$${value.toFixed(2)}`),
    isLoading: false,
  }),
}));

import { AllocationPieChart } from './AllocationPieChart';

function item(overrides: Partial<AssetAllocationItem>): AssetAllocationItem {
  return {
    assetUuid: 'asset-1',
    symbol: 'USDC',
    name: 'USD Coin',
    totalValue: 400,
    percentage: 40,
    basis: 'value',
    color: '#112233',
    totalQuantity: 400,
    perChain: [{ chain: 'base', quantity: 400, totalValue: 400, priced: true }],
    ...overrides,
  };
}

async function draw(data: AssetAllocationItem[], totalValue: number) {
  drawn.length = 0;
  const view = await render(<AllocationPieChart data={data} totalValue={totalValue} isLoading={false} />);
  return { ...drawn[drawn.length - 1], view };
}

beforeEach(() => {
  drawn.length = 0;
});

describe('what mobile hands its ring, rather than what the function returns', () => {
  it('draws each arc from the share the function chose, not from the value', async () => {
    const { data } = await draw(
      [
        item({ percentage: 75, totalValue: 3000 }),
        item({ assetUuid: 'asset-2', symbol: 'ETH', percentage: 25, totalValue: 1000 }),
      ],
      4000,
    );

    expect(data.map((arc) => arc.value)).toEqual([75, 25]);
    expect(data.map((arc) => arc.text)).toEqual(['USDC', 'ETH']);
  });

  it('leaves a zero share out of the ring rather than drawing an invisible arc', async () => {
    const { data } = await draw([item({ percentage: 100 }), item({ assetUuid: 'asset-2', percentage: 0 })], 400);

    expect(data).toHaveLength(1);
    expect(data[0].value).toBe(100);
  });

  it('carries each arc its own colour, so the list beside it can agree', async () => {
    const { data } = await draw([item({ color: '#abcdef', percentage: 100 })], 400);

    expect(data[0].color).toBe('#abcdef');
  });

  it('says beneath the total how many holdings it could not price', async () => {
    const { view } = await draw(
      [item({ percentage: 100 }), item({ assetUuid: 'asset-2', basis: 'unpriced', percentage: 0 })],
      400,
    );

    expect(view.getByText('excludes 1 unpriced')).toBeTruthy();
    expect(view.getByText('$400.00')).toBeTruthy();
  });
});
