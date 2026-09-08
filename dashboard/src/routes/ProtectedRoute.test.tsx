// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CACHE_TIMING } from '@ledova/shared';

import { AUTH_QUERY_KEY } from '@hooks/useAuth';
import apiClient from '@services/apiClient';
import { ProtectedRoute } from './ProtectedRoute';

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn() } }));

let client: QueryClient;

function renderGuard(valid: boolean, stale = true) {
  client.setQueryData(
    AUTH_QUERY_KEY,
    { data: { valid } },
    {
      updatedAt: Date.now() - (stale ? CACHE_TIMING.DEFAULT_STALE_TIME + 1000 : 0),
    },
  );
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <p>Protected content</p>
              </ProtectedRoute>
            }
          />
          <Route path="/signin" element={<p>Sign in</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function holdVerification() {
  let resolve!: (valid: boolean) => void;
  let reject!: (reason: Error) => void;
  vi.mocked(apiClient.get).mockReturnValue(
    new Promise((succeed, fail) => {
      resolve = (valid) => succeed({ data: { valid } });
      reject = fail;
    }),
  );
  return { resolve, reject };
}

describe('a protected route checks an auth correction before redirecting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  });

  afterEach(() => {
    cleanup();
    client.clear();
  });

  it('keeps protected content hidden until a stale negative has been corrected', async () => {
    const verification = holdVerification();
    renderGuard(false);

    expect(screen.getByRole('status', { name: 'Checking your session' })).toBeTruthy();
    expect(screen.queryByText('Sign in')).toBeNull();
    expect(screen.queryByText('Protected content')).toBeNull();
    await act(async () => verification.resolve(true));

    await waitFor(() => expect(screen.getByText('Protected content')).toBeTruthy());
    expect(screen.queryByText('Sign in')).toBeNull();
  });

  it('redirects after a fresh answer confirms the visitor is signed out', async () => {
    const verification = holdVerification();
    renderGuard(false);

    expect(screen.queryByText('Sign in')).toBeNull();
    await act(async () => verification.resolve(false));

    await waitFor(() => expect(screen.getByText('Sign in')).toBeTruthy());
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByText('Protected content')).toBeNull();
  });

  it('leaves the loading state when verification fails and grants no access', async () => {
    const verification = holdVerification();
    renderGuard(false);

    expect(screen.queryByText('Sign in')).toBeNull();
    await act(async () => verification.reject(new Error('Network unavailable')));

    await waitFor(() => expect(screen.getByText('Sign in')).toBeTruthy());
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByText('Protected content')).toBeNull();
  });

  it('redirects immediately on a current negative with no request in flight', () => {
    renderGuard(false, false);

    expect(screen.getByText('Sign in')).toBeTruthy();
    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it('keeps an authenticated page mounted while its cached positive is rechecked', async () => {
    const verification = holdVerification();
    renderGuard(true);

    expect(screen.getByText('Protected content')).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
    await act(async () => verification.resolve(true));
    expect(screen.getByText('Protected content')).toBeTruthy();
  });
});
