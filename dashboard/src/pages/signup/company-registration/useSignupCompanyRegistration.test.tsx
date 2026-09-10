// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, fireEvent, render, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useSignupCompanyRegistration } from './useSignupCompanyRegistration';
import { SignupCompanyRegistration } from './SignupCompanyRegistration';
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('@components/AuthLayout', () => ({
  AuthLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));

const summaryA = {
  uuid: 'company-a',
  name: 'Saved Company A',
  tradingName: 'Trading A',
  displayName: 'Saved Company A',
  companyType: 'pty',
  companyTypeDisplay: 'Proprietary',
  acn: '000000019',
  status: 'draft',
  statusDisplay: 'Draft',
  industry: '',
  city: '',
  state: '',
  isActive: false,
  isApproved: false,
  createdAt: '2026-01-01T00:00:00Z',
};
const summaryB = { ...summaryA, uuid: 'company-b', name: 'Saved Company B', tradingName: 'Trading B' };
const detailA = { ...summaryA, abn: '51824753556' };
const detailB = { ...summaryB, abn: '53004085616' };
const listKey = ['signup', 'company'];
const detailKey = (uuid: string) => ['signup', 'company-detail', uuid];
const list = (rows = [summaryA]) => ({ data: { count: rows.length, next: null, previous: null, results: rows } });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

let client: QueryClient;
let companyList: () => Promise<ReturnType<typeof list>>;
let companyA: () => Promise<{ data: typeof detailA }>;
let companyB: () => Promise<{ data: typeof detailB }>;

beforeEach(() => {
  vi.clearAllMocks();
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
            { uuid: 'profile-a', fullName: 'Synthetic Person', phoneNumber: '00000000', phoneCountryCode: '+61' },
          ],
        },
      });
    if (url === '/api/v1/companies/') return companyList();
    if (url === '/api/v1/companies/company-a/') return companyA();
    if (url === '/api/v1/companies/company-b/') return companyB();
    throw new Error(`Unexpected request: ${url}`);
  });
  api.patch.mockResolvedValue({ data: { name: 'Saved Company A', abn: detailA.abn } });
  api.post.mockResolvedValue({ data: { message: 'Registered', company: detailA } });
});

afterEach(async () => {
  await cleanup();
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function loaded() {
  const view = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(view.result.current.form.abn).toBe(detailA.abn));
  return view;
}

it('waits for the selected detail, then prefills ABN and saves that detail', async () => {
  const pending = deferred<{ data: typeof detailA }>();
  companyA = () => pending.promise;
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  expect(result.current.isLoading).toBe(true);
  expect(result.current.form.abn).toBe('');
  const saved = vi.fn();
  await act(() => result.current.handleSubmit(saved));
  expect(api.patch).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
  await act(() => pending.resolve({ data: detailA }));
  await waitFor(() => expect(result.current.form.abn).toBe(detailA.abn));
  await act(() => result.current.handleSubmit(saved));
  expect(api.patch).toHaveBeenCalledWith('/api/v1/companies/company-a/', {
    name: detailA.name,
    tradingName: detailA.tradingName,
    companyType: 'pty',
    acn: '000000019',
    abn: detailA.abn,
  });
  expect(saved).toHaveBeenCalledTimes(1);
});

it('preserves dirty fields and an emptied ABN while refreshing untouched fields', async () => {
  const { result } = await loaded();
  await act(() => {
    result.current.setFieldValue('name', 'Unsaved name');
    result.current.setFieldValue('abn', '');
  });
  companyA = () =>
    Promise.resolve({ data: { ...detailA, name: 'Remote name', tradingName: 'Fresh trading name', abn: detailB.abn } });
  await act(() => client.refetchQueries({ queryKey: detailKey('company-a') }));
  await waitFor(() => expect(result.current.form.tradingName).toBe('Fresh trading name'));
  expect(result.current.form.name).toBe('Unsaved name');
  expect(result.current.form.abn).toBe('');
  expect(api.patch).not.toHaveBeenCalled();
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.patch).toHaveBeenCalledWith(
    '/api/v1/companies/company-a/',
    expect.objectContaining({ name: 'Unsaved name', abn: undefined }),
  );
});

it('preserves edits accepted before the first detail response', async () => {
  const pending = deferred<{ data: typeof detailA }>();
  companyA = () => pending.promise;
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  await act(() => result.current.setFieldValue('name', 'Typed during loading'));
  await act(() => pending.resolve({ data: detailA }));
  await waitFor(() => expect(result.current.form.abn).toBe(detailA.abn));
  expect(result.current.form.name).toBe('Typed during loading');
});

