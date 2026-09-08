// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { updateUserProfileCompletion } from '@ledova/shared';
import { AUTH_QUERY_KEY } from '@hooks/useAuth';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

vi.mock('@ledova/shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ledova/shared')>()),
  getUserProfiles: vi.fn(async () => ({ data: { results: [{ uuid: 'profile-1' }] } })),
  getCompanies: vi.fn(async () => ({ data: { results: [] } })),
  updateUserProfileCompletion: vi.fn(async () => ({ data: {} })),
  useFinancialProfile: () => ({ financialProfile: { uuid: 'financial-1' }, isLoading: false }),
}));

vi.mock('@hooks/useAccountRole', () => ({ useAccountRole: () => ({ role: 'investor' }) }));

import { useReview } from './useReview';

let queryClient: QueryClient | undefined;

const harness = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  queryClient = client;
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
};

describe('the last click of signup', () => {
  beforeEach(() => {
    navigate.mockClear();
    vi.mocked(updateUserProfileCompletion).mockClear();
  });

  afterEach(() => {
    queryClient?.clear();
    queryClient = undefined;
  });

  it('refreshes the answer the route guard reads before it navigates', async () => {
    const { client, wrapper } = harness();
    const refetch = vi.spyOn(client, 'refetchQueries').mockResolvedValue(undefined);
    const { result } = renderHook(() => useReview(), { wrapper });
    await waitFor(() => expect(result.current.canCompleteSignup).toBe(true));

    act(() => result.current.completeSignup());

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(refetch).toHaveBeenCalledWith({ queryKey: AUTH_QUERY_KEY, exact: true });
  });

  it('does not navigate until that answer is back, so the guard cannot read a stale one', async () => {
    const { client, wrapper } = harness();
    let release: () => void = () => {};
    vi.spyOn(client, 'refetchQueries').mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    const { result } = renderHook(() => useReview(), { wrapper });
    await waitFor(() => expect(result.current.canCompleteSignup).toBe(true));

    act(() => result.current.completeSignup());
    await waitFor(() => expect(vi.mocked(updateUserProfileCompletion)).toHaveBeenCalled());

    expect(navigate).not.toHaveBeenCalled();

    await act(async () => {
      release();
    });

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/home'));
  });

  it('sends an investor to home', async () => {
    const { client, wrapper } = harness();
    vi.spyOn(client, 'refetchQueries').mockResolvedValue(undefined);
    const { result } = renderHook(() => useReview(), { wrapper });
    await waitFor(() => expect(result.current.canCompleteSignup).toBe(true));

    act(() => result.current.completeSignup());

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/home'));
  });
});
