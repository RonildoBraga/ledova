import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import type { PermissionResponse } from 'expo-camera';
import { AppState, type AppStateStatus } from 'react-native';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockCameraMounted = jest.fn();
const mockCameraUnmounted = jest.fn();
let mockScan: ((result: { data: string }) => void) | undefined;
const appStateListeners = new Set<(state: AppStateStatus) => void>();

async function changeAppState(state: AppStateStatus) {
  await act(() => {
    AppState.currentState = state;
    appStateListeners.forEach((listener) => listener(state));
  });
}

jest.mock('expo-camera/build/ExpoCameraManager', () => ({
  getCameraPermissionsAsync: () => mockGetPermission(),
  requestCameraPermissionsAsync: () => mockRequestPermission(),
}));

jest.mock('expo-camera', () => {
  const { Camera, useCameraPermissions } = jest.requireActual<typeof import('expo-camera')>('expo-camera');
  const { useEffect } = jest.requireActual<typeof import('react')>('react');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    Camera,
    useCameraPermissions,
    CameraView: ({ onBarcodeScanned }: { onBarcodeScanned?: typeof mockScan }) => {
      mockScan = onBarcodeScanned;
      useEffect(() => {
        mockCameraMounted();
        return () => {
          mockCameraUnmounted();
        };
      }, []);
      return <View testID="camera-preview" />;
    },
  };
});

jest.mock('../modal', () => {
  const { View, Pressable, Text } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    CustomModal: ({ children, onClose }: { children: React.ReactNode; onClose: () => void }) => (
      <View>
        {children}
        <Pressable onPress={onClose}>
          <Text>Cancel</Text>
        </Pressable>
      </View>
    ),
  };
});

import { QRScanner } from './QRScanner';

const undetermined: PermissionResponse = {
  status: 'undetermined' as PermissionResponse['status'],
  granted: false,
  canAskAgain: true,
  expires: 'never',
};
const granted: PermissionResponse = {
  ...undetermined,
  status: 'granted' as PermissionResponse['status'],
  granted: true,
};
const denied: PermissionResponse = { ...undetermined, status: 'denied' as PermissionResponse['status'] };

function deferredPermission() {
  let resolve!: (value: PermissionResponse) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<PermissionResponse>((accept, refuse) => {
    resolve = accept;
    reject = refuse;
  });
  return { promise, resolve, reject };
}

function scanner(visible: boolean, onScan = jest.fn(), onClose = jest.fn()) {
  return <QRScanner visible={visible} onScan={onScan} onClose={onClose} />;
}

beforeEach(() => {
  mockGetPermission.mockReset().mockResolvedValue(undetermined);
  mockRequestPermission.mockReset().mockResolvedValue(denied);
  AppState.currentState = 'active';
  appStateListeners.clear();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') appStateListeners.add(listener);
    return { remove: () => appStateListeners.delete(listener) };
  });
  mockScan = undefined;
});

