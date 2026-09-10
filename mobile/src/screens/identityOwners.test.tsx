import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { invalidateSessionScope } from '../services/sessionScope';
import { VerificationModal } from './user-profile/components/VerificationModal';
import { IdentityVerificationScreen } from './signup/identity-verification/IdentityVerificationScreen';

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useIsFocused: () => mockFocused,
  useNavigation: () => ({ navigate: jest.fn() }),
}));
jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn(), post: jest.fn() } }));
jest.mock('./signup/identity-verification/components/VerificationFormModal', () => {
  const { View, Text, Pressable } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    VerificationFormModal: ({
      visible,
      accessToken,
      formUrl,
      onComplete,
    }: {
      visible: boolean;
      accessToken: string | null;
      formUrl: string | null;
      onComplete: () => void;
    }) =>
      visible && (accessToken || formUrl) ? (
        <View testID="provider-owned-form">
          <Pressable onPress={onComplete}>
            <Text>Finish synthetic provider form</Text>
          </Pressable>
        </View>
      ) : null,
  };
});

const get = apiClient.get as jest.Mock;
const post = apiClient.post as jest.Mock;
const close = jest.fn();
const refresh = jest.fn();
let client: QueryClient;
const settleOutstanding: (() => void)[] = [];

beforeEach(() => {
  mockFocused = true;
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  get.mockReset().mockResolvedValue({ data: { isVerified: false, status: 'init' } });
  post.mockReset().mockResolvedValue({ data: { accessToken: 'synthetic-owner-token', formUrl: null } });
});

afterEach(async () => {
  await cleanup();
  await act(() => settleOutstanding.splice(0).forEach((settle) => settle()));
  client.clear();
});

function owner(kind: 'profile' | 'signup', visible = true) {
  return (
    <QueryClientProvider client={client}>
      {kind === 'profile' ? (
        <VerificationModal visible={visible} onClose={close} onRefresh={refresh} />
      ) : (
        <IdentityVerificationScreen />
      )}
    </QueryClientProvider>
  );
}

it.each(['profile', 'signup'] as const)('keeps the normal %s launch and submission progression', async (kind) => {
  const view = await render(owner(kind));
  await waitFor(() => expect(view.queryByText('Loading status...')).toBeNull());
  await fireEvent.press(view.getByText(kind === 'profile' ? 'Start' : 'Start Verification'));
  await waitFor(() => expect(view.getByTestId('provider-owned-form')).toBeTruthy());
  expect(post).toHaveBeenCalledTimes(1);
  await fireEvent.press(view.getByText('Finish synthetic provider form'));
  expect(view.queryByTestId('provider-owned-form')).toBeNull();
  if (kind === 'signup') expect(view.getByText('Continue')).toBeTruthy();
});

it.each(['profile', 'signup'] as const)('retires a pending %s launch when its route loses focus', async (kind) => {
  let resolve!: (value: unknown) => void;
  post.mockReturnValue(
    new Promise((accept) => {
      resolve = accept;
    }),
  );
  settleOutstanding.push(() => resolve({ data: { accessToken: 'synthetic-late-token', formUrl: null } }));
  const view = await render(owner(kind));
  await waitFor(() => expect(view.queryByText('Loading status...')).toBeNull());
  let pressing!: Promise<void>;
  await act(() => {
    pressing = fireEvent.press(view.getByText(kind === 'profile' ? 'Start' : 'Start Verification'));
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  mockFocused = false;
  await view.rerender(owner(kind));
  await act(async () => {
    resolve({ data: { accessToken: 'synthetic-late-token', formUrl: null } });
    await pressing;
  });
  mockFocused = true;
  await view.rerender(owner(kind));
  expect(view.queryByTestId('provider-owned-form')).toBeNull();
  post.mockResolvedValue({ data: { accessToken: 'synthetic-current-token', formUrl: null } });
  await fireEvent.press(view.getByText(kind === 'profile' ? 'Start' : 'Start Verification'));
  await waitFor(() => expect(view.getByTestId('provider-owned-form')).toBeTruthy());
});

it('removes the profile provider when the parent modal is hidden and permits a fresh opening', async () => {
  const view = await render(owner('profile'));
  await waitFor(() => expect(view.queryByText('Loading status...')).toBeNull());
  await fireEvent.press(view.getByText('Start'));
  await waitFor(() => expect(view.getByTestId('provider-owned-form')).toBeTruthy());
  await view.rerender(owner('profile', false));
  expect(view.queryByTestId('provider-owned-form')).toBeNull();
  await view.rerender(owner('profile'));
  expect(view.queryByTestId('provider-owned-form')).toBeNull();
  await fireEvent.press(view.getByText('Start'));
  await waitFor(() => expect(view.getByTestId('provider-owned-form')).toBeTruthy());
});

it.each(['profile', 'signup'] as const)('removes the %s form on session retirement', async (kind) => {
  const view = await render(owner(kind));
  await waitFor(() => expect(view.queryByText('Loading status...')).toBeNull());
  await fireEvent.press(view.getByText(kind === 'profile' ? 'Start' : 'Start Verification'));
  await waitFor(() => expect(view.getByTestId('provider-owned-form')).toBeTruthy());
  await act(() => invalidateSessionScope());
  expect(view.queryByTestId('provider-owned-form')).toBeNull();
});
