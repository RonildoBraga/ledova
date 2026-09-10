import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import type { JsonValue } from '@ledova/shared';
import { apiClient } from '../../../services/apiClient';
import { useFinancialProfile } from './useFinancialProfile';

jest.mock('../../../services/apiClient', () => ({ apiClient: { get: jest.fn(), patch: jest.fn() } }));

const get = jest.mocked(apiClient.get);
const patch = jest.mocked(apiClient.patch);

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
  patch.mockResolvedValue({ data: {} });
});

afterEach(async () => {
  await cleanup();
});

it.each<{ funds: JsonValue; choices: string[] }>([
  { funds: ['savings', 'historical choice'], choices: ['savings', 'historical choice'] },
  { funds: null, choices: [] },
  { funds: { source: 'legacy value' }, choices: [] },
  { funds: 'savings', choices: [] },
  { funds: 9, choices: [] },
  { funds: false, choices: [] },
  { funds: ['savings', null, 8, { other: true }], choices: ['savings'] },
])('loads editable choices from $funds and submits the selected strings', async ({ funds, choices }) => {
  get.mockResolvedValueOnce({ data: { count: 1, results: [{ uuid: 'profile-1' }] } });
  get.mockResolvedValueOnce({
    data: {
      count: 1,
      results: [{ uuid: 'financial-1', occupation: 'Engineer', sourceOfFunds: funds, intendedUse: 'savings' }],
    },
  });
  const saved = jest.fn();
  const { result } = await renderHook(() => useFinancialProfile());
  await waitFor(() => expect(result.current.isLoading).toBe(false));

  expect(result.current.form.sourceOfFunds).toEqual(choices);
  expect(patch).not.toHaveBeenCalled();
  await act(() => result.current.toggleSourceOfFunds('gift'));
  await act(() => result.current.handleSubmit(saved));

  expect(patch).toHaveBeenCalledWith('/api/financial-profiles/financial-1/', {
    occupation: 'Engineer',
    sourceOfFunds: [...choices, 'gift'],
    sourceOfFundsOtherText: null,
    intendedUse: 'savings',
    intendedUseOtherText: null,
  });
  expect(saved).toHaveBeenCalledTimes(1);
});
