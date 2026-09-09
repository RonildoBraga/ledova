import { act, renderHook } from '@testing-library/react-native';
import { useAddWalletForm } from './useAddWalletForm';

it('retains the selected Base network after entering and scanning an EVM address', async () => {
  const submit = jest.fn();
  const { result } = await renderHook(() =>
    useAddWalletForm({ userAccountUuid: 'account', onSubmit: submit, onBatchSubmit: jest.fn() }),
  );
  await act(async () => result.current!.setSelectedChain('base'));
  await act(async () => result.current!.handleAddressChange('0x' + 'a'.repeat(40)));
  await act(async () => result.current!.handleSubmit());
  expect(submit).toHaveBeenLastCalledWith(expect.objectContaining({ userAccount: 'account', chain: 'base' }));
  await act(async () => result.current!.handleQRScan('0x' + 'b'.repeat(40)));
  await act(async () => result.current!.handleSubmit());
  expect(submit).toHaveBeenLastCalledWith(
    expect.objectContaining({ userAccount: 'account', chain: 'base', address: '0x' + 'b'.repeat(40) }),
  );
});
