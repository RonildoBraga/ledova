import React from 'react';
import { act, cleanup, render } from '@testing-library/react-native';
import { AppState } from 'react-native';
import type { PermissionResponse } from 'expo-camera';
import { UR, UREncoder, URDecoder } from '@ngraveio/bc-ur';

jest.mock('react-native', () => {
  const actual = jest.requireActual('react-native');
  actual.Platform.OS = 'android';
  return actual;
});

const mockGetPermission = jest.fn();
const mockRequestPermission = jest.fn();
const mockCurrentScan = jest.fn();

jest.mock('expo-camera/build/ExpoCameraManager', () => ({
  getCameraPermissionsAsync: () => mockGetPermission(),
  requestCameraPermissionsAsync: () => mockRequestPermission(),
}));
jest.mock('expo', () => ({
  ...jest.requireActual('expo'),
  requireOptionalNativeModule: () => ({}),
  requireNativeView: () => {
    const { View } = jest.requireActual('react-native');
    const { forwardRef, useImperativeHandle } = jest.requireActual('react');
    return forwardRef((props: object, ref: React.Ref<unknown>) => {
      useImperativeHandle(ref, () => ({ isCurrentScan: mockCurrentScan }));
      return <View testID="native-scanner" {...props} />;
    });
  },
}));
jest.mock('../modal', () => {
  const { View } = jest.requireActual('react-native');
  return { CustomModal: ({ children }: { children: React.ReactNode }) => <View>{children}</View> };
});

import { QRScanner } from './QRScanner';
import { AnimatedQRScanner } from './AnimatedQRScanner';
import { SignatureScanStep } from '../../screens/wallets/components/SignatureScanStep';
import { useCameraScanner } from './useCameraScanner';
import { CameraAccessContext, createCameraAccess } from '../../contexts/cameraAccess';

const granted: PermissionResponse = {
  status: 'granted' as PermissionResponse['status'],
  granted: true,
  canAskAgain: true,
  expires: 'never',
};
const undetermined = { ...granted, granted: false, status: 'undetermined' };
let access: ReturnType<typeof createCameraAccess>;

function SignatureScanner({ onScan }: { onScan: (data: string) => void }) {
  const camera = useCameraScanner(true, (data, finish) => {
    finish();
    onScan(data);
  });
  return (
    <SignatureScanStep
      cameraMessage={camera.message}
      preview={camera.preview}
      isVerifying={false}
      verificationSuccess={false}
      verificationError={null}
    />
  );
}

const placements = [
  {
    name: 'modal',
    element: (onScan: (data: string) => void) => <QRScanner visible onClose={jest.fn()} onScan={onScan} />,
  },
  { name: 'animated', element: (onScan: (data: string) => void) => <AnimatedQRScanner onComplete={onScan} /> },
  { name: 'signature', element: (onScan: (data: string) => void) => <SignatureScanner onScan={onScan} /> },
];

beforeEach(() => {
  mockGetPermission.mockReset().mockResolvedValue(granted);
  mockRequestPermission.mockReset().mockResolvedValue(granted);
  mockCurrentScan.mockReset().mockResolvedValue(true);
  AppState.currentState = 'active';
  access = createCameraAccess();
  access.setAllowed(true);
});

afterEach(async () => cleanup());

function wrapper({ children }: { children: React.ReactNode }) {
  return <CameraAccessContext.Provider value={access}>{children}</CameraAccessContext.Provider>;
}

type NativeScanner = ReturnType<Awaited<ReturnType<typeof render>>['getByTestId']>;

function windowEvent(scanner: NativeScanner, allowed: boolean, generation: number) {
  scanner.props.onWindowChanged({ nativeEvent: { allowed, generation } });
}

function barcode(scanner: NativeScanner, data: string, generation: number, scanId: number) {
  scanner.props.onBarcodeScanned({ nativeEvent: { data, generation, scanId } });
}

