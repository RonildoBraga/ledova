import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import type { PermissionResponse } from 'expo-camera';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockCameraMounted = jest.fn();
const mockCameraUnmounted = jest.fn();
let mockScan: ((result: { data: string }) => void) | undefined;

jest.mock('expo-camera', () => {
  const { createPermissionHook } = jest.requireActual<typeof import('expo-modules-core')>('expo-modules-core');
  const { useEffect } = jest.requireActual<typeof import('react')>('react');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    useCameraPermissions: createPermissionHook({
      getMethod: () => mockGetPermission(),
      requestMethod: () => mockRequestPermission(),
    }),
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
  mockRequestPermission.mockReset().mockImplementation(() => new Promise(() => {}));
  mockScan = undefined;
});

it('keeps hidden scanners idle before and after the permission getter resolves', async () => {
  const initial = deferredPermission();
  mockGetPermission.mockReturnValue(initial.promise);
  const view = await render(
    <>
      {scanner(false)}
      {scanner(false)}
    </>,
  );
  expect(mockGetPermission).toHaveBeenCalledTimes(2);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(mockCameraMounted).not.toHaveBeenCalled();

  await act(() => initial.resolve(undetermined));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('requests once when opened after an undetermined permission has already loaded', async () => {
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

  await view.rerender(scanner(true));
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it('handles a rejected permission request without a retry loop', async () => {
  const request = deferredPermission();
  mockRequestPermission.mockReturnValue(request.promise);
  const view = await render(scanner(true));
  await act(() => request.reject(new Error('native-permission-failure')));
  expect(view.getByText('Unable to request camera permission. Close the scanner and try again.')).toBeTruthy();
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
