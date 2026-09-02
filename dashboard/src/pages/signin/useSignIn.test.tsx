// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { signin } from '@ledova/shared-services';
import apiClient from '@services/apiClient';
import { AUTH_QUERY_KEY } from '@hooks/useAuth';
import { useSignIn } from './useSignIn';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ledova/shared-services', () => ({
  signin: vi.fn(),
  verifyAuth: vi.fn(),
}));

const signinMock = vi.mocked(signin);

const createHarness = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { queryClient, wrapper };
};

const fillForm = (result: ReturnType<typeof renderHook<ReturnType<typeof useSignIn>, unknown>>['result']) => {
  act(() => result.current.setFieldValue('email', 'founder@example.test'));
  act(() => result.current.setFieldValue('password', 'correct horse battery staple'));
};

describe('useSignIn', () => {
  beforeEach(() => {
    signinMock.mockReset();
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('validates a blank form without making a request', async () => {
    const { queryClient, wrapper } = createHarness();
    const { result, unmount } = renderHook(() => useSignIn(), { wrapper });

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(signinMock).not.toHaveBeenCalled();
    expect(result.current.errors).toEqual({
      email: ['Email is required'],
      password: ['Password is required'],
    });

    unmount();
    queryClient.clear();
  });

  it('signs in, refreshes authentication state, then reports success', async () => {
    const { queryClient, wrapper } = createHarness();
    const callOrder: string[] = [];
    signinMock.mockImplementation(async () => {
      callOrder.push('signin');
      return { data: {} } as never;
    });
    vi.spyOn(queryClient, 'refetchQueries').mockImplementation(async (filters) => {
      expect(filters).toEqual({ queryKey: AUTH_QUERY_KEY, exact: true });
      callOrder.push('refetch');
    });
    const onSuccess = vi.fn(() => callOrder.push('success'));
    const { result, unmount } = renderHook(() => useSignIn(), { wrapper });
    fillForm(result);

    await act(async () => {
      await result.current.handleSubmit(onSuccess);
    });

    expect(signinMock).toHaveBeenCalledWith(apiClient, {
      email: 'founder@example.test',
      password: 'correct horse battery staple',
    });
    expect(callOrder).toEqual(['signin', 'refetch', 'success']);
    expect(onSuccess).toHaveBeenCalledOnce();

    unmount();
    queryClient.clear();
  });

  it('does not persist token-looking response fields', async () => {
    const { queryClient, wrapper } = createHarness();
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem');
    signinMock.mockResolvedValue({
      data: {
        access: 'legacy-access-token',
        refresh: 'legacy-refresh-token',
        token: 'legacy-token',
      },
    } as never);
    const { result, unmount } = renderHook(() => useSignIn(), { wrapper });
    fillForm(result);

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(storageWrite).not.toHaveBeenCalled();
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);

    storageWrite.mockRestore();
    unmount();
    queryClient.clear();
  });
});
