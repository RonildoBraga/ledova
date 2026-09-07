// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const useCompany = vi.fn();
const useTokensList = vi.fn();

vi.mock('./hooks/useCompany', () => ({ useCompany: () => useCompany() }));
vi.mock('./hooks/useTokens', () => ({ useTokensList: () => useTokensList() }));
vi.mock('@tanstack/react-query', () => ({
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

import CompanyPage from './index';

const DRAFT_TOKEN = {
  uuid: 'token-1',
  name: 'Ordinary Shares',
  symbol: 'QAT',
  tokenType: 'ordinary',
  status: 'draft',
  totalSupply: '1000000',
};

function aCompanyWith(tokens: unknown[], deployedCount: number) {
  useCompany.mockReturnValue({
    company: { uuid: 'company-1', name: 'QA Co', status: 'active' },
    companyUuid: 'company-1',
    stats: { totalTokens: deployedCount, totalShareholders: 0, pendingRequests: 0 },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  useTokensList.mockReturnValue({
    tokens,
    totalCount: tokens.length,
    page: 1,
    totalPages: 1,
    search: '',
    setSearch: vi.fn(),
    isLoading: false,
    error: null,
    isCreateModalOpen: false,
    setIsCreateModalOpen: vi.fn(),
    setPage: vi.fn(),
    createToken: vi.fn(),
    resetCreateError: vi.fn(),
    createError: null,
    isCreating: false,
    statusFilter: '',
    setStatusFilter: vi.fn(),
  });
}

describe('the Share Tokens panel', () => {
  afterEach(cleanup);

  it('counts the tokens it is listing, not only the deployed ones', () => {
    aCompanyWith([DRAFT_TOKEN], 0);

    render(<CompanyPage />);

    expect(screen.getByText('Share Tokens (1)')).toBeDefined();
    expect(screen.getByText('Ordinary Shares')).toBeDefined();
  });

  it('says none when it is listing none', () => {
    aCompanyWith([], 0);

    render(<CompanyPage />);

    expect(screen.getByText('Share Tokens (0)')).toBeDefined();
  });
});
