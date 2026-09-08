/** @jest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { focusManager, onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import type { PropsWithChildren } from 'react';

import { AUTH_ENDPOINTS } from '../../src/constants/api';
import { ApiClientProvider } from '../../src/hooks/useApiClient';
import { AUTH_QUERY_KEY, useAuth } from '../../src/hooks/useAuth';

const clients: QueryClient[] = [];

function harness(focus = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: focus } } });
  const apiClient = axios.create();
  const get = jest.spyOn(apiClient, 'get').mockResolvedValue({ data: { valid: true } });
  clients.push(client);
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>
      <ApiClientProvider client={apiClient}>{children}</ApiClientProvider>
    </QueryClientProvider>
  );
  return { client, get, wrapper };
}

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
  jest.restoreAllMocks();
});

describe('shared authentication follows the client refetch policy', () => {
  it.each([
    ['dashboard', true, 2],
    ['mobile', false, 1],
  ] as const)('%s rechecks on focus according to its own policy', async (_name, focus, expected) => {
    const { client, get, wrapper } = harness(focus);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
    expect(get).toHaveBeenCalledWith(AUTH_ENDPOINTS.VERIFY);
    await client.invalidateQueries({ queryKey: AUTH_QUERY_KEY, refetchType: 'none' });

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await waitFor(() => expect(get).toHaveBeenCalledTimes(expected));
    expect(result.current.isAuthenticated).toBe(true);
  });

  it.each([true, false])('rechecks a stale session on reconnect with focus policy %s', async (focus) => {
    const { client, get, wrapper } = harness(focus);
    renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await client.invalidateQueries({ queryKey: AUTH_QUERY_KEY, refetchType: 'none' });

    await act(async () => {
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('recovers a failed verification on a later mount without retrying it in a loop', async () => {
    const { get, wrapper } = harness();
    get.mockRejectedValueOnce(new Error('Network unavailable'));
    const first = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(first.result.current.isFetching).toBe(false));
    expect(first.result.current.isAuthenticated).toBe(false);
    expect(get).toHaveBeenCalledTimes(1);
    first.unmount();

    const second = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(second.result.current.isAuthenticated).toBe(true));
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('shares one session check between consumers of the same client', async () => {
    const { get, wrapper } = harness();
    const { result } = renderHook(() => [useAuth(), useAuth()], { wrapper });

    await waitFor(() => expect(result.current.every((auth) => auth.isAuthenticated)).toBe(true));
    expect(get).toHaveBeenCalledTimes(1);
  });
});
