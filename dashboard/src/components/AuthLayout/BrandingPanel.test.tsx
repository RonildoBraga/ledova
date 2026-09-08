// @vitest-environment jsdom

import { cleanup, render as renderComponent, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import apiClient from '@services/apiClient';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClientProvider } from '@ledova/shared';

import { BrandingPanel } from './BrandingPanel';

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn(async () => ({ data: { valid: false } })) } }));

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

afterEach(() => {
  cleanup();
  client.clear();
});

function render() {
  return renderComponent(
    <QueryClientProvider client={client}>
      <ApiClientProvider client={apiClient}>
        <BrandingPanel />
      </ApiClientProvider>
    </QueryClientProvider>,
  );
}

describe('what the panel beside every sign-in and sign-up screen says the product is', () => {
  it('names the thing a visitor is signing up to hold', () => {
    render();

    expect(screen.queryAllByText(/shares/i).length).toBeGreaterThan(0);
  });

  it('does not offer itself as a wallet for digital assets, which is what it is used to hold them', () => {
    render();

    expect(screen.queryAllByText(/smart wallet/i)).toEqual([]);
    expect(screen.queryAllByText(/your digital assets/i)).toEqual([]);
  });

  it('leads on signing rather than on the hardware that is one way to do it', () => {
    render();

    expect(screen.queryAllByText(/air-gapped/i)).toEqual([]);
    expect(screen.queryAllByText(/hardware wallet/i).length).toBeGreaterThan(0);
  });

  it('keeps the custody claim, which is the owner decision it is not this change to make', () => {
    render();

    expect(screen.queryAllByText(/non-custodial/i).length).toBeGreaterThan(0);
  });
});
