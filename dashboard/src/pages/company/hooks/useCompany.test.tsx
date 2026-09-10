// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useCompany } from './useCompany';

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));

const summary = { uuid: 'company-1', name: 'Synthetic Company', status: 'draft', acn: '000000019' };
let client: QueryClient;

beforeEach(() => {
  api.get.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  cleanup();
  client.clear();
});

function wrapper({ children }: PropsWithChildren) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function responses(detail: () => Promise<unknown>) {
  api.get.mockImplementation((url: string) => {
    if (url === '/api/v1/companies/') return Promise.resolve({ data: { results: [summary] } });
    if (url === '/api/v1/companies/company-1/stats/') return Promise.resolve({ data: { totalTokens: 2 } });
    if (url === '/api/v1/companies/company-1/') return detail();
    throw new Error(`Unexpected request: ${url}`);
  });
}

it('keeps the summary while detail is pending, then exposes the detail without inventing list fields', async () => {
  let resolve: (value: unknown) => void = () => {};
  const pending = new Promise((done) => {
    resolve = done;
  });
  responses(() => pending);
  const { result } = renderHook(() => useCompany(), { wrapper });
  await waitFor(() => expect(result.current.company).toEqual(summary));
  expect(result.current.company).not.toHaveProperty('abn');

  const detail = { ...summary, abn: 'test-abn', description: 'Fetched detail' };
  await act(async () => {
    resolve({ data: detail });
  });
  await waitFor(() => expect(result.current.company).toEqual(detail));
  expect(result.current.company?.abn).toBe('test-abn');
});

it('preserves the summary and reports the error when the detail request fails', async () => {
  const failure = new Error('detail unavailable');
  responses(() => Promise.reject(failure));
  const { result } = renderHook(() => useCompany(), { wrapper });
  await waitFor(() => expect(result.current.error).toBe(failure));
  expect(result.current.company).toEqual(summary);
  expect(result.current.company).not.toHaveProperty('abn');
  expect(result.current.companyUuid).toBe('company-1');
});