it('keeps hidden scanners idle without reading or requesting permission', async () => {
  const initial = deferredPermission();
  mockGetPermission.mockReturnValue(initial.promise);
  const view = await render(
    <>
      {scanner(false)}
      {scanner(false)}
    </>,
  );
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(mockCameraMounted).not.toHaveBeenCalled();

  await act(() => initial.resolve(undetermined));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('requests once when opened and the permission getter reports undetermined', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const onScan = jest.fn();
  const view = await render(scanner(false, onScan));
  expect(mockRequestPermission).not.toHaveBeenCalled();

  await view.rerender(scanner(true, onScan));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();

  await act(() => request.resolve(granted));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  expect(mockScan).toEqual(expect.any(Function));
  const scan = mockScan!;
  await act(() => {
    scan({ data: 'wallet-qr-control' });
    scan({ data: 'duplicate-camera-event' });
  });
  expect(onScan.mock.calls).toEqual([['wallet-qr-control']]);
});

it('waits for the getter when opened before permission is known', async () => {
  const initial = deferredPermission();
  mockGetPermission.mockReturnValue(initial.promise);
  const view = await render(scanner(true));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();

  await act(() => initial.resolve(undetermined));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
});

it('does not request when closed before the getter resolves', async () => {
  const initial = deferredPermission();
  mockGetPermission.mockReturnValue(initial.promise);
  const view = await render(scanner(true));
  await view.rerender(scanner(false));
  await act(() => initial.resolve(undetermined));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(mockCameraMounted).not.toHaveBeenCalled();
});

it('does not loop on denial and permits a new attempt on a later opening', async () => {
  mockRequestPermission.mockResolvedValue(denied);
  const view = await render(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(mockCameraMounted).not.toHaveBeenCalled();

  await view.rerender(scanner(false));
  mockRequestPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(2);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('keeps permanent denial readable without requesting or mounting a preview', async () => {
  mockGetPermission.mockResolvedValue({ ...denied, canAskAgain: false });
  const onClose = jest.fn();
  const view = await render(scanner(true, jest.fn(), onClose));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  expect(mockCameraMounted).not.toHaveBeenCalled();
  await fireEvent.press(view.getByText('Cancel'));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it('shares an outstanding attempt across quick close and reopen actions', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  await view.rerender(scanner(false));
  await view.rerender(scanner(true));
  await view.rerender(scanner(false));
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);

  await act(() => request.resolve(denied));
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();

  await view.rerender(scanner(false));
  mockRequestPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(2);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('does not mount a hidden preview when an outstanding request is granted', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(scanner(true));
  await view.rerender(scanner(false));
  await act(() => request.resolve(granted));
  expect(mockCameraMounted).not.toHaveBeenCalled();

  mockGetPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('handles a rejected permission request without a retry loop', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(scanner(true));
  await act(() => request.reject(new Error('native-permission-failure')));
  expect(view.getByText('Camera permission is unavailable. Close the scanner and try again.')).toBeTruthy();
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(mockCameraMounted).not.toHaveBeenCalled();

  await view.rerender(scanner(false));
  mockRequestPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(2);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('mounts an already permitted preview only while open and resets scanning on reopen', async () => {
  mockGetPermission.mockResolvedValue(granted);
  const onScan = jest.fn();
  const view = await render(scanner(false, onScan));
  expect(mockCameraMounted).not.toHaveBeenCalled();
  await view.rerender(scanner(true, onScan));
  expect(mockCameraMounted).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(mockScan).toEqual(expect.any(Function));
  const firstScan = mockScan!;
  await act(() => firstScan({ data: 'first-opening' }));

  await view.rerender(scanner(false, onScan));
  expect(mockCameraUnmounted).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => firstScan({ data: 'late-closed-event' }));
  expect(onScan.mock.calls).toEqual([['first-opening']]);

  await view.rerender(scanner(true, onScan));
  expect(mockCameraMounted).toHaveBeenCalledTimes(2);
  expect(mockScan).toEqual(expect.any(Function));
  await act(() => mockScan!({ data: 'second-opening' }));
  expect(onScan.mock.calls).toEqual([['first-opening'], ['second-opening']]);
});

it('ignores a retained scan callback after the scanner owner unmounts', async () => {
  mockGetPermission.mockResolvedValue(granted);
  const onScan = jest.fn();
  const view = await render(scanner(true, onScan));
  expect(mockCameraMounted).toHaveBeenCalledTimes(1);
  expect(mockScan).toEqual(expect.any(Function));
  const scan = mockScan!;
  await view.unmount();
  expect(mockCameraUnmounted).toHaveBeenCalledTimes(1);
  await act(() => scan({ data: 'event-after-owner-unmount' }));
  expect(onScan).not.toHaveBeenCalled();
});

it('ignores an earlier opening callback without consuming the current scan', async () => {
  mockGetPermission.mockResolvedValue(granted);
  const onScan = jest.fn();
  const view = await render(scanner(true, onScan));
  expect(mockScan).toEqual(expect.any(Function));
  const earlierScan = mockScan!;
  await view.rerender(scanner(false, onScan));
  await view.rerender(scanner(true, onScan));
  expect(mockScan).toEqual(expect.any(Function));
  const currentScan = mockScan!;
  await act(() => earlierScan({ data: 'event-from-earlier-opening' }));
  expect(onScan).not.toHaveBeenCalled();
  await act(() => currentScan({ data: 'current-opening-control' }));
  expect(onScan.mock.calls).toEqual([['current-opening-control']]);
});

it('handles an initial getter rejection and recovers on a later opening', async () => {
  mockGetPermission.mockRejectedValue(new Error('native-getter-failure'));
  const view = await render(scanner(true));
  expect(view.getByText(/Camera permission is unavailable/)).toBeTruthy();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(mockCameraMounted).not.toHaveBeenCalled();
  await view.rerender(scanner(false));
  mockGetPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('refreshes grants and revocations after settings without prompting again', async () => {
  const onScan = jest.fn();
  const view = await render(scanner(true, onScan));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  await changeAppState('background');
  mockGetPermission.mockResolvedValue(granted);
  await changeAppState('active');
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  const beforeSettings = mockScan!;

  await changeAppState('inactive');
  expect(mockCameraUnmounted).toHaveBeenCalledTimes(1);
  await act(() => beforeSettings({ data: 'background-event' }));
  expect(onScan).not.toHaveBeenCalled();
  mockGetPermission.mockResolvedValue(denied);
  await changeAppState('active');
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);

  await changeAppState('background');
  mockGetPermission.mockResolvedValue(granted);
  await changeAppState('active');
  await act(() => beforeSettings({ data: 'retired-preview-event' }));
  expect(onScan).not.toHaveBeenCalled();
  await act(() => mockScan!({ data: 'new-preview-control' }));
  expect(onScan.mock.calls).toEqual([['new-preview-control']]);
});

it('ignores a late getter result after backgrounding and requires a fresh foreground read', async () => {
  const initial = deferredPermission();
  mockGetPermission.mockReturnValue(initial.promise);
  const view = await render(scanner(true));
  await changeAppState('background');
  await act(() => initial.resolve(granted));
  expect(mockCameraMounted).not.toHaveBeenCalled();
  mockGetPermission.mockResolvedValue(denied);
  await changeAppState('active');
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await view.rerender(scanner(false));
  mockRequestPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('does not let a pending grant override a later settings revocation', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  await changeAppState('background');
  mockGetPermission.mockResolvedValue({ ...denied, canAskAgain: false });
  await changeAppState('active');
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await act(() => request.resolve(granted));
  expect(view.getByText(/Please enable it in settings/)).toBeTruthy();
  expect(mockCameraMounted).not.toHaveBeenCalled();
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
});

it('catches a failed settings refresh without restoring the old preview', async () => {
  mockGetPermission.mockResolvedValue(granted);
  const view = await render(scanner(true));
  expect(mockCameraMounted).toHaveBeenCalledTimes(1);
  await changeAppState('background');
  mockGetPermission.mockRejectedValue(new Error('settings-getter-failure'));
  await changeAppState('active');
  expect(view.getByText(/Camera permission is unavailable/)).toBeTruthy();
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('shares a native request across scanner owners and never requests for a hidden owner', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(
    <>
      {scanner(true)}
      {scanner(true)}
      {scanner(false)}
    </>,
  );
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
  await act(() => request.resolve(denied));
  expect(view.getAllByText(/Please enable it in settings/)).toHaveLength(2);
  expect(mockCameraMounted).not.toHaveBeenCalled();
});

it('uses a request completed during another owner getter instead of prompting twice', async () => {
  const slowGetter = deferredPermission();
  mockGetPermission.mockResolvedValueOnce(undetermined).mockReturnValueOnce(slowGetter.promise);
  mockRequestPermission.mockResolvedValue(granted);
  const view = await render(
    <>
      {scanner(true)}
      {scanner(true)}
    </>,
  );
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  await act(() => slowGetter.resolve(undetermined));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getAllByTestId('camera-preview')).toHaveLength(2);
});

it('retires callbacks immediately on Cancel even before the owner hides the modal', async () => {
  mockGetPermission.mockResolvedValue(granted);
  const onScan = jest.fn();
  const onClose = jest.fn();
  const view = await render(scanner(true, onScan, onClose));
  const retained = mockScan!;
  await fireEvent.press(view.getByText('Cancel'));
  expect(onClose).toHaveBeenCalledTimes(1);
  await act(() => retained({ data: 'after-cancel' }));
  expect(onScan).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('does not read or prompt while inactive and only refreshes when becoming active', async () => {
  AppState.currentState = 'background';
  const view = await render(scanner(true));
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await changeAppState('active');
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await view.rerender(scanner(false));
  mockRequestPermission.mockResolvedValue(granted);
  await view.rerender(scanner(true));
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it.each(['close', 'background', 'unmount'] as const)(
  'does not continue a waiting foreground permission read after %s',
  async (retire) => {
    const request = deferredPermission();
    mockRequestPermission.mockReturnValue(request.promise);
    const view = await render(scanner(true));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
    expect(mockGetPermission).toHaveBeenCalledTimes(1);
    await changeAppState('background');
    await changeAppState('active');
    if (retire === 'close') await view.rerender(scanner(false));
    else if (retire === 'background') await changeAppState('background');
    else await view.unmount();

    await act(() => request.resolve(granted));
    expect(mockGetPermission).toHaveBeenCalledTimes(1);
    expect(mockCameraMounted).not.toHaveBeenCalled();
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  },
);