describe.each(placements)('$name scanner window', ({ element }) => {
  it('retains an inactive native observer and requests permission only after its own window is focused', async () => {
    mockGetPermission.mockResolvedValue(undetermined);
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    expect(mockGetPermission).not.toHaveBeenCalled();
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 0));
    expect(mockRequestPermission).not.toHaveBeenCalled();
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
    const scanner = view.getByTestId('native-scanner');
    expect(scanner.props.active).toBe(true);
    await act(() => barcode(scanner, 'synthetic-qr', 1, scanner.props.scanId));
    expect(onScan).toHaveBeenCalledWith('synthetic-qr');
  });

  it('retires callbacks synchronously on window loss and requires fresh admission without another prompt', async () => {
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    const scanner = view.getByTestId('native-scanner');
    const oldId = scanner.props.scanId;
    const stale = scanner.props.onBarcodeScanned;
    await act(() => {
      windowEvent(scanner, false, 2);
      stale({ nativeEvent: { data: 'late-qr', generation: 1, scanId: oldId } });
    });
    expect(AppState.currentState).toBe('active');
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    expect(onScan).not.toHaveBeenCalled();
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    const resumed = view.getByTestId('native-scanner');
    expect(resumed.props.active).toBe(true);
    expect(resumed.props.generation).toBe(3);
    expect(mockRequestPermission).not.toHaveBeenCalled();
    await act(() => {
      stale({ nativeEvent: { data: 'obsolete', generation: 1, scanId: oldId } });
      barcode(resumed, 'current-qr', 3, resumed.props.scanId);
    });
    expect(onScan.mock.calls).toEqual([['current-qr']]);
  });

  it('does not revive a completed scan after window loss and regain', async () => {
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    const scanner = view.getByTestId('native-scanner');
    const id = scanner.props.scanId;
    await act(() => barcode(scanner, 'completed-qr', 1, id));
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    await act(() => barcode(view.getByTestId('native-scanner'), 'duplicate', 1, id));
    expect(onScan.mock.calls).toEqual([['completed-qr']]);
  });

  it('refuses delayed permission results and late callbacks after unmount', async () => {
    let resolve!: (permission: PermissionResponse) => void;
    mockGetPermission.mockReturnValueOnce(
      new Promise((accept) => {
        resolve = accept;
      }),
    );
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
    await act(() => resolve(granted));
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    const scanner = view.getByTestId('native-scanner');
    const stale = scanner.props.onBarcodeScanned;
    const id = scanner.props.scanId;
    expect(scanner.props.active).toBe(true);
    await view.unmount();
    await act(() => stale({ nativeEvent: { data: 'retired', generation: 3, scanId: id } }));
    expect(onScan).not.toHaveBeenCalled();
  });

  it('keeps lock admission in force when the owning window regains focus', async () => {
    const view = await render(element(jest.fn()), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    expect(view.getByTestId('native-scanner').props.active).toBe(true);
    await act(() => access.setAllowed(false));
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    await act(() => access.setAllowed(true));
    expect(view.getByTestId('native-scanner').props.active).toBe(true);
    expect(mockRequestPermission).not.toHaveBeenCalled();
  });

  it('ignores reordered window events and mount failures from an earlier admission', async () => {
    const view = await render(element(jest.fn()), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    const oldId = view.getByTestId('native-scanner').props.scanId;
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    await act(() => {
      windowEvent(view.getByTestId('native-scanner'), false, 2);
      view.getByTestId('native-scanner').props.onMountError({ nativeEvent: { generation: 1, scanId: oldId } });
    });
    const current = view.getByTestId('native-scanner');
    expect(current.props.active).toBe(true);
    await act(() => current.props.onMountError({ nativeEvent: { generation: 3, scanId: current.props.scanId } }));
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
  });

  it('does not request again when a native permission dialog temporarily takes focus', async () => {
    let resolve!: (permission: PermissionResponse) => void;
    mockGetPermission.mockResolvedValue(undetermined);
    mockRequestPermission.mockReturnValueOnce(
      new Promise((accept) => {
        resolve = accept;
      }),
    );
    const view = await render(element(jest.fn()), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
    await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
    await act(() => resolve(granted));
    expect(view.getByTestId('native-scanner').props.active).toBe(false);
    mockGetPermission.mockResolvedValue(granted);
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
    expect(view.getByTestId('native-scanner').props.active).toBe(true);
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  });

  it('refuses a queued barcode when native focus was lost before JavaScript receives the window event', async () => {
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    const scanner = view.getByTestId('native-scanner');
    mockCurrentScan.mockResolvedValue(false);
    await act(() => barcode(scanner, 'queued-before-window-event', 1, scanner.props.scanId));
    expect(onScan).not.toHaveBeenCalled();
    mockCurrentScan.mockResolvedValue(true);
    await act(() => barcode(scanner, 'current-control', 1, scanner.props.scanId));
    expect(onScan.mock.calls).toEqual([['current-control']]);
  });

  it('retires a delayed native admission response after a JavaScript lock pause', async () => {
    let resolve!: (admitted: boolean) => void;
    const onScan = jest.fn();
    const view = await render(element(onScan), { wrapper });
    await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
    const scanner = view.getByTestId('native-scanner');
    mockCurrentScan.mockReturnValueOnce(
      new Promise((accept) => {
        resolve = accept;
      }),
    );
    await act(() => barcode(scanner, 'delayed-admission', 1, scanner.props.scanId));
    await act(() => access.setAllowed(false));
    await act(() => resolve(true));
    expect(onScan).not.toHaveBeenCalled();
    await act(() => access.setAllowed(true));
    const resumed = view.getByTestId('native-scanner');
    await act(() => barcode(resumed, 'current-control', 1, resumed.props.scanId));
    expect(onScan.mock.calls).toEqual([['current-control']]);
  });
});

it('preserves partial animated UR decoding across window loss and finishes exactly once', async () => {
  const payload = Buffer.from('synthetic-wallet-data-'.repeat(15));
  const encoder = new UREncoder(UR.fromBuffer(payload), 40);
  const parts = Array.from({ length: encoder.fragmentsLength }, () => encoder.nextPart());
  expect(parts.length).toBeGreaterThan(2);
  const onComplete = jest.fn();
  const view = await render(<AnimatedQRScanner onComplete={onComplete} />, { wrapper });
  await act(() => windowEvent(view.getByTestId('native-scanner'), true, 1));
  const original = view.getByTestId('native-scanner');
  await act(() => barcode(original, parts[0], 1, original.props.scanId));
  expect(onComplete).not.toHaveBeenCalled();
  await act(() => windowEvent(view.getByTestId('native-scanner'), false, 2));
  await act(() => windowEvent(view.getByTestId('native-scanner'), true, 3));
  const resumed = view.getByTestId('native-scanner');
  const id = resumed.props.scanId;
  await act(() => parts.slice(1).forEach((data) => barcode(resumed, data, 3, id)));
  expect(onComplete).toHaveBeenCalledTimes(1);
  const decoded = new URDecoder();
  decoded.receivePart(onComplete.mock.calls[0][0]);
  expect(decoded.resultUR().decodeCBOR()).toEqual(payload);
  await act(() => parts.forEach((data) => barcode(view.getByTestId('native-scanner'), data, 3, id)));
  expect(onComplete).toHaveBeenCalledTimes(1);
});
