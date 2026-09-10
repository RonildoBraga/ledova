import React from 'react';
import { act, renderHook } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { getSessionEpoch, invalidateSessionScope } from '../services/sessionScope';
import { useCompanyProfile } from './useCompanyProfile';
import { useCompanyDocuments } from '../screens/listing/useCompanyDocuments';
import { useInvestorEligibility } from '../screens/investor-eligibility/useInvestorEligibility';

jest.mock('../services/apiClient', () => ({
  apiClient: { get: jest.fn(async () => ({ data: {} })), post: jest.fn() },
}));
jest.mock('./useCompanyProfile', () => ({ useCompanyProfile: jest.fn() }));

const post = jest.mocked(apiClient.post);
let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } },
  });
  post.mockReset().mockResolvedValue({ data: {} });
  jest
    .mocked(useCompanyProfile)
    .mockReturnValue({ companyUuid: 'company-a', company: { status: 'draft' }, isLoading: false } as ReturnType<
      typeof useCompanyProfile
    >);
});

afterEach(() => {
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function pauseMutation() {
  let entered!: () => void;
  let resume!: () => void;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const resumed = new Promise<void>((resolve) => {
    resume = resolve;
  });
  client.setDefaultOptions({
    ...client.getDefaultOptions(),
    mutations: {
      retry: false,
      gcTime: 0,
      onMutate: async () => {
        entered();
        await resumed;
      },
    },
  });
  return { started, resume };
}

it('keeps the selected company and session after React Query replaces pending mutation options', async () => {
  const pause = pauseMutation();
  const invalidated = jest.spyOn(client, 'invalidateQueries');
  const view = await renderHook(() => useCompanyDocuments(), { wrapper });
  let pending!: Promise<unknown>;
  const epoch = getSessionEpoch();
  await act(async () => {
    pending = view.result.current!.upload({
      companyUuid: 'company-a',
      sessionEpoch: epoch,
      documentType: 'cert_inc',
      name: 'evidence.pdf',
      file: { uri: 'file:///synthetic', name: 'evidence.pdf', type: 'application/pdf' },
    });
    await pause.started;
  });
  jest
    .mocked(useCompanyProfile)
    .mockReturnValue({ companyUuid: 'company-b', company: { status: 'draft' }, isLoading: false } as ReturnType<
      typeof useCompanyProfile
    >);
  await view.rerender({});
  expect(post).not.toHaveBeenCalled();
  await act(async () => {
    pause.resume();
    await pending;
  });
  expect(post).toHaveBeenCalledWith(
    expect.stringContaining('/company-a/'),
    expect.any(FormData),
    expect.objectContaining({ ledovaSessionEpoch: epoch }),
  );
  expect(invalidated).toHaveBeenCalledWith({ queryKey: ['company-documents', 'company-a'] });
  expect(invalidated).not.toHaveBeenCalledWith({ queryKey: ['company-documents', 'company-b'] });
});

it('does not invalidate a newer session when an old company upload succeeds', async () => {
  let finish!: () => void;
  post.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = () => resolve({ data: {} });
      }),
  );
  const invalidated = jest.spyOn(client, 'invalidateQueries');
  const view = await renderHook(() => useCompanyDocuments(), { wrapper });
  let pending!: Promise<unknown>;
  await act(async () => {
    pending = view.result.current!.upload({
      companyUuid: 'company-a',
      sessionEpoch: getSessionEpoch(),
      documentType: 'cert_inc',
      name: 'evidence.pdf',
      file: {},
    });
  });
  expect(post).toHaveBeenCalledTimes(1);
  await act(async () => {
    invalidateSessionScope();
    finish();
    await pending;
  });
  expect(invalidated).not.toHaveBeenCalled();
});

it('forwards the eligibility session fence and suppresses stale completion invalidation', async () => {
  let finish!: () => void;
  post.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = () => resolve({ data: {} });
      }),
  );
  const invalidated = jest.spyOn(client, 'invalidateQueries');
  const view = await renderHook(() => useInvestorEligibility(), { wrapper });
  let pending!: Promise<unknown>;
  const epoch = getSessionEpoch();
  await act(async () => {
    pending = view.result.current!.submitClaim({
      userAccount: 'account-a',
      sessionEpoch: epoch,
      category: 'product_value',
      declaredBasis: 'Synthetic evidence',
      file: {},
    });
  });
  expect(post).toHaveBeenCalledWith(
    expect.any(String),
    expect.any(FormData),
    expect.objectContaining({ ledovaSessionEpoch: epoch }),
  );
  await act(async () => {
    invalidateSessionScope();
    finish();
    await pending;
  });
  expect(invalidated).not.toHaveBeenCalled();
});
