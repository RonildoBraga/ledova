// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const never = () => new Promise(() => {});
const resolved = (results: unknown[]) => () => Promise.resolve({ data: { results } });

vi.mock('@ledova/shared', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@ledova/shared');
  return {
    ...actual,
    getOfferings: resolved([{ uuid: 'offering-1' }]),
    getCompanyTokens: resolved([]),
    getOperator: never,
  };
});

const { useOfferings } = await import('./useOffering');

function Probe() {
  const { offerings, isLoading } = useOfferings();
  return (
    <span>
      offerings:{offerings.length} {isLoading ? 'loading' : 'ready'}
    </span>
  );
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  );
}

describe('useOfferings loading state', () => {
  afterEach(cleanup);

  it('is still loading after the other queries answer, while the operator has not', async () => {
    mount();

    await screen.findByText(/offerings:1/);

    expect(screen.getByText(/loading/)).toBeDefined();
    expect(screen.queryByText(/ready/)).toBeNull();
  });
});