it('retires A immediately and ignores its late detail after the first list selection changes to B', async () => {
  const pendingA = deferred<{ data: typeof detailA }>();
  const pendingB = deferred<{ data: typeof detailB }>();
  companyA = () => pendingA.promise;
  companyB = () => pendingB.promise;
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  await act(() => result.current.setFieldValue('name', 'Unsent A'));
  await act(() => {
    companyList = () => Promise.resolve(list([summaryB, summaryA]));
    client.setQueryData(listKey, list([summaryB, summaryA]));
  });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-b/'));
  expect(result.current.form.name).not.toBe('Unsent A');
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.patch).not.toHaveBeenCalled();
  await act(() => pendingB.resolve({ data: detailB }));
  await waitFor(() => expect(result.current.form.abn).toBe(detailB.abn));
  await act(() => pendingA.resolve({ data: detailA }));
  expect(result.current.form.abn).toBe(detailB.abn);
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.patch).toHaveBeenCalledWith(
    '/api/v1/companies/company-b/',
    expect.objectContaining({ name: detailB.name, abn: detailB.abn }),
  );
});

it('does not hydrate a different UUID returned from the selected detail endpoint', async () => {
  companyA = () => Promise.resolve({ data: detailB });
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(result.current.loadError).toBeTruthy());
  expect(result.current.form.abn).toBe('');
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.patch).not.toHaveBeenCalled();
});

it('keeps a failed detail unresolved and recovers through the real retry path', async () => {
  companyA = () => Promise.reject(new Error('Detail unavailable'));
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(result.current.loadError).toBe('Detail unavailable'));
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.patch).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
  companyA = () => Promise.resolve({ data: detailA });
  await act(() => result.current.retryLoad());
  await waitFor(() => expect(result.current.form.abn).toBe(detailA.abn));
  expect(result.current.loadError).toBeNull();
});

it('preserves dirty input after a background failure and explicit retry', async () => {
  const { result } = await loaded();
  await act(() => result.current.setFieldValue('abn', detailB.abn));
  companyA = () => Promise.reject(new Error('Refresh unavailable'));
  await act(() => client.refetchQueries({ queryKey: detailKey('company-a') }));
  await waitFor(() => expect(result.current.loadError).toBe('Refresh unavailable'));
  expect(result.current.form.abn).toBe(detailB.abn);
  companyA = () => Promise.resolve({ data: { ...detailA, tradingName: 'Recovered' } });
  await act(() => result.current.retryLoad());
  await waitFor(() => expect(result.current.form.tradingName).toBe('Recovered'));
  expect(result.current.form.abn).toBe(detailB.abn);
});

it('does not mistake a failed list load for a new registration', async () => {
  companyList = () => Promise.reject(new Error('List unavailable'));
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await act(() => {
    result.current.setFieldValue('name', 'New input');
    result.current.setFieldValue('acn', '000000019');
  });
  await act(() => result.current.handleSubmit(vi.fn()));
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.loadError).toBe('List unavailable');
});

it('retains new registration, empty-ABN omission and its ordinary invalidations', async () => {
  companyList = () => Promise.resolve(list([]));
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await act(() => {
    result.current.setFieldValue('name', 'New company');
    result.current.setFieldValue('acn', '000 000 019');
  });
  const saved = vi.fn();
  await act(() => result.current.handleSubmit(saved));
  expect(api.post).toHaveBeenCalledWith('/api/v1/companies/', {
    name: 'New company',
    tradingName: undefined,
    companyType: 'pty',
    acn: '000000019',
    abn: undefined,
    primaryContact: { firstName: 'Synthetic', lastName: 'Person', phone: '+61 00000000' },
  });
  expect(api.patch).not.toHaveBeenCalled();
  expect(saved).toHaveBeenCalledTimes(1);
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['auth'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['userPreferences'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: listKey });
});

it.each(['success', 'failure'])('ignores a late A save %s after B is selected', async (outcome) => {
  const pending = deferred<{ data: { name: string } }>();
  api.patch.mockReturnValue(pending.promise);
  const { result } = await loaded();
  const saved = vi.fn();
  let submitting!: Promise<void>;
  await act(() => {
    submitting = result.current.handleSubmit(saved);
  });
  await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
  await act(() => {
    companyList = () => Promise.resolve(list([summaryB]));
    client.setQueryData(listKey, list([summaryB]));
  });
  await waitFor(() => expect(result.current.form.abn).toBe(detailB.abn));
  await act(async () => {
    if (outcome === 'success') pending.resolve({ data: { name: 'Saved A' } });
    else pending.reject({ response: { data: { error: 'A save refused' } } });
    await submitting;
  });
  expect(saved).not.toHaveBeenCalled();
  expect(result.current.generalError).toBe('');
  expect(result.current.form.name).toBe(detailB.name);
});

it('does not complete a stale A save after selection changes A to B to A', async () => {
  const pending = deferred<{ data: { name: string } }>();
  api.patch.mockReturnValue(pending.promise);
  const { result } = await loaded();
  const saved = vi.fn();
  let submitting!: Promise<void>;
  await act(() => {
    submitting = result.current.handleSubmit(saved);
  });
  await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
  await act(() => {
    companyList = () => Promise.resolve(list([summaryB]));
    client.setQueryData(listKey, list([summaryB]));
  });
  await waitFor(() => expect(result.current.form.abn).toBe(detailB.abn));
  await act(() => {
    companyList = () => Promise.resolve(list());
    client.setQueryData(listKey, list());
  });
  await waitFor(() => expect(result.current.form.abn).toBe(detailA.abn));
  await act(async () => {
    pending.resolve({ data: { name: 'Saved A' } });
    await submitting;
  });
  expect(saved).not.toHaveBeenCalled();
});

