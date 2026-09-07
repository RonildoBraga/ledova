// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { calculateAssetAllocation } from '@ledova/shared';
import type { HoldingWithWallet, HoldingsSummary } from '@ledova/shared';

const drawn: { data: { datasets: { data: number[] }[]; labels: string[] }; options: TooltipOptions }[] = [];

interface TooltipOptions {
  plugins: { tooltip: { callbacks: { label: (context: { dataIndex: number }) => string } } };
}

vi.mock('react-chartjs-2', () => ({
  Doughnut: (props: { data: (typeof drawn)[number]['data']; options: TooltipOptions }) => {
    drawn.push({ data: props.data, options: props.options });
    return null;
  },
}));

const { AssetAllocationCard } = await import('./AssetAllocationCard');

function holding(symbol: string, quantity: string, marketValue: string | null): HoldingWithWallet {
  return {
    uuid: `holding-${symbol}`,
    assetSymbol: symbol,
    assetName: `${symbol} Asset`,
    quantity,
    marketValue,
    asset: { uuid: `asset-${symbol}`, symbol, name: `${symbol} Asset` },
    walletInfo: { uuid: 'wallet', name: 'Wallet', address: '0x0', chain: 'base' },
  } as unknown as HoldingWithWallet;
}

function draw(holdings: HoldingWithWallet[], totalValue: number) {
  drawn.length = 0;
  const summary = {
    totalValue,
    holdingsCount: holdings.length,
    walletsCount: 1,
    byAssetType: [],
  } satisfies HoldingsSummary;
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AssetAllocationCard
        assetAllocation={calculateAssetAllocation(holdings, totalValue)}
        totalValue={totalValue}
        summary={summary}
        assetQuantities={{}}
        isLoading={false}
        hasError={false}
        onAssetClick={() => {}}
      />
    </QueryClientProvider>,
  );
  return { ...drawn[drawn.length - 1], view };
}

const UNPRICED = [holding('AAA', '30', null), holding('BBB', '10', null)];
const MIXED = [holding('SHARES', '10000', null), holding('USDC', '12', '12')];

beforeEach(() => {
  cleanup();
  drawn.length = 0;
});

describe('what the dashboard ring is handed, not what the function returns', () => {
  it('draws arcs from the shares the function chose, so the unpriced fallback reaches the ring', () => {
    const { data } = draw(UNPRICED, 0);

    expect(data.labels).toEqual(['AAA', 'BBB']);
    expect(data.datasets[0].data).toEqual([75, 25]);
  });

  it('agrees with the list beneath it, which reads the same shares', () => {
    const { data, view } = draw(UNPRICED, 0);

    expect(data.datasets[0].data).toEqual([75, 25]);
    expect(view.getByText('75.0%')).toBeTruthy();
    expect(view.getByText('25.0%')).toBeTruthy();
  });

  it('names the basis in the tooltip rather than dividing by a total of zero', () => {
    const { options } = draw(UNPRICED, 0);

    expect(options.plugins.tooltip.callbacks.label({ dataIndex: 0 })).toBe('AAA: unpriced (75.0% by quantity)');
  });

  it('draws the priced share of a mixed portfolio and leaves the 0% slice out of the ring', () => {
    const { data } = draw(MIXED, 12);

    expect(data.labels).toEqual(['USDC']);
    expect(data.datasets[0].data).toEqual([100]);
  });

  it('says the total excludes what it could not price', () => {
    const { view } = draw(MIXED, 12);

    expect(view.getByText('excludes 1 unpriced holding')).toBeTruthy();
    expect(view.getByText('unpriced')).toBeTruthy();
  });

  it('prints no percentage beside unpriced, so the label has no number arguing with it', () => {
    const { view } = draw(MIXED, 12);

    expect(view.container.textContent).toContain('SHARES Assetunpriced—');
    expect(view.container.textContent).not.toContain('unpriced0.0%');
  });

  it('keeps the percentage when the whole page is weighed by quantity, since then it means something', () => {
    const { view } = draw(UNPRICED, 0);

    expect(view.container.textContent).toContain('AAA Assetunpriced75.0%');
    expect(view.container.textContent).toContain('BBB Assetunpriced25.0%');
  });
});
