// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { focusManager, onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { FeatureFlag } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFeatureFlags } from './useFeatureFlags';

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn() } }));

const get = vi.mocked(apiClient.get);
let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
});

afterEach(() => {
  cleanup();
  client.clear();
  get.mockReset();
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
});

function flag(overrides: Partial<FeatureFlag> = {}): FeatureFlag {
  return {
    uuid: 'synthetic-flag',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    name: 'trading_enabled',
    description: '',
    enabled: true,
    platform: 'all',
    minAppVersion: '',
    ...overrides,
  };
}

function response(flags: FeatureFlag[]) {
  return { data: { count: flags.length, next: null, previous: null, results: flags } };
}

function wrapper({ children }: PropsWithChildren) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function loadFlags(flags: FeatureFlag[]) {
  get.mockResolvedValue(response(flags) as never);
  const { result } = renderHook(() => useFeatureFlags(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  return result;
}

describe('dashboard feature flags', () => {
  it('reports enabled trading and requests the existing endpoint', async () => {
    const result = await loadFlags([flag()]);
    expect(result.current.tradingEnabled).toBe(true);
    expect(get).toHaveBeenCalledWith('/api/feature-flags/');
  });

  it('rejects a disabled flag delivered in the payload', async () => {
    const result = await loadFlags([flag({ enabled: false })]);
    expect(result.current.tradingEnabled).toBe(false);
  });

  it.each([
    [false, true],
    [true, false],
  ] as const)('preserves any-enabled-match for duplicate names (%s, %s)', async (first, second) => {
    const result = await loadFlags([flag({ enabled: first }), flag({ enabled: second })]);
    expect(result.current.tradingEnabled).toBe(true);
  });

  it('does not use an enabled flag with another name', async () => {
    const result = await loadFlags([flag({ name: 'another_feature' })]);
    expect(result.current.tradingEnabled).toBe(false);
  });

  it('preserves dashboard behavior for mobile-targeted minimum-version metadata', async () => {
    const result = await loadFlags([flag({ platform: 'ios', minAppVersion: '99.0.0' })]);
    expect(result.current.tradingEnabled).toBe(true);
  });

  it('keeps trading disabled until the first request settles', async () => {
    let release!: (value: unknown) => void;
    get.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }) as never,
    );
    const { result } = renderHook(() => useFeatureFlags(), { wrapper });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.tradingEnabled).toBe(false);

    await act(async () => {
      release(response([flag()]));
    });
    await waitFor(() => expect(result.current.tradingEnabled).toBe(true));
  });

  it('keeps trading disabled after an initial request failure', async () => {
    get.mockRejectedValue(new Error('Synthetic failure'));
    const { result } = renderHook(() => useFeatureFlags(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.tradingEnabled).toBe(false);
    expect(client.getQueryState(['featureFlags'])?.status).toBe('error');
  });

  it('shares the existing query between dashboard consumers', async () => {
    get.mockResolvedValue(response([flag()]) as never);
    const { result } = renderHook(() => [useFeatureFlags(), useFeatureFlags()], { wrapper });
    await waitFor(() => expect(result.current.every((flags) => flags.tradingEnabled)).toBe(true));
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('retains the dashboard stale-query focus and reconnect policy', async () => {
    const result = await loadFlags([flag()]);
    await client.invalidateQueries({ queryKey: ['featureFlags'], refetchType: 'none' });
    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));

    await client.invalidateQueries({ queryKey: ['featureFlags'], refetchType: 'none' });
    await act(async () => {
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.tradingEnabled).toBe(true);
  });

  it('retains cached flags when a later refetch fails', async () => {
    const result = await loadFlags([flag()]);
    get.mockRejectedValue(new Error('Synthetic refetch failure'));
    await act(async () => {
      await client.refetchQueries({ queryKey: ['featureFlags'] });
    });
    expect(client.getQueryState(['featureFlags'])?.status).toBe('error');
    expect(result.current.tradingEnabled).toBe(true);
  });
});
