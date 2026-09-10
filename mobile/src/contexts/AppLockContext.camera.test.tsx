import React, { useContext, useLayoutEffect } from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react-native';
import { AppState, Text, type AppStateStatus } from 'react-native';
import type { PermissionResponse } from 'expo-camera';
import { UR, URDecoder, UREncoder } from '@ngraveio/bc-ur';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockGetAccessToken = jest.fn<Promise<string | null>, []>();
const mockReadPreference = jest.fn<Promise<string | null>, []>();
const mockAuthenticate = jest.fn();
const mockDelivered = jest.fn();
const mockCameraMounted = jest.fn();
const mockAccessChanged = jest.fn();
let mockScan: ((result: { data: string }) => void) | undefined;
const listeners = new Set<(state: AppStateStatus) => void>();
const settleOutstanding: (() => void)[] = [];

jest.mock('expo-camera/build/ExpoCameraManager', () => ({
  getCameraPermissionsAsync: () => mockGetPermission(),
  requestCameraPermissionsAsync: () => mockRequestPermission(),
}));
jest.mock('expo-camera', () => {
  const { Camera } = jest.requireActual<typeof import('expo-camera')>('expo-camera');
  const { useEffect } = jest.requireActual<typeof import('react')>('react');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    Camera,
    CameraView: ({ onBarcodeScanned }: { onBarcodeScanned?: typeof mockScan }) => {
      mockScan = onBarcodeScanned;
      useEffect(() => {
        mockCameraMounted();
      }, []);
      return <View testID="camera-preview" />;
    },
  };
});
jest.mock('expo-local-authentication', () => ({
  AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2 },
  hasHardwareAsync: async () => true,
  isEnrolledAsync: async () => true,
  supportedAuthenticationTypesAsync: async () => [1],
  authenticateAsync: (...args: unknown[]) => mockAuthenticate(...args),
}));
jest.mock('expo-secure-store', () => ({
  getItemAsync: () => mockReadPreference(),
  setItemAsync: async () => {},
}));
jest.mock('../services/tokenStorage', () => ({
  getAccessToken: () => mockGetAccessToken(),
  getBiometricLoginState: async () => ({ enabled: false, ready: false }),
}));

import { AppLockProvider, useAppLock } from './AppLockContext';
import { AppLockScreen } from '../components/app-lock/AppLockScreen';
import { QRScanner } from '../components/qr/QRScanner';
import { AnimatedQRScanner } from '../components/qr/AnimatedQRScanner';
import { CameraAccessContext } from './cameraAccess';

let currentLock: ReturnType<typeof useAppLock>;
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

function deferred<T>(fallback: T) {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  settleOutstanding.push(() => resolve(fallback));
  return { promise, resolve };
}

function LockState() {
  const lock = useAppLock();
  useLayoutEffect(() => {
    currentLock = lock;
  }, [lock]);
  const access = useContext(CameraAccessContext);
  useLayoutEffect(() => access.subscribe(() => mockAccessChanged(access.getSnapshot().allowed)), [access]);
  return <Text>{lock.isLocked ? 'locked-control' : 'unlocked-control'}</Text>;
}

function app(visible = true, animated = false) {
  return (
    <AppLockProvider>
      <LockState />
      {animated ? (
        <AnimatedQRScanner active={visible} onComplete={mockDelivered} />
      ) : (
        <QRScanner visible={visible} onScan={mockDelivered} onClose={jest.fn()} />
      )}
      <AppLockScreen />
    </AppLockProvider>
  );
}

async function changeAppState(state: AppStateStatus, reverse = false) {
  await act(() => {
    AppState.currentState = state;
    const ordered = [...listeners];
    if (reverse) ordered.reverse();
    ordered.forEach((listener) => listener(state));
  });
}

async function leaveAndReturn(reverse = false, duration = 3001) {
  await changeAppState('background', reverse);
  jest.setSystemTime(Date.now() + duration);
  await changeAppState('active', reverse);
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-09-10T00:00:00Z'));
  mockGetPermission.mockReset().mockResolvedValue(granted);
  mockRequestPermission.mockReset().mockResolvedValue(granted);
  mockGetAccessToken.mockReset().mockResolvedValue('synthetic-session');
  mockReadPreference.mockReset().mockResolvedValue('true');
  mockAuthenticate.mockReset().mockResolvedValue({ success: true });
  mockAccessChanged.mockReset();
  mockScan = undefined;
  listeners.clear();
  AppState.currentState = 'active';
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') listeners.add(listener);
    return { remove: () => listeners.delete(listener) };
  });
});

afterEach(async () => {
  await cleanup();
  await act(() => settleOutstanding.splice(0).forEach((settle) => settle()));
  jest.clearAllTimers();
  jest.useRealTimers();
});

