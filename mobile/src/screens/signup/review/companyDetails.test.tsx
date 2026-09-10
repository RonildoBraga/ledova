import React from 'react';
import { act, cleanup, fireEvent, render, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { useReview } from './useReview';
import { ReviewScreen } from './index';

let mockCompany = true;
const mockReset = jest.fn();
jest.mock('../../../services/apiClient', () => ({ apiClient: { get: jest.fn(), patch: jest.fn() } }));
jest.mock('../../../hooks/useRole', () => ({ useRole: () => ({ isCompany: mockCompany }) }));
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useNavigation: () => ({ reset: mockReset, navigate: jest.fn() }),
}));
jest.mock('@ledova/shared', () => ({
  ...jest.requireActual('@ledova/shared'),
  useFinancialProfile: () => ({
    financialProfile: { uuid: 'financial-a', occupation: 'Engineer', sourceOfFunds: [], intendedUse: 'savings' },
    isLoading: false,
    error: null,
  }),
}));
const api = jest.mocked(apiClient);

const summaryA = { uuid: 'company-a', name: 'Saved A', companyType: 'pty', acn: '000000019' };
const summaryB = { ...summaryA, uuid: 'company-b', name: 'Saved B' };
const detailA = { ...summaryA, abn: '51824753556' };
const detailB = { ...summaryB, abn: '53004085616' };
const list = (rows = [summaryA]) => ({ data: { count: rows.length, next: null, previous: null, results: rows } });
let client: QueryClient;
let companyList: () => Promise<ReturnType<typeof list>>;
let companyA: () => Promise<{ data: typeof detailA }>;
let companyB: () => Promise<{ data: typeof detailB }>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockCompany = true;
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } },
  });
  companyList = () => Promise.resolve(list());
  companyA = () => Promise.resolve({ data: detailA });
  companyB = () => Promise.resolve({ data: detailB });
  api.get.mockImplementation((url: string) => {
    if (url === '/api/user-profiles/')
      return Promise.resolve({
        data: {
          results: [
            { uuid: 'profile-a', fullName: 'Synthetic Person', phoneNumber: '00000000', residentialAddress: null },
          ],
        },
      });
    if (url === '/api/v1/companies/') return companyList();
    if (url === '/api/v1/companies/company-a/') return companyA();
    if (url === '/api/v1/companies/company-b/') return companyB();
    throw new Error(`Unexpected request: ${url}`);
  });
  api.patch.mockResolvedValue({ data: { uuid: 'profile-a' } });
});

afterEach(async () => {
  await cleanup();
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

it('waits for company detail before review can complete', async () => {
  const pending = deferred<{ data: typeof detailA }>();
  companyA = () => pending.promise;
  const { result } = await renderHook(() => useReview(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  expect(result.current.isLoading).toBe(true);
  expect(result.current.company).toBeNull();
  await act(() => result.current.completeSignup());
  expect(api.patch).not.toHaveBeenCalled();
  await act(() => pending.resolve({ data: detailA }));
  await waitFor(() => expect(result.current.company?.abn).toBe(detailA.abn));
  expect(result.current.canCompleteSignup).toBe(true);
  await act(() => result.current.completeSignup());
  await waitFor(() => expect(mockReset).toHaveBeenCalled());
  expect(api.patch).toHaveBeenCalledWith('/api/user-profiles/profile-a/', {
    termsAndConditions: true,
    isSignupCompleted: true,
  });
});

it('does not show a late A detail after first-list selection moves to B', async () => {
  const pending = deferred<{ data: typeof detailA }>();
  companyA = () => pending.promise;
  const { result } = await renderHook(() => useReview(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  companyList = () => Promise.resolve(list([summaryB, summaryA]));
  await act(() => {
    client.setQueryData(['signup', 'company'], list([summaryB, summaryA]));
  });
  await waitFor(() => expect(result.current.company?.abn).toBe(detailB.abn));
  await act(() => pending.resolve({ data: detailA }));
  expect(result.current.company?.uuid).toBe('company-b');
  expect(result.current.company?.abn).toBe(detailB.abn);
});

it('rejects mismatched detail and keeps completion unavailable', async () => {
  companyA = () => Promise.resolve({ data: detailB });
  const { result } = await renderHook(() => useReview(), { wrapper });
  await waitFor(() => expect(result.current.error).toBeTruthy());
  expect(result.current.company).toBeNull();
  expect(result.current.canCompleteSignup).toBe(false);
  await act(() => result.current.completeSignup());
  expect(api.patch).not.toHaveBeenCalled();
});

it('does not confuse an empty company list with completed company review', async () => {
  companyList = () => Promise.resolve(list([]));
  const { result } = await renderHook(() => useReview(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(result.current.company).toBeNull();
  expect(result.current.canCompleteSignup).toBe(false);
  expect(api.get).not.toHaveBeenCalledWith('/api/v1/companies/company-a/');
});

it('ignores a cached company error while retaining investor completion', async () => {
  mockCompany = false;
  await client
    .fetchQuery({
      queryKey: ['signup', 'company'],
      queryFn: () => Promise.reject(new Error('Cached company failure')),
      retry: false,
    })
    .catch(() => undefined);
  const { result } = await renderHook(() => useReview(), { wrapper });
  await waitFor(() => expect(result.current.canCompleteSignup).toBe(true));
  expect(result.current.error).toBeNull();
  expect(result.current.company).toBeNull();
  expect(api.get).not.toHaveBeenCalledWith('/api/v1/companies/');
  await act(() => result.current.completeSignup());
  await waitFor(() => expect(mockReset).toHaveBeenCalled());
});

it('renders a separately fetched ABN after retrying the real review error screen', async () => {
  companyA = () => Promise.reject(new Error('Detail unavailable'));
  const view = await render(
    <QueryClientProvider client={client}>
      <ReviewScreen />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(view.getByText('Detail unavailable')).toBeTruthy());
  expect(view.queryByText(detailA.abn)).toBeNull();
  expect(api.patch).not.toHaveBeenCalled();
  companyA = () => Promise.resolve({ data: detailA });
  await fireEvent.press(view.getByText('Try Again'));
  await waitFor(() => expect(view.getByText(detailA.abn)).toBeTruthy());
  expect(view.queryByText('Detail unavailable')).toBeNull();
});
