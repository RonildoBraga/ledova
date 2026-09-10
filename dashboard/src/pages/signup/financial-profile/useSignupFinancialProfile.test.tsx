// @vitest-environment jsdom

import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { JsonValue } from '@ledova/shared';
import { useSignupFinancialProfile } from './useSignupFinancialProfile';

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));

beforeEach(() => {
  vi.clearAllMocks();
  api.patch.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

it.each<{ funds: JsonValue; choices: string[] }>([
  { funds: ['savings', 'historical choice'], choices: ['savings', 'historical choice'] },
  { funds: null, choices: [] },
  { funds: { source: 'legacy value' }, choices: [] },
  { funds: 'savings', choices: [] },
  { funds: 9, choices: [] },
  { funds: false, choices: [] },
  { funds: ['savings', null, 8, { other: true }], choices: ['savings'] },
])('loads editable choices from $funds and submits the selected strings', async ({ funds, choices }) => {
  api.get.mockResolvedValueOnce({ data: { count: 1, results: [{ uuid: 'profile-1' }] } });
  api.get.mockResolvedValueOnce({
    data: {
      count: 1,
      results: [{ uuid: 'financial-1', occupation: 'Engineer', sourceOfFunds: funds, intendedUse: 'savings' }],
    },
  });
  const saved = vi.fn();
  const { result } = renderHook(() => useSignupFinancialProfile());
  await waitFor(() => expect(result.current.isLoading).toBe(false));

  expect(result.current.form.sourceOfFunds).toEqual(choices);
  expect(api.patch).not.toHaveBeenCalled();
  act(() => result.current.toggleSourceOfFunds('gift'));
  await act(() => result.current.handleSubmit(saved));

  expect(api.patch).toHaveBeenCalledWith('/api/financial-profiles/financial-1/', {
    occupation: 'Engineer',
    sourceOfFunds: [...choices, 'gift'],
    sourceOfFundsOtherText: null,
    intendedUse: 'savings',
    intendedUseOtherText: null,
  });
  expect(saved).toHaveBeenCalledOnce();
});