it.each([false, true])('pauses before the foreground lock decision in either listener order: %s', async (reverse) => {
  const pending = deferred<string | null>(null);
  mockGetAccessToken.mockReturnValue(pending.promise);
  const view = await render(app());
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  await leaveAndReturn(reverse);
  expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => pending.resolve(null));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
  await act(() => mockScan!({ data: 'unlocked-control' }));
  expect(mockDelivered.mock.calls).toEqual([['unlocked-control']]);
});

it.each(['refused', 'rejected'] as const)(
  'keeps the preview paused through a %s unlock, then resumes passively',
  async (result) => {
    const view = await render(app());
    const retained = mockScan!;
    await leaveAndReturn();
    expect(view.getByText('locked-control')).toBeTruthy();
    expect(view.queryByTestId('camera-preview')).toBeNull();
    if (result === 'refused') mockAuthenticate.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    else mockAuthenticate.mockRejectedValueOnce(new Error('synthetic authentication refusal'));
    await fireEvent.press(view.getByText('Unlock with Touch ID'));
    expect(view.getByText('locked-control')).toBeTruthy();
    await act(() => retained({ data: 'while-locked' }));
    expect(mockDelivered).not.toHaveBeenCalled();
    expect(view.queryByTestId('camera-preview')).toBeNull();
    await fireEvent.press(view.getByText('Unlock with Touch ID'));
    expect(view.getByText('unlocked-control')).toBeTruthy();
    expect(view.getByTestId('camera-preview')).toBeTruthy();
    expect(mockRequestPermission).not.toHaveBeenCalled();
    await act(() => {
      retained({ data: 'retired-after-unlock' });
      mockScan!({ data: 'fresh-after-unlock' });
    });
    expect(mockDelivered.mock.calls).toEqual([['fresh-after-unlock']]);
    expect(mockAuthenticate).toHaveBeenLastCalledWith({
      promptMessage: 'Unlock with Touch ID',
      fallbackLabel: 'Use passcode',
      disableDeviceFallback: false,
    });
  },
);

