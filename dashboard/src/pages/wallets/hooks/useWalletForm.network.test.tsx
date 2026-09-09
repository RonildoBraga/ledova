// @vitest-environment jsdom

import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useWalletForm } from './useWalletForm';

afterEach(cleanup);

it('retains the chosen Base network when an EVM address is entered', () => {
  const submit = vi.fn();
  const { result } = renderHook(() =>
    useWalletForm({ userAccountUuid: 'account', onSubmit: submit, onBatchSubmit: vi.fn() }),
  );
  act(() => result.current.setSelectedChain('base'));
  act(() => result.current.handleAddressChange('0x' + 'a'.repeat(40)));
  act(() => result.current.handleSubmit());
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ userAccount: 'account', chain: 'base' }));
});
