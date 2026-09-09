import { render } from '@testing-library/react-native';
import type { TransactionData } from '@ledova/shared';
import { ReviewTransaction } from './ReviewTransaction';

it.each(['BASE', 'ETH'])('shows the ETH amount and gas details on %s', async (chainShortName) => {
  const data: TransactionData = {
    transaction: '',
    fromAddress: '0x1111',
    toAddress: '0x2222',
    amountEth: '1',
    gasCostEth: '0.01',
    totalCostEth: '1.01',
    gasPriceGwei: '2',
    gasLimit: '21000',
  };
  const view = await render(<ReviewTransaction transactionData={data} chainShortName={chainShortName} />);
  expect(view.getByText('1 ETH')).toBeTruthy();
  expect(view.getByText('0.01 ETH')).toBeTruthy();
  expect(view.getByText('1.01 ETH')).toBeTruthy();
  expect(view.getByText('Gas Limit')).toBeTruthy();
  expect(view.getByText('21000')).toBeTruthy();
  expect(view.queryByText('1 BASE')).toBeNull();
});
