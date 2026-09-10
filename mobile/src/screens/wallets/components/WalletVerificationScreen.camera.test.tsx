import React, { useLayoutEffect } from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { AppState, Platform, type AppStateStatus } from 'react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PermissionResponse } from 'expo-camera';
import type { Wallet } from '@ledova/shared';
import { ETHSignature } from '@keystonehq/bc-ur-registry-eth';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestChallenge = jest.fn();
const mockVerifySignature = jest.fn();
const mockGoBack = jest.fn();
const mockGetAccessToken = jest.fn<Promise<string | null>, []>();
const mockLockPreference = jest.fn<Promise<string | null>, []>();
const mockNavigation = { goBack: mockGoBack };
let mockScan: ((result: { data: string }) => void) | undefined;
let mockFocused = true;
let mockWallet: Wallet;
const listeners = new Set<(state: AppStateStatus) => void>();
let client: QueryClient;

jest.mock('uuid', () => ({ v4: () => '11111111-1111-4111-8111-111111111111' }));

jest.mock('expo', () => {
  const actual = jest.requireActual<typeof import('expo')>('expo');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return { ...actual, requireNativeView: () => View };
});

jest.mock('expo-camera/build/ExpoCameraManager', () => ({
  getCameraPermissionsAsync: () => mockGetPermission(),
  requestCameraPermissionsAsync: () => mockRequestPermission(),
}));
jest.mock('expo-camera', () => {
  const { Camera, useCameraPermissions } = jest.requireActual<typeof import('expo-camera')>('expo-camera');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    Camera,
    useCameraPermissions,
    CameraView: ({ onBarcodeScanned }: { onBarcodeScanned?: typeof mockScan }) => {
      mockScan = onBarcodeScanned;
      return <View testID="camera-preview" />;
    },
  };
});
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => mockNavigation,
  useRoute: () => ({ params: { wallet: mockWallet } }),
  useIsFocused: () => mockFocused,
}));
jest.mock('@ledova/shared', () => ({
  ...jest.requireActual('@ledova/shared'),
  requestVerificationChallenge: (...args: unknown[]) => mockRequestChallenge(...args),
  verifyWalletSignature: (...args: unknown[]) => mockVerifySignature(...args),
}));
jest.mock('../../../hooks/useUserPreferences', () => ({
  useUserPreferences: () => ({ selectedAccount: { uuid: 'synthetic-account' } }),
}));
jest.mock('../../../services/apiClient', () => ({ apiClient: {} }));
jest.mock('../../../services/secureKeyStorage', () => ({ getSeedPhrase: async () => null }));
jest.mock('../../../services/tokenStorage', () => ({
  getAccessToken: () => mockGetAccessToken(),
  getBiometricLoginState: async () => ({ enabled: false, ready: false }),
}));
jest.mock('expo-secure-store', () => ({ getItemAsync: () => mockLockPreference() }));
jest.mock('expo-local-authentication', () => ({
  AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2 },
  hasHardwareAsync: async () => true,
  isEnrolledAsync: async () => true,
  supportedAuthenticationTypesAsync: async () => [1],
  authenticateAsync: async () => ({ success: true }),
}));

import { WalletVerificationScreen } from './WalletVerificationScreen';
import { AppLockProvider, useAppLock } from '../../../contexts/AppLockContext';

let currentLock: ReturnType<typeof useAppLock>;

function LockControl() {
  const lock = useAppLock();
  useLayoutEffect(() => {
    currentLock = lock;
  }, [lock]);
  return null;
}

