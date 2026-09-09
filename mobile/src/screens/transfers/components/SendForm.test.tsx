import { fireEvent, render } from '@testing-library/react-native';
import type { TransferableAsset } from '@ledova/shared';

jest.mock('../../../hooks/useCurrency', () => ({
  useCurrency: () => ({ formatDisplayCurrency: (value: number) => `$${value.toFixed(2)}` }),
}));

import { SendForm } from './SendForm';

const native: TransferableAsset = {
  uuid: 'native',
  symbol: 'ETH',
  name: 'Ether',
  balance: '1',
  marketValue: '100',
  isNative: true,
  decimals: 18,
  chain: 'base',
};
const share: TransferableAsset = {
  uuid: 'share',
  symbol: 'QAT',
  name: 'QA shares',
  balance: '10',
  marketValue: null,
  isNative: false,
  decimals: 0,
  chain: 'base',
  contractAddress: `0x${'3'.repeat(40)}`,
};

function show(asset = share, amount = '2', assets = [native, asset], setAmount = jest.fn()) {
  return render(
    <SendForm
      chainShortName="BASE"
      walletName="Test wallet"
      walletAddress={`0x${'1'.repeat(40)}`}
      selectedAsset={asset}
      transferableAssets={assets}
      toAddress=""
      amount={amount}
      isLoadingHoldings={false}
      prepareError={null}
      selectAsset={jest.fn()}
      setToAddress={jest.fn()}
      setAmount={setAmount}
      useMaxAmount={jest.fn()}
      onOpenAddressScanner={jest.fn()}
    />,
  );
}

describe('fiat values in the mobile send form', () => {
  it('labels an unpriced asset without turning it into zero or NaN', async () => {
    const view = await show();
    expect(view.getByText('Unpriced')).toBeTruthy();
    expect(view.getByText('Unpriced: no fiat estimate available.')).toBeTruthy();
    expect(view.queryByText(/NaN|≈|\$0\.00/)).toBeNull();
  });

  it('keeps the missing-price explanation when only one asset is offered', async () => {
    const setAmount = jest.fn();
    const view = await show(share, '2', [share], setAmount);
    expect(view.getByText('Unpriced: no fiat estimate available.')).toBeTruthy();
    await fireEvent.changeText(view.getByPlaceholderText('0.0'), '3');
    expect(setAmount).toHaveBeenCalledWith('3');
  });

  it.each(['', 'NaN', 'Infinity', '-1'])('treats unusable price %s as unpriced', async (marketValue) => {
    const view = await show({ ...share, marketValue });
    expect(view.getByText('Unpriced')).toBeTruthy();
    expect(view.queryByText(/≈/)).toBeNull();
  });

  it('estimates a priced transfer from the holding quantity and value', async () => {
    const view = await show({ ...share, marketValue: '20' });
    expect(view.getByText('$20.00')).toBeTruthy();
    expect(view.getByText('≈ $4.00')).toBeTruthy();
    expect(view.queryByText(/Unpriced/)).toBeNull();
  });

  it('distinguishes a quoted zero value from a missing price', async () => {
    const view = await show({ ...share, marketValue: '0' });
    expect(view.getByText('$0.00')).toBeTruthy();
    expect(view.getByText('≈ $0.00')).toBeTruthy();
    expect(view.queryByText(/Unpriced/)).toBeNull();
  });

  it.each(['', 'Infinity', 'garbage'])('omits estimates for an unusable amount %s', async (amount) => {
    const view = await show({ ...share, marketValue: '20' }, amount);
    expect(view.queryByText(/≈|NaN|Infinity/)).toBeNull();
  });
});