it('preserves a genuine registration success when the created company appears in the list', async () => {
  companyList = () => Promise.resolve(list([]));
  const pending = deferred<{ data: { message: string; company: typeof detailA } }>();
  api.post.mockReturnValue(pending.promise);
  const { result } = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await act(() => {
    result.current.setFieldValue('name', 'New company');
    result.current.setFieldValue('acn', '000000019');
  });
  const saved = vi.fn();
  let submitting!: Promise<void>;
  await act(() => {
    submitting = result.current.handleSubmit(saved);
  });
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  companyList = () => Promise.resolve(list());
  await act(() => {
    companyList = () => Promise.resolve(list());
    client.setQueryData(listKey, list());
  });
  await waitFor(() => expect(result.current.form.abn).toBe(detailA.abn));
  await act(async () => {
    pending.resolve({ data: { message: 'Registered', company: detailA } });
    await submitting;
  });
  expect(saved).toHaveBeenCalledTimes(1);
});

it('does not navigate when a save resolves after unmount', async () => {
  const pending = deferred<{ data: { name: string } }>();
  api.patch.mockReturnValue(pending.promise);
  const { result, unmount } = await loaded();
  const saved = vi.fn();
  let submitting!: Promise<void>;
  await act(() => {
    submitting = result.current.handleSubmit(saved);
  });
  await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
  unmount();
  await act(async () => {
    pending.resolve({ data: { name: 'Saved A' } });
    await submitting;
  });
  expect(saved).not.toHaveBeenCalled();
});

it('keeps identifier validation and a current save failure without clearing edits', async () => {
  const { result } = await loaded();
  const saved = vi.fn();
  await act(() => result.current.setFieldValue('abn', 'short'));
  await act(() => result.current.handleSubmit(saved));
  expect(result.current.errors.abn).toEqual(['ABN must be exactly 11 digits']);
  expect(api.patch).not.toHaveBeenCalled();
  await act(() => result.current.setFieldValue('abn', detailB.abn));
  api.patch.mockRejectedValue({ response: { data: { error: 'Current save refused' } } });
  await act(() => result.current.handleSubmit(saved));
  expect(result.current.generalError).toBe('Current save refused');
  expect(result.current.form.abn).toBe(detailB.abn);
  expect(saved).not.toHaveBeenCalled();
});

it('uses the real registration retry screen and preserves visible edits on a failed refresh', async () => {
  companyA = () => Promise.reject(new Error('Detail unavailable'));
  const view = render(
    <QueryClientProvider client={client}>
      <SignupCompanyRegistration />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(view.getByText('Detail unavailable')).toBeTruthy());
  expect(api.post).not.toHaveBeenCalled();
  expect(api.patch).not.toHaveBeenCalled();
  companyA = () => Promise.resolve({ data: detailA });
  fireEvent.click(view.getByRole('button', { name: 'Retry' }));
  await waitFor(() => expect(view.getByDisplayValue(detailA.abn)).toBeTruthy());
  fireEvent.change(view.getByDisplayValue(detailA.abn), { target: { value: detailB.abn } });
  companyA = () => Promise.reject(new Error('Refresh unavailable'));
  await act(() => client.refetchQueries({ queryKey: detailKey('company-a') }));
  await waitFor(() => expect(view.getByText('Refresh unavailable')).toBeTruthy());
  expect(view.getByDisplayValue(detailB.abn)).toBeTruthy();
  companyA = () => Promise.resolve({ data: detailA });
  fireEvent.click(view.getByRole('button', { name: 'Try Again' }));
  await waitFor(() => expect(view.queryByText('Refresh unavailable')).toBeNull());
  expect(view.getByDisplayValue(detailB.abn)).toBeTruthy();
});

it('does not hydrate the next mounted form from an unmounted detail response', async () => {
  const pending = deferred<{ data: typeof detailA }>();
  companyA = () => pending.promise;
  const first = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/companies/company-a/'));
  first.unmount();
  companyList = () => Promise.resolve(list([summaryB]));
  client.setQueryData(listKey, list([summaryB]));
  const next = renderHook(() => useSignupCompanyRegistration(), { wrapper });
  await waitFor(() => expect(next.result.current.form.abn).toBe(detailB.abn));
  await act(() => pending.resolve({ data: detailA }));
  expect(next.result.current.form.abn).toBe(detailB.abn);
});

it('rejects a captured submit callback after its form owner changes', async () => {
  const { result } = await loaded();
  const submitA = result.current.handleSubmit;
  companyList = () => Promise.resolve(list([summaryB]));
  await act(() => {
    client.setQueryData(listKey, list([summaryB]));
  });
  await waitFor(() => expect(result.current.form.abn).toBe(detailB.abn));
  await act(() => submitA(vi.fn()));
  expect(api.patch).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.form.abn).toBe(detailB.abn);
});
