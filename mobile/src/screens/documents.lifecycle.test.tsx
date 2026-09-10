import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as DocumentPicker from 'expo-document-picker';
import { InvestorEligibilityScreen } from './investor-eligibility';
import { ListingScreen } from './listing';
import { useInvestorEligibility } from './investor-eligibility/useInvestorEligibility';
import { useCompanyDocuments } from './listing/useCompanyDocuments';
import { files, pickedFile, resetFiles } from '../testSupport/documentFiles';

jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-file-system', () => jest.requireActual('../testSupport/documentFiles').nativeFileSystem);
jest.mock('../services/tokenStorage', () => ({ getAccessToken: jest.fn(async () => 'synthetic-access') }));
jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn(async () => ({ data: {} })) } }));
jest.mock('./investor-eligibility/useInvestorEligibility', () => ({ useInvestorEligibility: jest.fn() }));
jest.mock('./listing/useCompanyDocuments', () => ({ useCompanyDocuments: jest.fn() }));

const pick = jest.mocked(DocumentPicker.getDocumentAsync);
const submitClaim = jest.fn();
const upload = jest.fn();
let client: QueryClient;

beforeEach(() => {
  resetFiles();
  pick.mockReset();
  submitClaim.mockReset();
  upload.mockReset();
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  jest.mocked(useInvestorEligibility).mockReturnValue({
    eligibility: { account: 'account-a', isEligible: false, reasons: [] },
    classifications: [],
    isLoading: false,
    submitClaim,
    isSubmitting: false,
    deleteClaim: jest.fn(),
    isDeleting: false,
  } as unknown as ReturnType<typeof useInvestorEligibility>);
  jest.mocked(useCompanyDocuments).mockReturnValue({
    company: { uuid: 'company-a', status: 'draft', name: 'Synthetic company' },
    companyUuid: 'company-a',
    documents: [],
    uploadedTypes: new Set(),
    canEdit: true,
    isLoading: false,
    upload,
    isUploading: false,
    deleteDocument: jest.fn(),
    isDeleting: false,
    submitApplication: jest.fn(),
    isSubmitting: false,
    resubmitApplication: jest.fn(),
    isResubmitting: false,
    withdrawApplication: jest.fn(),
    isWithdrawing: false,
  } as unknown as ReturnType<typeof useCompanyDocuments>);
});

afterEach(() => {
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function claimForm() {
  const view = await render(<InvestorEligibilityScreen />, { wrapper });
  await fireEvent.press(view.getByLabelText('Attach evidence for Large investment'));
  await fireEvent.changeText(
    view.getByPlaceholderText('Describe why this category applies to you'),
    'Synthetic evidence',
  );
  await fireEvent.press(view.getByText('Attach evidence (PDF or image, max 10 MB)'));
  return view;
}

it('retains evidence after refusal and cleans it after the eligibility retry succeeds', async () => {
  const returned = pickedFile();
  pick.mockResolvedValue(returned);
  const view = await claimForm();
  expect(view.getByText('1.pdf')).toBeTruthy();
  submitClaim.mockRejectedValueOnce(new Error('Claim refused')).mockResolvedValueOnce({});
  await fireEvent.press(view.getByText('Submit for review'));
  const first = submitClaim.mock.calls[0][0];
  expect(files.has(first.file.uri)).toBe(true);
  expect(view.getByText('1.pdf')).toBeTruthy();
  await fireEvent.press(view.getByText('Submit for review'));
  expect(submitClaim.mock.calls[1][0].file).toEqual(first.file);
  expect(first.userAccount).toBe('account-a');
  expect(files.has(first.file.uri)).toBe(false);
  expect(files.has(returned.assets[0].uri)).toBe(false);
  expect(view.queryByText('1.pdf')).toBeNull();
});

it('keeps an edited eligibility draft when its earlier submission succeeds', async () => {
  pick.mockResolvedValue(pickedFile());
  const view = await claimForm();
  let finish!: () => void;
  submitClaim.mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  let pressed!: Promise<void>;
  await act(async () => {
    pressed = fireEvent.press(view.getByText('Submit for review'));
  });
  const uri = submitClaim.mock.calls[0][0].file.uri;
  await fireEvent.changeText(view.getByPlaceholderText('Describe why this category applies to you'), 'Newer draft');
  await act(async () => {
    finish();
    await pressed;
  });
  expect(view.getByDisplayValue('Newer draft')).toBeTruthy();
  expect(files.has(uri)).toBe(false);
});

it.each(['success', 'refusal'])('retires a listing upload after %s and preserves it while pending', async (outcome) => {
  const returned = pickedFile();
  pick.mockResolvedValue(returned);
  let finish!: () => void;
  let refuse!: (error: Error) => void;
  upload.mockImplementation(
    () =>
      new Promise<void>((resolve, reject) => {
        finish = resolve;
        refuse = reject;
      }),
  );
  const view = await render(<ListingScreen />, { wrapper });
  let pressed!: Promise<void>;
  await act(async () => {
    pressed = fireEvent.press(view.getByLabelText('Upload Certificate of Incorporation'));
  });
  expect(upload).toHaveBeenCalledTimes(1);
  const input = upload.mock.calls[0][0];
  expect(input).toMatchObject({ companyUuid: 'company-a', documentType: 'cert_inc' });
  expect(files.has(input.file.uri)).toBe(true);
  await view.unmount();
  expect(files.has(input.file.uri)).toBe(true);
  await act(async () => {
    if (outcome === 'success') finish();
    else refuse(new Error('Refused'));
    await pressed;
  });
  expect(files.has(input.file.uri)).toBe(false);
  expect(files.has(returned.assets[0].uri)).toBe(false);
  expect(Alert.alert).not.toHaveBeenCalled();
});