const granted: PermissionResponse = {
  status: 'granted' as PermissionResponse['status'],
  granted: true,
  canAskAgain: true,
  expires: 'never',
};
const undetermined: PermissionResponse = {
  ...granted,
  status: 'undetermined' as PermissionResponse['status'],
  granted: false,
};
const signatureBytes = Buffer.alloc(65, 1);
const signatureQR = new ETHSignature(signatureBytes).toUREncoder(1000).nextPart();

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mockWallet = {
    uuid: 'synthetic-wallet',
    userAccount: 'synthetic-account',
    address: '0x' + 'a'.repeat(40),
    chain: 'base',
    signingPreference: 'hardware',
    derivationPath: "m/44'/60'/0'/0/0",
    masterFingerprint: 'aabbccdd',
    verificationStatus: 'PENDING',
    nativeBalance: '0',
    nativeMarketValue: '0',
    marketValue: '0',
    createdAt: '2026-09-10T00:00:00Z',
    updatedAt: '2026-09-10T00:00:00Z',
  };
  mockRequestChallenge.mockReset().mockResolvedValue({ data: { challenge: 'synthetic-verification-challenge' } });
  mockVerifySignature.mockReset().mockResolvedValue({ data: {} });
  mockGetPermission.mockReset().mockResolvedValue(granted);
  mockGetAccessToken.mockReset().mockResolvedValue(null);
  mockLockPreference.mockReset().mockResolvedValue('false');
  mockRequestPermission.mockReset().mockResolvedValue(granted);
  mockFocused = true;
  mockScan = undefined;
  AppState.currentState = 'active';
  listeners.clear();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') listeners.add(listener);
    return { remove: () => listeners.delete(listener) };
  });
});

afterEach(async () => {
  await cleanup();
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <AppLockProvider>
      <LockControl />
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </AppLockProvider>
  );
}

async function openScanner() {
  const view = await render(<WalletVerificationScreen />, { wrapper });
  await fireEvent.press(view.getByText('Start'));
  await waitFor(() => expect(view.getByText('Continue')).toBeTruthy());
  await fireEvent.press(view.getByText('Continue'));
  return view;
}

async function changeAppState(state: AppStateStatus) {
  await act(() => {
    AppState.currentState = state;
    listeners.forEach((listener) => listener(state));
  });
}

