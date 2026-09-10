import React from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { focusManager, onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { FeatureFlag } from '@ledova/shared';
import { useFeatureFlags } from './useFeatureFlags';
import { apiClient } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn() } }));
jest.mock('expo-constants', () => ({
  get expoConfig() {
    return { name: 'Ledova', slug: 'ledova', version: '1.2.3' };
  },
}));

const get = apiClient.get as jest.Mock;

let client: QueryClient;

beforeEach(() => {
  get.mockReset();
  jest.replaceProperty(Platform, 'OS', 'ios');
  jest.spyOn(Constants, 'expoConfig', 'get').mockReturnValue({ name: 'Ledova', slug: 'ledova', version: '1.2.3' });
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchOnWindowFocus: true, refetchOnReconnect: false },
    },
  });
});

afterEach(async () => {
  await cleanup();
  client.clear();
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
});

function flag(overrides: Partial<FeatureFlag>): FeatureFlag {
  return {
    uuid: 'flag-uuid',
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

  it.each([
    [false, true],
    [true, false],
  ] as const)('preserves any-enabled-match for duplicate names (%s, %s)', async (first, second) => {
    const result = await loadFlags([flag({ enabled: first }), flag({ enabled: second })]);
    expect(result.current?.isEnabled('trading_enabled')).toBe(true);
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

  it.each(['ios', 'android'] as const)('supplies the actual %s platform to the shared reader', async (platform) => {
    jest.replaceProperty(Platform, 'OS', platform);
    const other = platform === 'ios' ? 'android' : 'ios';
    const result = await loadFlags([
      flag({ name: 'matching', platform }),
      flag({ name: 'other', platform: other }),
      flag({ name: 'mobile', platform: 'mobile' }),
    ]);

    expect(result.current?.isEnabled('matching')).toBe(true);
    expect(result.current?.isEnabled('other')).toBe(false);
    expect(result.current?.isEnabled('mobile')).toBe(true);
  });

  it('supplies the current Expo version and retains eligible disabled entries', async () => {
    const disabled = flag({ name: 'disabled', minAppVersion: '1.2.3', enabled: false });
    const result = await loadFlags([
      flag({ name: 'matching', minAppVersion: '1.2.3' }),
      flag({ name: 'future', minAppVersion: '1.2.4' }),
      disabled,
    ]);

    expect(result.current?.isEnabled('matching')).toBe(true);
    expect(result.current?.isEnabled('future')).toBe(false);
    expect(result.current?.isEnabled('disabled')).toBe(false);
    expect(result.current?.flags).toContainEqual(disabled);
    expect(jest.spyOn(Constants, 'expoConfig', 'get')).toHaveBeenCalled();
  });

  it('preserves missing Expo version behavior', async () => {
    jest.spyOn(Constants, 'expoConfig', 'get').mockReturnValue(null);
    const result = await loadFlags([flag({ minAppVersion: '99.0.0' })]);
    expect(result.current?.isEnabled('trading_enabled')).toBe(true);
  });

  it('does not read Expo config for empty, unversioned or excluded flags', async () => {
    const readConfig = jest.spyOn(Constants, 'expoConfig', 'get').mockImplementation(() => {
      throw new Error('Synthetic manifest unavailable');
    });
    const result = await loadFlags([flag({}), flag({ platform: 'web', minAppVersion: '2.0.0' })]);

    expect(result.current?.isEnabled('trading_enabled')).toBe(true);
    expect(readConfig).not.toHaveBeenCalled();
  });

  it('keeps stale mobile queries paused on focus and refetches on reconnect', async () => {
    await loadFlags([flag({ enabled: true })]);
    await client.invalidateQueries({ queryKey: ['featureFlags'], refetchType: 'none' });
    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    expect(get).toHaveBeenCalledTimes(1);

    await act(async () => {
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('retains cached flags when a later refetch fails', async () => {
    const result = await loadFlags([flag({ enabled: true })]);
    get.mockRejectedValue(new Error('Synthetic refetch failure'));
    await act(async () => {
      await result.current?.refetch();
    });
    await waitFor(() => expect(result.current?.isError).toBe(true));
    expect(result.current?.isEnabled('trading_enabled')).toBe(true);
  });
});
