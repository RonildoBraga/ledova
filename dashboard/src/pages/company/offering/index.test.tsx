// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Offering, OfferingInput } from '@ledova/shared';

const useCompany = vi.fn();
const useOfferings = vi.fn();
const useOfferingActions = vi.fn();
const useOfferingSubscriptions = vi.fn();
const useOfferingUnderEdit = vi.fn();
const update = vi.fn((variables: { uuid: string; data: OfferingInput }) => Promise.resolve(variables));

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('@tanstack/react-query', () => ({
  useMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock('../hooks/useCompany', () => ({ useCompany: () => useCompany() }));
vi.mock('./useOffering', () => ({
  useOfferings: () => useOfferings(),
  useOfferingActions: () => useOfferingActions(),
  useOfferingSubscriptions: () => useOfferingSubscriptions(),
  useOfferingUnderEdit: (uuid: string | undefined) => useOfferingUnderEdit(uuid),
}));

import OfferingPage from './index';

const REJECTION = 'The exemption does not apply to this class.';

function anOffering(overrides: Partial<Offering>): Offering {
  return {
    uuid: 'offering-1',
    tokenUuid: 'token-1',
    tokenSymbol: 'QAT',
    tokenName: 'Ordinary Shares',
    status: 'draft',
    statusDisplay: 'Draft',
    exemption: 's708_11_professional',
    exemptionDisplay: 'Professional investor',
    pricePerShare: '2.50',
    priceCurrency: 'AUD',
    minimumShares: 100,
    targetShares: 5000,
    capShares: 10000,
    maximumShares: null,
    opensAt: '2027-03-01T00:00:00.000Z',
    closesAt: null,
    isOpen: false,
    createdAt: '2026-09-01T00:00:00.000Z',
    settlementAssets: [],
    acceptsBankTransfer: true,
    summary: 'A tranche',
    useOfProceeds: 'Plant',
    documents: [],
    submittedByEmail: null,
    submittedAt: null,
    reviewedByEmail: null,
    reviewedAt: null,
    reviewNotes: '',
    rejectionReason: '',
    closedAt: null,
    closeReason: '',
    canBeEdited: true,
    canBeDeleted: true,
    updatedAt: '2026-09-01T00:00:00.000Z',
    ...overrides,
  } as Offering;
}

function aPageShowing(offering: Offering, underEdit?: Offering) {
  useCompany.mockReturnValue({
    company: {
      uuid: 'company-1',
      name: 'QA Co',
      statusDisplay: 'Active',
      canIssueTokens: true,
      isOpenToInvestors: true,
    },
    companyUuid: 'company-1',
    isLoading: false,
  });
  useOfferings.mockReturnValue({
    offerings: [offering],
    tokens: [{ uuid: 'token-1', name: 'Ordinary Shares', symbol: 'QAT', status: 'deployed' }],
    settlementAssets: [],
    isLoading: false,
    refresh: vi.fn(),
  });
  useOfferingActions.mockReturnValue({
    create: { isPending: false, mutateAsync: vi.fn(() => Promise.resolve()) },
    update: { isPending: false, mutateAsync: update },
    submit: { isPending: false, mutateAsync: vi.fn(() => Promise.resolve()) },
    withdraw: { isPending: false, mutateAsync: vi.fn(() => Promise.resolve()) },
    remove: { isPending: false, mutateAsync: vi.fn(() => Promise.resolve()) },
  });
  useOfferingSubscriptions.mockReturnValue({ subscriptions: [], isLoading: false });
  useOfferingUnderEdit.mockImplementation(() => ({ offering: underEdit, isLoading: false }));
}

afterEach(() => {
  cleanup();
  update.mockClear();
  useOfferingUnderEdit.mockReset();
});

describe('which offerings an issuer may edit, and which may be deleted', () => {
  it('offers Edit and Delete on a draft, because a draft is both', () => {
    aPageShowing(anOffering({ status: 'draft', canBeEdited: true, canBeDeleted: true }));

    render(<OfferingPage />);

    expect(screen.getByText('Edit')).toBeTruthy();
    expect(screen.getByText('Delete')).toBeTruthy();
    expect(screen.getByText('Submit for review')).toBeTruthy();
  });

  it('offers Edit but not Delete on a rejected offering, which is the whole of the decision', () => {
    aPageShowing(anOffering({ status: 'rejected', statusDisplay: 'Rejected', canBeEdited: true, canBeDeleted: false }));

    render(<OfferingPage />);

    expect(screen.getByText('Edit')).toBeTruthy();
    expect(screen.queryByText('Delete')).toBeNull();
  });

  it('says Submit again rather than Submit for review, because the operator has seen it once', () => {
    aPageShowing(anOffering({ status: 'rejected', statusDisplay: 'Rejected', canBeEdited: true, canBeDeleted: false }));

    render(<OfferingPage />);

    expect(screen.getByText('Submit again')).toBeTruthy();
    expect(screen.queryByText('Submit for review')).toBeNull();
  });

  it('offers neither on an approved offering', () => {
    aPageShowing(
      anOffering({ status: 'approved', statusDisplay: 'Approved', canBeEdited: false, canBeDeleted: false }),
    );

    render(<OfferingPage />);

    expect(screen.queryByText('Edit')).toBeNull();
    expect(screen.queryByText('Delete')).toBeNull();
  });

  it('shows the rejection reason while it is rejected and not once it has moved on', () => {
    aPageShowing(
      anOffering({ status: 'rejected', statusDisplay: 'Rejected', rejectionReason: REJECTION, canBeDeleted: false }),
    );

    render(<OfferingPage />);

    expect(screen.getByText(`Rejected: ${REJECTION}`)).toBeTruthy();

    cleanup();
    aPageShowing(
      anOffering({ status: 'submitted', statusDisplay: 'Submitted', rejectionReason: REJECTION, canBeEdited: false }),
    );

    render(<OfferingPage />);

    expect(screen.queryByText(`Rejected: ${REJECTION}`)).toBeNull();
  });
});

describe('what the edit form is seeded with, and what Save sends', () => {
  const REJECTED = anOffering({
    status: 'rejected',
    statusDisplay: 'Rejected',
    rejectionReason: REJECTION,
    canBeEdited: true,
    canBeDeleted: false,
    summary: 'The tranche as the operator saw it',
    pricePerShare: '3.25',
    minimumShares: 250,
  });

  it('opens the form on the offering rather than on an empty one', () => {
    aPageShowing(REJECTED, REJECTED);

    render(<OfferingPage />);
    fireEvent.click(screen.getByText('Edit'));

    expect(screen.getByDisplayValue('3.25')).toBeTruthy();
    expect(screen.getByDisplayValue('250')).toBeTruthy();
    expect(screen.getByDisplayValue('The tranche as the operator saw it')).toBeTruthy();
    expect(screen.getByText('Save changes')).toBeTruthy();
  });

  it('sends the edited value to the update mutation under the offering it came from', () => {
    aPageShowing(REJECTED, REJECTED);

    render(<OfferingPage />);
    fireEvent.click(screen.getByText('Edit'));
    fireEvent.change(screen.getByDisplayValue('The tranche as the operator saw it'), {
      target: { value: 'Corrected after the review' },
    });
    fireEvent.click(screen.getByText('Save changes'));

    expect(update).toHaveBeenCalledTimes(1);
    const sent = update.mock.calls[0][0];
    expect(sent.uuid).toBe('offering-1');
    expect(sent.data.summary).toBe('Corrected after the review');
    expect(sent.data.pricePerShare).toBe('3.25');
  });

  it('says what submitting it again will do, so Save is not mistaken for resubmission', () => {
    aPageShowing(REJECTED, REJECTED);

    render(<OfferingPage />);
    fireEvent.click(screen.getByText('Edit'));

    expect(screen.getByText(/Submitting it again sends it back for review/)).toBeTruthy();
  });
});
