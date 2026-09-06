import React from 'react';
import { renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { FeatureFlag } from '@ledova/shared';
import { useFeatureFlags } from './useFeatureFlags';
import { apiClient } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn() } }));

const get = apiClient.get as jest.Mock;

let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
});

afterEach(() => {
  client.clear();
});

function flag(overrides: Partial<FeatureFlag>): FeatureFlag {
  return {
    uuid: 'flag-uuid',
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

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function renderFlags() {
  const { result } = await renderHook(() => useFeatureFlags(), { wrapper });

  return result;
}

async function loadFlags(flags: FeatureFlag[]) {
  get.mockResolvedValue({ data: { count: flags.length, next: null, previous: null, results: flags } });
  const result = await renderFlags();
  await waitFor(() => expect(result.current?.isLoading).toBe(false));

  return result;
}

describe('useFeatureFlags', () => {
  it('reports an enabled flag as enabled', async () => {
    const result = await loadFlags([flag({ enabled: true })]);

    expect(result.current?.isEnabled('trading_enabled')).toBe(true);
  });

  it('reports a disabled flag as disabled even though it arrived in the payload', async () => {
    const result = await loadFlags([flag({ enabled: false })]);

    expect(result.current?.isEnabled('trading_enabled')).toBe(false);
  });

  it('reports an absent flag as disabled', async () => {
    const result = await loadFlags([]);

    expect(result.current?.isEnabled('trading_enabled')).toBe(false);
  });

  it('drops a web-only flag on a mobile client', async () => {
    const result = await loadFlags([flag({ platform: 'web' })]);

    expect(result.current?.isEnabled('trading_enabled')).toBe(false);
  });

  it('treats everything as disabled while the request is still in flight', async () => {
    let release: (payload: unknown) => void = () => {};
    get.mockReturnValue(new Promise((resolve) => (release = resolve)));
    const result = await renderFlags();

    await waitFor(() => expect(result.current?.isLoading).toBe(true));
    expect(result.current?.isEnabled('trading_enabled')).toBe(false);

    release({ data: { count: 1, next: null, previous: null, results: [flag({ enabled: true })] } });
    await waitFor(() => expect(result.current?.isEnabled('trading_enabled')).toBe(true));
  });

  it('treats everything as disabled when the request fails, so a flag cannot fail open', async () => {
    get.mockRejectedValue(new Error('network down'));
    const result = await renderFlags();

    await waitFor(() => expect(result.current?.isError).toBe(true));
    expect(result.current?.isEnabled('trading_enabled')).toBe(false);
  });
});
