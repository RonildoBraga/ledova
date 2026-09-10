import React from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { useCompanyProfile } from './useCompanyProfile';

jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn(), patch: jest.fn() } }));

const get = jest.mocked(apiClient.get);
const patch = jest.mocked(apiClient.patch);
const summary = { uuid: 'company-1', name: 'Synthetic Company', status: 'draft', acn: '000000019' };
let client: QueryClient;

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } },
  });
});

afterEach(async () => {
  await cleanup();
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

it('preserves the real summary fallback when detail fails', async () => {
  const failure = new Error('detail unavailable');
  get.mockImplementation((url: string) => {
    if (url === '/api/v1/companies/') return Promise.resolve({ data: { results: [summary] } });
    if (url === '/api/v1/companies/company-1/stats/') return Promise.resolve({ data: { totalTokens: 2 } });
    return Promise.reject(failure);
  });
  const { result } = await renderHook(() => useCompanyProfile(), { wrapper });
  await waitFor(() => expect(result.current.error).toBe(failure));
  expect(result.current.company).toEqual(summary);
  expect(result.current.company).not.toHaveProperty('abn');
  expect(result.current.companyUuid).toBe('company-1');
});

it('uses fetched detail and invalidates after an update without treating its body as company detail', async () => {
  const detail = { ...summary, abn: 'test-abn', description: 'Fetched detail' };
  get.mockImplementation((url: string) =>
    Promise.resolve({
      data:
        url === '/api/v1/companies/' ? { results: [summary] } : url.endsWith('/stats/') ? { totalTokens: 2 } : detail,
    }),
  );
  patch.mockResolvedValue({ data: { name: 'Updated company', operatorWallet: null } });
  const invalidate = jest.spyOn(client, 'invalidateQueries');
  const { result } = await renderHook(() => useCompanyProfile(), { wrapper });
  await waitFor(() => expect(result.current.company?.abn).toBe('test-abn'));
  await act(async () => {
    await result.current.updateCompany({ name: 'Updated company' });
  });

  expect(patch).toHaveBeenCalledWith('/api/v1/companies/company-1/', { name: 'Updated company' });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['company'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['companies'] });
  expect(result.current.company).toEqual(detail);
});
