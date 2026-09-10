import React from 'react';
import { act, render } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import type { PermissionResponse } from 'expo-camera';
import { UR, UREncoder, URDecoder } from '@ngraveio/bc-ur';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
let mockScan: ((result: { data: string }) => void) | undefined;
const listeners = new Set<(state: AppStateStatus) => void>();

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

import { AnimatedQRScanner } from './AnimatedQRScanner';

const granted: PermissionResponse = {
  status: 'granted' as PermissionResponse['status'],
  granted: true,
  canAskAgain: true,
  expires: 'never',
};
const undetermined: PermissionResponse = {
  ...granted,
  granted: false,
  status: 'undetermined' as PermissionResponse['status'],
};

beforeEach(() => {
  mockGetPermission.mockReset().mockResolvedValue(granted);
  mockRequestPermission.mockReset().mockResolvedValue(granted);
  mockScan = undefined;
  AppState.currentState = 'active';
  listeners.clear();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') listeners.add(listener);
    return { remove: () => listeners.delete(listener) };
  });
});

async function changeAppState(state: AppStateStatus) {
  await act(() => {
    AppState.currentState = state;
    listeners.forEach((listener) => listener(state));
  });
}

it('completes an ordinary QR once and retires the preview', async () => {
  const onComplete = jest.fn();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  const retained = mockScan!;
  await act(() => {
    retained({ data: 'synthetic-wallet-address' });
    retained({ data: 'duplicate-frame' });
  });
  expect(onComplete.mock.calls).toEqual([['synthetic-wallet-address']]);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await changeAppState('background');
  await changeAppState('active');
  await act(() => retained({ data: 'after-completion' }));
  expect(onComplete).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('reassembles real animated UR fragments across a permission refresh and completes once', async () => {
  const payload = Buffer.from('synthetic-wallet-import-control-'.repeat(8));
  const ur = UR.fromBuffer(payload);
  const encoder = new UREncoder(ur, 40);
  const parts = Array.from({ length: encoder.fragmentsLength }, () => encoder.nextPart());
  expect(parts.length).toBeGreaterThan(2);
  const onComplete = jest.fn();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />);
  const firstPreview = mockScan!;
  await act(() => {
    firstPreview({ data: parts[0].toUpperCase() });
    firstPreview({ data: parts[0] });
  });
  expect(view.getByText(/^Scanning: 1\//)).toBeTruthy();
  expect(onComplete).not.toHaveBeenCalled();

  await changeAppState('background');
  await act(() => firstPreview({ data: parts[1] }));
  expect(onComplete).not.toHaveBeenCalled();
  expect(view.queryByTestId('camera-preview')).toBeNull();
  await changeAppState('active');
  const currentPreview = mockScan!;
  await act(() => parts.slice(1).forEach((data) => currentPreview({ data })));
  expect(onComplete).toHaveBeenCalledTimes(1);
  await act(() => parts.forEach((data) => currentPreview({ data })));
  expect(onComplete).toHaveBeenCalledTimes(1);
  const decoded = new URDecoder();
  expect(decoded.receivePart(onComplete.mock.calls[0][0])).toBe(true);
  expect(decoded.isComplete()).toBe(true);
  expect(decoded.resultUR().decodeCBOR()).toEqual(payload);
  expect(view.queryByTestId('camera-preview')).toBeNull();
  expect(mockRequestPermission).not.toHaveBeenCalled();
});

it('ignores events after unmount and after hiding without consuming a new opening', async () => {
  const onComplete = jest.fn();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />);
  const earlier = mockScan!;
  await view.rerender(<AnimatedQRScanner active={false} onComplete={onComplete} />);
  await act(() => earlier({ data: 'hidden-event' }));
  expect(onComplete).not.toHaveBeenCalled();
  await view.rerender(<AnimatedQRScanner active onComplete={onComplete} />);
  await act(() => earlier({ data: 'old-opening-event' }));
  expect(onComplete).not.toHaveBeenCalled();
  await act(() => mockScan!({ data: 'current-opening-control' }));
  expect(onComplete.mock.calls).toEqual([['current-opening-control']]);

  await view.unmount();
  const next = await render(<AnimatedQRScanner onComplete={onComplete} />);
  const unmounted = mockScan!;
  await next.unmount();
  await act(() => unmounted({ data: 'unmounted-event' }));
  expect(onComplete).toHaveBeenCalledTimes(1);
});

it('does not open an inactive importer and requests an undetermined permission when shown', async () => {
  mockGetPermission.mockResolvedValue(undetermined);
  const view = await render(<AnimatedQRScanner active={false} onComplete={jest.fn()} />);
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await view.rerender(<AnimatedQRScanner active onComplete={jest.fn()} />);
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(view.getByTestId('camera-preview')).toBeTruthy();
});

it.each(['get', 'request'] as const)('handles a native %s rejection without retrying', async (operation) => {
  mockGetPermission.mockResolvedValue(undetermined);
  const failing = operation === 'get' ? mockGetPermission : mockRequestPermission;
  failing.mockRejectedValue(new Error('synthetic-native-failure'));
  const view = await render(<AnimatedQRScanner onComplete={jest.fn()} />);
  expect(view.getByText(/Camera permission is unavailable/)).toBeTruthy();
  expect(failing).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
});

it('continues after malformed UR input and accepts a valid single part', async () => {
  const onComplete = jest.fn();
  const expected = new UREncoder(UR.fromBuffer(Buffer.from('synthetic-control'))).nextPart();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />);
  await act(() => mockScan!({ data: 'ur:malformed' }));
  expect(onComplete).not.toHaveBeenCalled();
  expect(view.getByTestId('camera-preview')).toBeTruthy();
  await act(() => mockScan!({ data: expected }));
  expect(onComplete.mock.calls).toEqual([[expected]]);
});

it('retires a completed UR even if its consumer throws', async () => {
  const onComplete = jest.fn(() => {
    throw new Error('synthetic-consumer-failure');
  });
  const expected = new UREncoder(UR.fromBuffer(Buffer.from('synthetic-control'))).nextPart();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />);
  const retained = mockScan!;
  await act(() => {
    retained({ data: expected });
    retained({ data: expected });
  });
  expect(onComplete).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('camera-preview')).toBeNull();
});