it.each(['background', 'next-evaluation'] as const)('ignores a retired lock decision during %s', async (phase) => {
  const first = deferred<string | null>(null);
  const second = deferred<string | null>(null);
  mockGetAccessToken.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const view = await render(app());
  await leaveAndReturn();
  await changeAppState('background');
  if (phase === 'background') {
    await act(() => first.resolve('synthetic-old-session'));
    expect(view.getByText('unlocked-control')).toBeTruthy();
  }
  jest.setSystemTime(Date.now() + 3001);
  await changeAppState('active');
  expect(mockGetAccessToken).toHaveBeenCalledTimes(2);
  if (phase === 'next-evaluation') {
    await act(() => first.resolve('synthetic-old-session'));
    expect(view.getByText('unlocked-control')).toBeTruthy();
  }
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => second.resolve(null));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('does not let an old foreground decision relock after the setting is disabled', async () => {
  const pending = deferred<string | null>(null);
  mockGetAccessToken.mockReturnValue(pending.promise);
  const view = await render(app());
  await leaveAndReturn();
  await act(async () => {
    expect(await currentLock.setEnabled(false)).toBe(true);
  });
  await act(() => pending.resolve('synthetic-old-session'));
  expect(view.getByText('unlocked-control')).toBeTruthy();
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('withholds the scanner during provider initialization', async () => {
  const preference = deferred<string | null>('false');
  mockReadPreference.mockReturnValue(preference.promise);
  const view = await render(app());
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => preference.resolve('false'));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it.each(['disabled', 'short', 'boundary'] as const)('preserves the existing %s no-lock control', async (control) => {
  if (control === 'disabled') mockReadPreference.mockResolvedValue('false');
  const view = await render(app());
  await leaveAndReturn(false, control === 'short' ? 1000 : control === 'boundary' ? 3000 : 3001);
  expect(mockGetAccessToken).not.toHaveBeenCalled();
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  await act(() => mockScan!({ data: 'allowed-control' }));
  expect(mockDelivered.mock.calls).toEqual([['allowed-control']]);
});

it('keeps a completed scan retired across lock and unlock', async () => {
  const view = await render(app());
  const retained = mockScan!;
  await act(() => retained({ data: 'completed' }));
  await leaveAndReturn();
  await fireEvent.press(view.getByText('Unlock with Touch ID'));
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  await act(() => retained({ data: 'after-unlock' }));
  expect(mockDelivered.mock.calls).toEqual([['completed']]);
});

it('retains real UR fragments through the locked overlay and completes with only the remaining parts', async () => {
  const payload = Buffer.from('synthetic-app-lock-wallet-'.repeat(8));
  const encoder = new UREncoder(UR.fromBuffer(payload), 40);
  const parts = Array.from({ length: encoder.fragmentsLength }, () => encoder.nextPart());
  expect(parts.length).toBeGreaterThan(2);
  const view = await render(app(true, true));
  await act(() => mockScan!({ data: parts[0] }));
  expect(view.getByText(/^Scanning: 1\//)).toBeTruthy();
  await leaveAndReturn();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await fireEvent.press(view.getByText('Unlock with Touch ID'));
  await act(() => parts.slice(1).forEach((data) => mockScan!({ data })));
  expect(mockDelivered).toHaveBeenCalledTimes(1);
  const decoder = new URDecoder();
  expect(decoder.receivePart(mockDelivered.mock.calls[0][0])).toBe(true);
  expect(decoder.resultUR().decodeCBOR()).toEqual(payload);
});

it('does not use a pending camera grant while locked or reprompt merely on unlock', async () => {
  const grant = deferred(granted);
  mockGetPermission.mockResolvedValue(undetermined);
  mockRequestPermission.mockReturnValue(grant.promise);
  const view = await render(app());
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  await leaveAndReturn();
  await act(() => grant.resolve(granted));
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  await fireEvent.press(view.getByText('Unlock with Touch ID'));
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  mockGetPermission.mockResolvedValue(granted);
  await view.rerender(app(false));
  await view.rerender(app());
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('refuses a retained callback before the camera subscriber or React commit handles the pause', async () => {
  await render(app());
  const retained = mockScan!;
  mockAccessChanged.mockImplementation((allowed: boolean) => {
    if (!allowed) retained({ data: 'before-camera-retirement' });
  });
  await changeAppState('background');
  expect(mockAccessChanged).toHaveBeenCalledWith(false);
  expect(mockDelivered).not.toHaveBeenCalled();
  await changeAppState('active');
  await act(() => mockScan!({ data: 'current-control' }));
  expect(mockDelivered.mock.calls).toEqual([['current-control']]);
});

it('stays paused when authentication succeeds in the background and preserves the unlock grace', async () => {
  const authentication = deferred({ success: false });
  mockAuthenticate.mockReturnValue(authentication.promise);
  const view = await render(app());
  await leaveAndReturn();
  let unlocking!: Promise<boolean>;
  await act(() => {
    unlocking = currentLock.unlock();
  });
  await changeAppState('inactive');
  jest.setSystemTime(Date.now() + 3001);
  await changeAppState('active');
  expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await changeAppState('background');
  await act(async () => {
    authentication.resolve({ success: true });
    expect(await unlocking).toBe(true);
  });
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  jest.setSystemTime(Date.now() + 3001);
  await changeAppState('active');
  expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
});

it('keeps a new opening passive when it starts behind the lock overlay', async () => {
  const view = await render(app(false));
  await leaveAndReturn();
  await view.rerender(app());
  expect(mockGetPermission).not.toHaveBeenCalled();
  mockGetPermission.mockResolvedValue(undetermined);
  await fireEvent.press(view.getByText('Unlock with Touch ID'));
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await view.rerender(app(false));
  await view.rerender(app());
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('retires a pending lock decision on unmount without releasing a different provider', async () => {
  const previous = deferred<string | null>(null);
  const current = deferred<string | null>(null);
  mockGetAccessToken.mockReturnValueOnce(previous.promise).mockReturnValueOnce(current.promise);
  const oldView = await render(app());
  await leaveAndReturn();
  await oldView.unmount();
  expect(listeners.size).toBe(0);
  const view = await render(app());
  await leaveAndReturn();
  await act(() => previous.resolve(null));
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
  await act(() => current.resolve(null));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockGetPermission).toHaveBeenCalledTimes(3);
});

it('does not admit a camera without an initialized app-lock provider', async () => {
  const view = await render(<QRScanner visible onScan={mockDelivered} onClose={jest.fn()} />);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).not.toHaveBeenCalled();
  await view.unmount();
  const initialized = await render(app());
  expect(initialized.getByTestId('camera-preview')).toBeTruthy();
});

it('does not turn a pending getter into a permission request after the app locks', async () => {
  const permission = deferred(undetermined);
  mockGetPermission.mockReturnValueOnce(permission.promise);
  const view = await render(app());
  await leaveAndReturn();
  await act(() => permission.resolve(undetermined));
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await fireEvent.press(view.getByText('Unlock with Touch ID'));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
});

it('keeps an initially backgrounded opening passive on the first foreground', async () => {
  AppState.currentState = 'background';
  mockGetPermission.mockResolvedValue(undetermined);
  const view = await render(app());
  expect(mockGetPermission).not.toHaveBeenCalled();
  await changeAppState('active');
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await view.rerender(app(false));
  await view.rerender(app());
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('ignores retained lifecycle listeners after provider teardown while a current provider still evaluates', async () => {
  const view = await render(app());
  const retained = [...listeners];
  await view.unmount();
  await act(() => retained.forEach((listener) => listener('background')));
  jest.setSystemTime(Date.now() + 3001);
  await act(() => retained.forEach((listener) => listener('active')));
  expect(mockGetAccessToken).not.toHaveBeenCalled();
  const current = await render(app());
  await leaveAndReturn();
  expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
  expect(current.getByText('locked-control')).toBeTruthy();
});
