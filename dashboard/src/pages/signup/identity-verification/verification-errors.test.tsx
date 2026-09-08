// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IDENTITY_VERIFICATION_ENDPOINTS } from '@ledova/shared';
import apiClient from '@services/apiClient';
import snsWebSdk from '@sumsub/websdk';
import { IdentityVerificationModal } from '@pages/user-profile/components/IdentityVerificationModal';
import { SignupIdentityVerification } from './SignupIdentityVerification';

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@sumsub/websdk', () => ({ default: { init: vi.fn() } }));
vi.mock('@components/AuthLayout', () => ({ AuthLayout: ({ children }: PropsWithChildren) => <>{children}</> }));

const clients: QueryClient[] = [];
const NOT_CONFIGURED = 'This feature is not configured on this server.';
const FALLBACK = 'Failed to start verification. Please try again.';

function showVerification(location: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        {location === 'signup' ? (
          <SignupIdentityVerification />
        ) : (
          <IdentityVerificationModal isOpen onClose={vi.fn()} />
        )}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function refusal(data?: unknown) {
  return Object.assign(new Error('Request failed with status code 503'), { response: { status: 503, data } });
}

beforeEach(() => {
  vi.mocked(apiClient.get).mockResolvedValue({ data: { isVerified: false, status: 'not_started' } });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  for (const client of clients.splice(0)) client.clear();
  vi.restoreAllMocks();
  vi.resetAllMocks();
});

describe.each(['signup', 'profile'])('verification errors in %s', (location) => {
  it('shows the backend explanation after the real token mutation fails', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(refusal({ error: 'Service not configured', detail: NOT_CONFIGURED }));
    showVerification(location);

    fireEvent.click(await screen.findByRole('button', { name: 'Start Verification' }));

    expect((await screen.findByRole('alert')).textContent).toBe(NOT_CONFIGURED);
    expect(apiClient.post).toHaveBeenCalledWith(IDENTITY_VERIFICATION_ENDPOINTS.TOKEN);
    expect(snsWebSdk.init).not.toHaveBeenCalled();
  });

  it('uses useful fallback text when the server supplies no explanation', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(refusal());
    showVerification(location);

    fireEvent.click(await screen.findByRole('button', { name: 'Start Verification' }));

    expect((await screen.findByRole('alert')).textContent).toBe(FALLBACK);
  });

  it('clears the previous refusal when a later attempt opens verification', async () => {
    vi.mocked(apiClient.post)
      .mockRejectedValueOnce(refusal({ detail: NOT_CONFIGURED }))
      .mockResolvedValueOnce({ data: { formUrl: 'https://example.test/verification' } });
    showVerification(location);
    fireEvent.click(await screen.findByRole('button', { name: 'Start Verification' }));
    await screen.findByRole('alert');

    fireEvent.click(screen.getByRole('button', { name: 'Start Verification' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByTitle('Identity Verification')).toBeDefined();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
  });
});
