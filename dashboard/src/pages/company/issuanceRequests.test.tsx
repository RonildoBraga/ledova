// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const useTokenDetail = vi.fn();

vi.mock('./hooks/useTokens', () => ({
  useTokensList: vi.fn(),
  useTokenDetail: (uuid: string) => useTokenDetail(uuid),
}));
vi.mock('@tanstack/react-query', () => ({
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

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

function aTokenWhose(issuanceRequests: unknown[]) {
  useTokenDetail.mockReturnValue({
    token: TOKEN,
    isLoading: false,
    holders: [],
    totalHolders: 0,
    isLoadingHolders: false,
    issuances: [],
    issuanceCount: 0,
    isLoadingIssuances: false,
    capitalIncreases: [],
    capitalIncreaseCount: 0,
    issuanceRequests,
    issuanceRequestCount: issuanceRequests.length,
    isLoadingIssuanceRequests: false,
    isLoadingCapitalIncreases: false,
    showCapitalIncreaseForm: false,
    setShowCapitalIncreaseForm: vi.fn(),
    deploy: vi.fn(),
    isDeploying: false,
    pause: vi.fn(),
    isPausing: false,
    unpause: vi.fn(),
    isUnpausing: false,
    downloadRegister: vi.fn(),
    isDownloadingRegister: false,
    registerError: null,
    createCapitalIncrease: vi.fn(),
    isCreatingCapitalIncrease: false,
    submitCapitalIncrease: vi.fn(),
    isSubmittingCapitalIncrease: false,
  });
}

describe('the token modal Issuance Requests section', () => {
  afterEach(cleanup);

  it('shows the issuer the request it made and the status it is waiting on', () => {
    aTokenWhose([REQUEST]);

    render(<TokenDetailModal uuid="token-1" companyStatus="active" onClose={vi.fn()} />);

    expect(screen.getByText('Issuance Requests')).toBeDefined();
    expect(screen.getByText('(1)')).toBeDefined();
    expect(screen.getByText(/10,000 QAT to/)).toBeDefined();
    expect(screen.getByText('Submitted')).toBeDefined();
  });

  it('says none when the issuer has made none', () => {
    aTokenWhose([]);

    render(<TokenDetailModal uuid="token-1" companyStatus="active" onClose={vi.fn()} />);

    expect(screen.getByText('No issuance requests yet.')).toBeDefined();
  });
});
