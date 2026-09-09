// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { COMPANY_TOKEN_ENDPOINTS } from '@ledova/shared';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));

import { TokenDetailModal } from './index';

const TOKEN = {
  uuid: 'token-1',
  name: 'Ordinary Shares',
  symbol: 'QAT',
  status: 'deployed',
  tokenType: 'ordinary',
  totalSupply: '1000000',
  contractAddress: `0x${'c'.repeat(40)}`,
  chain: 'base',
};

const REQUEST = {
  uuid: 'request-1',
  token: 'token-1',
  tokenSymbol: 'QAT',
  tokenName: 'Ordinary Shares',
  recipientAddress: `0x${'b'.repeat(40)}`,
  amount: 10000,
  issuanceType: 'additional',
  issuanceTypeDisplay: 'Additional',
  reason: 'Founder allocation',
  status: 'submitted',
  statusDisplay: 'Submitted',
  dilutionPercentage: null,
  submittedBy: 'user-1',
  submittedByEmail: 'issuer@example.test',
  submittedAt: '2026-09-07T00:00:00Z',
  createdAt: '2026-09-07T00:00:00Z',
};

let requests: Array<typeof REQUEST & { executionNotes?: string }>;
let tokenStatus: string;
let refuseRequests: boolean;
let queryClient: QueryClient;

function showHistory() {
  render(
    <QueryClientProvider client={queryClient}>
      <TokenDetailModal uuid="token-1" companyStatus="active" onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  requests = [];
  tokenStatus = 'deployed';
  refuseRequests = false;
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  api.get.mockReset();
  api.post.mockReset();
  api.get.mockImplementation(async (url: string, config?: { params?: { page?: number } }) => {
    if (url === COMPANY_TOKEN_ENDPOINTS.DETAIL('token-1')) return { data: { ...TOKEN, status: tokenStatus } };
    if (url === COMPANY_TOKEN_ENDPOINTS.HOLDERS('token-1')) return { data: { holders: [], totalHolders: 0 } };
    if (url === COMPANY_TOKEN_ENDPOINTS.ISSUANCES('token-1') || url === COMPANY_TOKEN_ENDPOINTS.CAPITAL_INCREASES) {
      return { data: { results: [], count: 0, next: null, previous: null } };
    }
    if (url === COMPANY_TOKEN_ENDPOINTS.ISSUANCE_REQUESTS) {
      if (refuseRequests) throw new Error('Network unavailable');
      const page = config?.params?.page ?? 1;
      return {
        data: {
          results: requests.slice((page - 1) * 25, page * 25),
          count: requests.length,
          previous: null,
          next:
            requests.length > page * 25
              ? `https://example.test/api/v1/tokens/issuance-requests/?page=${page + 1}`
              : null,
        },
      };
    }
    throw new Error(`Unexpected GET ${url}`);
  });
});

afterEach(() => {
  cleanup();
  queryClient.clear();
});

describe('the issuer request history through real query and service hooks', () => {
  it('refreshes the history after a submitted request receives 201', async () => {
    api.post.mockImplementation(async (url: string, data: { recipient: string; amount: number; reason: string }) => {
      expect(url).toBe(COMPANY_TOKEN_ENDPOINTS.ISSUE('token-1'));
      requests = [{ ...REQUEST, recipientAddress: data.recipient, amount: data.amount, reason: data.reason }];
      return { status: 201, data: { message: 'Submitted', token: TOKEN, issuanceRequest: requests[0] } };
    });
    showHistory();
    await screen.findByText('No issuance requests yet.');
    fireEvent.click(screen.getByRole('button', { name: 'Request Issuance' }));
    fireEvent.change(screen.getByLabelText('Recipient Address'), { target: { value: REQUEST.recipientAddress } });
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '10000' } });
    fireEvent.change(screen.getByLabelText('Reason (optional)'), { target: { value: 'Founder allocation' } });
    fireEvent.click(screen.getByRole('button', { name: 'Request Issuance' }));

    await screen.findByText('Submitted');
    expect(screen.getByText(/10,000 QAT to/)).toBeDefined();
    expect(screen.getByText('(1)')).toBeDefined();
    expect(api.post).toHaveBeenCalledExactlyOnceWith(COMPANY_TOKEN_ENDPOINTS.ISSUE('token-1'), {
      recipient: REQUEST.recipientAddress,
      amount: 10000,
      reason: 'Founder allocation',
    });
  });

  it('keeps the whole page visible and can load older requests', async () => {
    requests = Array.from({ length: 26 }, (_, index) => ({
      ...REQUEST,
      uuid: `request-${index}`,
      reason: `Allocation ${index}`,
    }));
    showHistory();
    await screen.findByText('Allocation 24');
    expect(screen.queryByText('Allocation 25')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Load more issuance requests' }));
    await screen.findByText('Allocation 25');
    expect(screen.getByText('Allocation 0')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Load more issuance requests' })).toBeNull();
    expect(api.get).toHaveBeenCalledWith(COMPANY_TOKEN_ENDPOINTS.ISSUANCE_REQUESTS, {
      params: { token: 'token-1', page: 2 },
    });
  });

  it('reports a failed history load and retries without claiming it is empty', async () => {
    refuseRequests = true;
    showHistory();
    await screen.findByRole('alert');
    expect(screen.queryByText('No issuance requests yet.')).toBeNull();
    refuseRequests = false;
    requests = [REQUEST];
    fireEvent.click(screen.getByRole('button', { name: 'Retry issuance requests' }));
    await screen.findByText('Submitted');
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('shows safe execution history and distinguishes approved and rejected requests', async () => {
    requests = [
      {
        ...REQUEST,
        status: 'approved',
        statusDisplay: 'Approved',
        executionNotes: 'Execution failed. Operations review is required.',
      },
      { ...REQUEST, uuid: 'request-2', status: 'rejected', statusDisplay: 'Rejected' },
    ];
    showHistory();
    await screen.findByText('Approved');
    expect(screen.getByText('Approved').className).not.toEqual(screen.getByText('Rejected').className);
    expect(screen.getByText('Execution history')).toBeDefined();
    expect(screen.getByText('Execution failed. Operations review is required.')).toBeDefined();
  });

  it('hides empty history on a draft token but preserves any existing requests', async () => {
    tokenStatus = 'draft';
    showHistory();
    await screen.findByText('Deploy Token');
    expect(screen.queryByText('Issuance Requests')).toBeNull();
    requests = [REQUEST];
    await queryClient.invalidateQueries({ queryKey: ['token', 'token-1', 'issuance-requests'] });
    await screen.findByText('Submitted');
    expect(screen.getByText('Issuance Requests')).toBeDefined();
  });
});
