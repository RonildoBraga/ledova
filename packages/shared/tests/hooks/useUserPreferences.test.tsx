/** @jest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import type { PropsWithChildren } from 'react';

import { USER_PREFERENCES_ENDPOINTS } from '../../src/constants/api';
import { ApiClientProvider } from '../../src/hooks/useApiClient';
import { AUTH_QUERY_KEY } from '../../src/hooks/useAuth';
import { USER_PREFERENCES_QUERY_KEY, useUserPreferences } from '../../src/hooks/useUserPreferences';

const preferences = {
  displayCurrency: 'AUD',
  selectedAccount: { uuid: 'account-1' },
  selectedPortfolio: { uuid: 'portfolio-1' },
};
const clients: QueryClient[] = [];

function harness(authenticated: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(AUTH_QUERY_KEY, { data: { valid: authenticated } });
  const apiClient = axios.create();
  const get = jest.spyOn(apiClient, 'get').mockResolvedValue({ data: preferences });
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
  jest.restoreAllMocks();
});

describe('shared user preferences', () => {
  it('does not request or expose account preferences while signed out', () => {
    const { client, get, wrapper } = harness(false);
    client.setQueryData(USER_PREFERENCES_QUERY_KEY, { data: preferences });
    const { result } = renderHook(() => useUserPreferences(), { wrapper });

    expect(get).not.toHaveBeenCalled();
    expect(result.current.preferences).toBeUndefined();
    expect(result.current.selectedAccount).toBeNull();
    expect(result.current.selectedPortfolio).toBeNull();
  });

  it('loads the selected account and portfolio after authentication', async () => {
    const { client, get, wrapper } = harness(false);
    const { result } = renderHook(() => useUserPreferences(), { wrapper });
    expect(get).not.toHaveBeenCalled();

    await act(async () => {
      client.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
    });

    await waitFor(() => expect(result.current.preferences).toEqual(preferences));
    expect(get).toHaveBeenCalledWith(USER_PREFERENCES_ENDPOINTS.BASE);
    expect(result.current.selectedAccount).toEqual(preferences.selectedAccount);
    expect(result.current.selectedPortfolio).toEqual(preferences.selectedPortfolio);
  });

  it('does not expose a preferences response that arrives after sign-out', async () => {
    const { client, get, wrapper } = harness(true);
    let finish!: () => void;
    get.mockReturnValue(
      new Promise((resolve) => {
        finish = () => resolve({ data: preferences });
      }),
    );
    const { result } = renderHook(() => useUserPreferences(), { wrapper });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));

    await act(async () => {
      client.setQueryData(AUTH_QUERY_KEY, { data: { valid: false } });
      finish();
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toBeUndefined();
    expect(result.current.selectedAccount).toBeNull();
    expect(result.current.selectedPortfolio).toBeNull();
  });

  it('reports a failed read without inventing an account selection', async () => {
    const { get, wrapper } = harness(true);
    get.mockRejectedValue(new Error('Preferences unavailable'));
    const { result } = renderHook(() => useUserPreferences(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.selectedAccount).toBeNull();
    expect(result.current.selectedPortfolio).toBeNull();
  });
});
