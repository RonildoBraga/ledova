// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { verifyAuth } from '@ledova/shared-services';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from './useAuth';

vi.mock('@ledova/shared-services', () => ({
  verifyAuth: vi.fn(),
}));

const verifyAuthMock = vi.mocked(verifyAuth);
let queryClient: QueryClient | undefined;

const createWrapper = () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  queryClient = client;

  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  return Wrapper;
};

describe('useAuth', () => {
  afterEach(() => {
    queryClient?.clear();
    queryClient = undefined;
    verifyAuthMock.mockReset();
  });

  it('reports an authenticated user when verification is valid', async () => {
    verifyAuthMock.mockResolvedValue({ data: { valid: true } } as never);
    const { result, unmount } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isAuthenticated).toBe(true);
    expect(verifyAuthMock).toHaveBeenCalledOnce();
    unmount();
  });

  it('reports an unauthenticated user when verification is invalid', async () => {
    verifyAuthMock.mockResolvedValue({ data: { valid: false } } as never);
    const { result, unmount } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isAuthenticated).toBe(false);
    expect(verifyAuthMock).toHaveBeenCalledOnce();
    unmount();
  });
});