it('keeps Android verification pending for its own window and rejects a replaced session callback', async () => {
  jest.replaceProperty(Platform, 'OS', 'android');
  const view = await openScanner();
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  const firstOwner = view.getByTestId('camera-window');
  const update = (owner: typeof firstOwner, generation: number, allowed: boolean) =>
    fireEvent(owner, 'windowChange', { nativeEvent: { ownerId: owner.props.ownerId, generation, allowed } });
  await update(firstOwner, 1, true);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  const previous = mockScan!;
  await update(firstOwner, 2, false);
  await act(() => previous({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  await fireEvent.press(view.getByText('Back'));
  await fireEvent.press(view.getByText('Continue'));
  const currentOwner = view.getByTestId('camera-window');
  expect(currentOwner.props.ownerId).not.toBe(firstOwner.props.ownerId);
  await act(() =>
    firstOwner.props.onWindowChange({
      nativeEvent: { ownerId: firstOwner.props.ownerId, generation: 3, allowed: true },
    }),
  );
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await update(currentOwner, 1, true);
  await act(() => previous({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  await act(() => mockScan!({ data: signatureQR }));
  await waitFor(() => expect(view.getByText('Verification Successful!')).toBeTruthy());
  expect(mockVerifySignature).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
});

it('requests an undetermined permission only after continuing from the challenge', async () => {
  mockGetPermission.mockResolvedValue(undetermined);
  const view = await render(<WalletVerificationScreen />, { wrapper });
  expect(view.getByText('Start')).toBeTruthy();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await fireEvent.press(view.getByText('Start'));
  await waitFor(() => expect(view.getByText('Continue')).toBeTruthy());
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();

  await fireEvent.press(view.getByText('Continue'));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
}, 15_000);

it('decodes a real signature once and does not submit retained frames after success', async () => {
  const view = await openScanner();
  const retained = mockScan!;
  await act(() => {
    retained({ data: signatureQR });
    retained({ data: signatureQR });
  });
  await waitFor(() => expect(view.getByText('Verification Successful!')).toBeTruthy());
  expect(mockVerifySignature.mock.calls).toEqual([
    [{}, 'synthetic-wallet', { signature: '0x' + signatureBytes.toString('hex') }, 'synthetic-account'],
  ]);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await changeAppState('background');
  await changeAppState('active');
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).toHaveBeenCalledTimes(1);
});

it('keeps scanning after an unsupported code and accepts the following valid signature', async () => {
  const view = await openScanner();
  const scan = mockScan!;
  await act(() => scan({ data: 'ordinary-qr-control' }));
  const guidance = view.queryByText(/This QR code is not a supported signature/);
  expect(mockVerifySignature).not.toHaveBeenCalled();
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  await act(() => scan({ data: signatureQR }));
  await waitFor(() => expect(mockVerifySignature).toHaveBeenCalledTimes(1));
  expect(guidance).toBeTruthy();
});

it('rejects a callback after Back and keeps the next scan step usable', async () => {
  const view = await openScanner();
  const previous = mockScan!;
  await fireEvent.press(view.getByText('Back'));
  await act(() => previous({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await fireEvent.press(view.getByText('Continue'));
  await act(() => previous({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  await act(() => mockScan!({ data: signatureQR }));
  await waitFor(() => expect(mockVerifySignature).toHaveBeenCalledTimes(1));
});

it('rejects a callback after the verification screen unmounts', async () => {
  const view = await openScanner();
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  const retained = mockScan!;
  await view.unmount();
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
});

it('pauses for a covered route and rejects its old callback when focused again', async () => {
  const view = await openScanner();
  const retained = mockScan!;
  mockFocused = false;
  await view.rerender(<WalletVerificationScreen />);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  mockFocused = true;
  await view.rerender(<WalletVerificationScreen />);
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  await act(() => mockScan!({ data: signatureQR }));
  await waitFor(() => expect(mockVerifySignature).toHaveBeenCalledTimes(1));
});

it('refreshes settings while scanning and ignores background events', async () => {
  const view = await openScanner();
  const retained = mockScan!;
  await changeAppState('background');
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  mockGetPermission.mockResolvedValue({ ...undetermined, canAskAgain: false });
  await changeAppState('active');
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await changeAppState('background');
  mockGetPermission.mockResolvedValue(granted);
  await changeAppState('active');
  await act(() => mockScan!({ data: signatureQR }));
  await waitFor(() => expect(mockVerifySignature).toHaveBeenCalledTimes(1));
  expect(mockRequestPermission).not.toHaveBeenCalled();
});

it.each(['get', 'request'] as const)('shows a native %s failure with a usable Back action', async (operation) => {
  mockGetPermission.mockResolvedValue(undetermined);
  const failing = operation === 'get' ? mockGetPermission : mockRequestPermission;
  failing.mockRejectedValue(new Error('synthetic-permission-failure'));
  const view = await openScanner();
  expect(view.getByText(/Camera permission is unavailable/)).toBeTruthy();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await fireEvent.press(view.getByText('Back'));
  expect(view.getByText('Continue')).toBeTruthy();
  expect(failing).toHaveBeenCalledTimes(1);
});

it('does not involve the camera when verifying a software wallet', async () => {
  mockWallet.signingPreference = 'software';
  const view = await render(<WalletVerificationScreen />, { wrapper });
  await waitFor(() => expect(mockRequestChallenge).toHaveBeenCalledTimes(1));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('keeps the verification step and challenge through app lock without submitting paused frames', async () => {
  mockLockPreference.mockResolvedValue('true');
  mockGetAccessToken.mockResolvedValue('synthetic-session');
  const now = jest.spyOn(Date, 'now').mockReturnValue(10000);
  const view = await openScanner();
  const retained = mockScan!;
  await changeAppState('background');
  now.mockReturnValue(13001);
  await changeAppState('active');
  expect(currentLock.isLocked).toBe(true);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => retained({ data: signatureQR }));
  expect(mockVerifySignature).not.toHaveBeenCalled();
  await act(async () => {
    expect(await currentLock.unlock()).toBe(true);
  });
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockRequestChallenge).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await act(() => {
    retained({ data: signatureQR });
    mockScan!({ data: signatureQR });
  });
  await waitFor(() => expect(view.getByText('Verification Successful!')).toBeTruthy());
  expect(mockVerifySignature.mock.calls).toEqual([
    [{}, 'synthetic-wallet', { signature: '0x' + signatureBytes.toString('hex') }, 'synthetic-account'],
  ]);
});
