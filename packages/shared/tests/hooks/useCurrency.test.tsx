/** @jest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import type { PropsWithChildren } from 'react';

import { ASSET_ENDPOINTS } from '../../src/constants/api';
import { ApiClientProvider } from '../../src/hooks/useApiClient';
import { AUTH_QUERY_KEY } from '../../src/hooks/useAuth';
import { useCurrency } from '../../src/hooks/useCurrency';
import { USER_PREFERENCES_QUERY_KEY } from '../../src/hooks/useUserPreferences';
import type { DisplayCurrency } from '../../src/types';

const clients: QueryClient[] = [];

function harness(authenticated: boolean, currency: DisplayCurrency = 'AUD') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(AUTH_QUERY_KEY, { data: { valid: authenticated } });
  client.setQueryData(USER_PREFERENCES_QUERY_KEY, { data: { displayCurrency: currency } });
  const apiClient = axios.create();
  const get = jest.spyOn(apiClient, 'get').mockResolvedValue({ data: { rate: '1.5' } });
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

describe('shared display currency', () => {
  it('does not request preferences or exchange rates while signed out', () => {
    const { get, wrapper } = harness(false);
    const { result } = renderHook(() => useCurrency(), { wrapper });

    expect(get).not.toHaveBeenCalled();
    expect(result.current.displayCurrency).toBe('AUD');
    expect(result.current.formatDisplayCurrency(10)).toBe('—');
  });

  it('starts the exchange-rate request once authentication is confirmed', async () => {
    const { client, get, wrapper } = harness(false);
    const { result } = renderHook(() => useCurrency(), { wrapper });
    expect(get).not.toHaveBeenCalled();

    await act(async () => {
      client.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
    });

    await waitFor(() => expect(result.current.exchangeRate).toBe(1.5));
    expect(get).toHaveBeenCalledWith(ASSET_ENDPOINTS.EXCHANGE_RATES, { params: { currency: 'AUD' } });
    expect(result.current.formatDisplayCurrency(10)).toBe('$15.00');
  });

  it('formats USD without requesting a conversion rate', () => {
    const { get, wrapper } = harness(true, 'USD');
    const { result } = renderHook(() => useCurrency(), { wrapper });

    expect(get).not.toHaveBeenCalled();
    expect(result.current.exchangeRate).toBe(1);
    expect(result.current.formatDisplayCurrency(10)).toBe('$10.00');
    expect(result.current.formatDisplayCurrency(0)).toBe('$0.00');
  });

  it('uses a newly selected currency instead of retaining the previous conversion', async () => {
    const { client, get, wrapper } = harness(true, 'USD');
    const { result } = renderHook(() => useCurrency(), { wrapper });

    await act(async () => {
      client.setQueryData(USER_PREFERENCES_QUERY_KEY, { data: { displayCurrency: 'AUD' } });
    });

    await waitFor(() => expect(result.current.formatDisplayCurrency(10)).toBe('$15.00'));
    expect(result.current.displayCurrency).toBe('AUD');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('shows an unavailable value when the exchange rate cannot be read', async () => {
    const { get, wrapper } = harness(true);
    get.mockRejectedValue(new Error('Rate unavailable'));
    const { result } = renderHook(() => useCurrency(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.exchangeRate).toBe(0);
    expect(result.current.formatDisplayCurrency(10)).toBe('—');
  });

  it('keeps missing values distinct from zero and honors display precision', () => {
    const { wrapper } = harness(true, 'USD');
    const { result } = renderHook(() => useCurrency(), { wrapper });

    for (const value of [undefined, null, NaN]) {
      expect(result.current.formatDisplayCurrency(value)).toBe('—');
    }
    expect(result.current.formatDisplayCurrency(1.2345, 3)).toBe('$1.235');
  });
});
