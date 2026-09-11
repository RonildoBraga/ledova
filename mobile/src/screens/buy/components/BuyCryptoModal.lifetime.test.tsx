import React, { useState } from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { getSessionEpoch, invalidateSessionScope } from '../../../services/sessionScope';

const mockWidget = jest.fn();
const mockNavigate = jest.fn();
const mockWallets = [{ uuid: 'synthetic-wallet', chain: 'base' }];
const pending: ((value: { data: { url: string } }) => void)[] = [];

jest.mock('@ledova/shared', () => ({
  ...jest.requireActual('@ledova/shared'),
  getOnRampWidgetUrl: (...args: unknown[]) => mockWidget(...args),
  getUserVerificationStatus: () => ({ type: 'verified' }),
}));
jest.mock('@tanstack/react-query', () => ({
  ...jest.requireActual('@tanstack/react-query'),
  useQuery: ({ queryKey, enabled }: { queryKey: string[]; enabled?: boolean }) =>
    queryKey[0] === 'userProfiles'
      ? { data: { data: { results: [{}] } }, isLoading: false }
      : { data: { data: { results: enabled ? mockWallets : [] } }, isLoading: false },
}));
jest.mock('../../../hooks/useCurrency', () => ({ useCurrency: () => ({ formatDisplayCurrency: String }) }));
jest.mock('../../../services/apiClient', () => ({ apiClient: {} }));
jest.mock('../../../contexts', () => ({
  useAppTheme: () => jest.requireActual('@ledova/shared').DESIGN_TOKENS,
  useThemedStyles: () => ({}),
}));
jest.mock('../../../components/modal', () => ({
  CustomModal: ({
    visible,
    children,
    onCancel,
  }: {
    visible: boolean;
    children: React.ReactNode;
    onCancel: () => void;
  }) => {
    const { View, Button } = jest.requireActual<typeof import('react-native')>('react-native');
    return visible ? (
      <View>
        {children}
        <Button title="Cancel" onPress={onCancel} />
      </View>
    ) : null;
  },
}));

import { BuyCryptoModal } from './BuyCryptoModal';

let client: QueryClient;

function Harness({ account = 'synthetic-account', shown = true }: { account?: string; shown?: boolean }) {
  const [open, setOpen] = useState(true);
  return (
    <QueryClientProvider client={client}>
      <BuyCryptoModal
        visible={open && shown}
        initialAsset="ETH"
        userAccountUuid={account}
        onClose={() => setOpen(false)}
        onNavigateToProfile={jest.fn()}
        onNavigateToWebView={(url, epoch) => {
          setOpen(false);
          mockNavigate(url, epoch);
        }}
      />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { mutations: { retry: false, gcTime: Infinity } } });
  pending.length = 0;
  mockWidget.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));
});

afterEach(async () => {
  await cleanup();
  await act(() =>
    pending.splice(0).forEach((resolve) => resolve({ data: { url: 'https://provider.example.test/late' } })),
  );
  client.clear();
});

async function respond(url = 'https://provider.example.test/current') {
  await act(async () => {
    pending.shift()!({ data: { url } });
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

it('carries the requesting session into a current provider opening', async () => {
  const epoch = getSessionEpoch();
  await render(<Harness />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(1));
  await respond();
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('https://provider.example.test/current', epoch));
  expect(mockNavigate).toHaveBeenCalledTimes(1);
});

it('refuses a URL fetched for a previous session', async () => {
  await render(<Harness />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(1));
  await act(() => invalidateSessionScope());
  await respond();
  await waitFor(() => expect(client.isMutating()).toBe(0));
  expect(mockNavigate).not.toHaveBeenCalled();
});

it('does not reopen the provider after cancelling its pending request', async () => {
  const view = await render(<Harness />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(1));
  await fireEvent.press(view.getByText('Cancel'));
  await respond();
  await waitFor(() => expect(client.isMutating()).toBe(0));
  expect(mockNavigate).not.toHaveBeenCalled();
});

it('rejects the previous account response while accepting the current account', async () => {
  const view = await render(<Harness />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(1));
  await view.rerender(<Harness account="synthetic-account-b" />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(2));
  await respond('https://provider.example.test/old-account');
  expect(mockNavigate).not.toHaveBeenCalled();
  await respond();
  await waitFor(() =>
    expect(mockNavigate).toHaveBeenCalledWith('https://provider.example.test/current', getSessionEpoch()),
  );
  expect(mockNavigate).toHaveBeenCalledTimes(1);
});

it('does not navigate after the requesting screen unmounts', async () => {
  const view = await render(<Harness />);
  await waitFor(() => expect(mockWidget).toHaveBeenCalledTimes(1));
  await view.unmount();
  await respond();
  await waitFor(() => expect(client.isMutating()).toBe(0));
  expect(mockNavigate).not.toHaveBeenCalled();
});
