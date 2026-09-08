// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function axiosRefusal(data: unknown) {
  return Object.assign(new Error('Request failed with status code 400'), {
    response: { status: 400, data },
  });
}

interface DialogState {
  createError?: unknown;
  createToken?: (...args: unknown[]) => unknown;
}

function theCreateDialog({ createError = null, createToken = vi.fn() }: DialogState = {}) {
  useCompany.mockReturnValue({
    company: { uuid: 'company-1', name: 'QA Co', status: 'active' },
    companyUuid: 'company-1',
    stats: { totalTokens: 0, totalShareholders: 0, pendingRequests: 0 },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  useTokensList.mockReturnValue({
    tokens: [],
    totalCount: 0,
    page: 1,
    totalPages: 1,
    search: '',
    setSearch: vi.fn(),
    isLoading: false,
    error: null,
    isCreateModalOpen: true,
    setIsCreateModalOpen: vi.fn(),
    setPage: vi.fn(),
    createToken,
    resetCreateError: vi.fn(),
    createError,
    isCreating: false,
    statusFilter: '',
    setStatusFilter: vi.fn(),
  });
}

describe('a create that the backend refused', () => {
  afterEach(cleanup);

  it('shows the reason the backend gave, and not the HTTP status', () => {
    theCreateDialog({ createError: axiosRefusal({ symbol: ['Symbol must contain only letters.'] }) });

    render(<CompanyPage />);

    expect(screen.getByText('Symbol must contain only letters.')).toBeDefined();
    expect(screen.queryByText(/status code 400/)).toBeNull();
  });

  it('says which of two fields is wrong when the backend named both', () => {
    theCreateDialog({
      createError: axiosRefusal({
        symbol: ['Symbol must contain only letters.'],
        totalSupply: ['Ensure this value is greater than 0.'],
      }),
    });

    render(<CompanyPage />);

    expect(screen.getByText(/Symbol must contain only letters\./)).toBeDefined();
    expect(screen.getByText(/Ensure this value is greater than 0\./)).toBeDefined();
  });

  it('still says something when the refusal carries no body', () => {
    theCreateDialog({ createError: axiosRefusal(undefined) });

    render(<CompanyPage />);

    expect(screen.getByText('Failed to create token. Please try again.')).toBeDefined();
    expect(screen.queryByText(/status code 400/)).toBeNull();
  });
});

describe('what a failed submit leaves on screen', () => {
  afterEach(cleanup);

  it('keeps what the director typed, so they are not asked to type it again', async () => {
    const createToken = vi.fn().mockRejectedValue(axiosRefusal({ symbol: ['Symbol must contain only letters.'] }));
    theCreateDialog({ createToken });

    render(<CompanyPage />);
    fireEvent.change(screen.getByLabelText('Token Name'), { target: { value: 'Ordinary Shares' } });
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'QA1ORD' } });
    fireEvent.change(screen.getByLabelText('Total Supply (Authorized Shares)'), { target: { value: '1000000' } });

    fireEvent.click(screen.getByText('Create Token'));

    await waitFor(() => expect(createToken).toHaveBeenCalled());
    expect((screen.getByLabelText('Token Name') as HTMLInputElement).value).toBe('Ordinary Shares');
    expect((screen.getByLabelText('Symbol') as HTMLInputElement).value).toBe('QA1ORD');
    expect((screen.getByLabelText('Total Supply (Authorized Shares)') as HTMLInputElement).value).toBe('1000000');
  });
});
