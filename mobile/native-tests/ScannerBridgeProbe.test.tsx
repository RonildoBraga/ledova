import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react-native';
import { AppState } from 'react-native';

const mockCurrentScan = jest.fn();

jest.mock('react-native', () => {
  const actual = jest.requireActual('react-native');
  actual.Platform.OS = 'android';
  return actual;
});
jest.mock('expo-camera/build/ExpoCameraManager', () => ({
  getCameraPermissionsAsync: async () => ({ granted: true, canAskAgain: true, status: 'granted', expires: 'never' }),
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

import { ScannerBridgeProbe } from './ScannerBridgeProbe';

beforeEach(() => {
  AppState.currentState = 'active';
  mockCurrentScan.mockReset().mockImplementation(async (generation: number) => generation >= 0);
});
afterEach(async () => cleanup());

it('acknowledges removal of an active scanner before remounting without accepting its pending barcode', async () => {
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  const scanner = () => view.getAllByTestId('native-scanner').find((item) => item.props.onWindowChanged)!;
  const inactive = () => view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  expect(view.queryByLabelText('scanner-probe-unmount-active')).toBeNull();
  await act(() => inactive().props.onLayout());
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
  const first = scanner();
  expect(first.props.active).toBe(true);
  expect(view.getByLabelText('scanner-probe-state').props.children).toBe(`ready|1|${first.props.scanId}|0`);
  let resolveAdmission!: (value: boolean) => void;
  mockCurrentScan.mockReturnValueOnce(new Promise<boolean>((resolve) => (resolveAdmission = resolve)));
  const pending = first.props.onBarcodeScanned({
    nativeEvent: { data: 'synthetic-pending-proof', generation: 1, scanId: first.props.scanId },
  });
  try {
    await fireEvent.press(view.getByLabelText('scanner-probe-unmount-active'));
    expect(view.getByLabelText('scanner-probe-active-unmounted')).toBeTruthy();
    expect(view.queryAllByTestId('native-scanner')).toEqual([]);
    expect(view.queryByLabelText('scanner-probe-state')).toBeNull();
    expect(onComplete).not.toHaveBeenCalled();
    await fireEvent.press(view.getByLabelText('scanner-probe-remount'));
    expect(view.queryByLabelText('scanner-probe-active-unmounted')).toBeNull();
    await act(() => inactive().props.onLayout());
    await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
    const fresh = scanner();
    expect(fresh.props.active).toBe(true);
    expect(fresh.props.scanId).not.toBe(first.props.scanId);
    await act(async () => {
      resolveAdmission(true);
      await pending;
    });
    expect(view.getByLabelText('scanner-probe-state').props.children).toBe(`ready|1|${fresh.props.scanId}|0`);
    expect(onComplete).not.toHaveBeenCalled();
  } finally {
    await act(async () => {
      resolveAdmission(true);
      await pending;
    });
  }
});

it('the live native admission calls the real finish callback once and stays complete while mounted', async () => {
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  const scanner = () => view.getAllByTestId('native-scanner').find((item) => item.props.onWindowChanged)!;
  const inactive = () => view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  await act(() => inactive().props.onLayout());
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
  await fireEvent.press(view.getByLabelText('scanner-probe-unmount-active'));
  await fireEvent.press(view.getByLabelText('scanner-probe-remount'));
  await act(() => inactive().props.onLayout());
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
  const first = scanner();
  await act(() =>
    first.props.onBarcodeScanned({
      nativeEvent: { data: 'synthetic-live-proof', generation: 1, scanId: first.props.scanId },
    }),
  );
  expect(view.getByText('scanned')).toBeTruthy();
  expect(onComplete).not.toHaveBeenCalled();
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: false, generation: 2 } }));
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 3 } }));
  expect(view.getByText('scanned')).toBeTruthy();
  expect(scanner().props.active).toBe(false);
  await act(() =>
    first.props.onBarcodeScanned({ nativeEvent: { data: 'late-proof', generation: 1, scanId: first.props.scanId } }),
  );
  expect(view.getByLabelText('scanner-probe-state').props.children).toBe('scanned|-1|0|1');
  expect(onComplete).not.toHaveBeenCalled();
});

it('the same unchanged bridge refuses the queued tuple and admits a fresh tuple before probe completion', async () => {
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  const scanner = () => view.getAllByTestId('native-scanner').find((item) => item.props.onWindowChanged)!;
  const inactive = () => view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  await act(() => inactive().props.onLayout());
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
  await fireEvent.press(view.getByLabelText('scanner-probe-unmount-active'));
  await fireEvent.press(view.getByLabelText('scanner-probe-remount'));
  await act(() => inactive().props.onLayout());
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
  const old = scanner();
  await fireEvent.press(view.getByLabelText('scanner-probe-cover'));
  mockCurrentScan.mockResolvedValueOnce(false);
  await act(() =>
    old.props.onBarcodeScanned({
      nativeEvent: { data: 'synthetic-queued-proof', generation: 1, scanId: old.props.scanId },
    }),
  );
  expect(view.getByText('ready')).toBeTruthy();
  expect(view.getByLabelText('scanner-probe-state').props.children).toBe(`ready|1|${old.props.scanId}|0`);
  await fireEvent.press(view.getByLabelText('scanner-probe-return'));
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: false, generation: 2 } }));
  await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 3 } }));
  const fresh = scanner();
  await act(() =>
    fresh.props.onBarcodeScanned({
      nativeEvent: { data: 'synthetic-live-proof', generation: 3, scanId: fresh.props.scanId },
    }),
  );
  expect(view.getByText('scanned')).toBeTruthy();
  expect(view.queryByLabelText('scanner-probe-completed-unmounted')).toBeNull();
  await fireEvent.press(view.getByLabelText('scanner-probe-complete'));
  expect(view.getByLabelText('scanner-probe-completed-unmounted')).toBeTruthy();
  expect(view.queryAllByTestId('native-scanner')).toEqual([]);
  expect(view.queryByLabelText('scanner-probe-state')).toBeNull();
  expect(onComplete).not.toHaveBeenCalled();
  await fireEvent.press(view.getByLabelText('scanner-probe-report'));
  expect(onComplete.mock.calls).toEqual([[true]]);
});

it('a failed native readiness check retains its failure without a successful unmount checkpoint', async () => {
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  const inactive = view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  mockCurrentScan.mockResolvedValueOnce(true);
  await act(() => inactive.props.onLayout());
  expect(onComplete.mock.calls).toEqual([[false, 'inactive-admitted']]);
  expect(view.queryByLabelText('scanner-probe-active-unmounted')).toBeNull();
  expect(view.queryByLabelText('scanner-probe-completed-unmounted')).toBeNull();
  expect(view.queryByLabelText('scanner-probe-report')).toBeNull();
});

it('keeps the initial active scanner bounded by its original one-minute deadline', async () => {
  jest.useFakeTimers();
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  try {
    await act(() => jest.advanceTimersByTime(59_999));
    expect(onComplete).not.toHaveBeenCalled();
    await act(() => jest.advanceTimersByTime(1));
    expect(onComplete.mock.calls).toEqual([[false, 'window-timeout']]);
  } finally {
    await view.unmount();
    jest.useRealTimers();
  }
});

it('allows the expanded continuation past one minute but still refuses a stalled sequence', async () => {
  jest.useFakeTimers();
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  try {
    const scanner = () => view.getAllByTestId('native-scanner').find((item) => item.props.onWindowChanged)!;
    const inactive = () => view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
    await act(() => inactive().props.onLayout());
    await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
    await act(() => jest.advanceTimersByTime(30_000));
    await fireEvent.press(view.getByLabelText('scanner-probe-unmount-active'));
    await fireEvent.press(view.getByLabelText('scanner-probe-remount'));
    await act(() => inactive().props.onLayout());
    await act(() => scanner().props.onWindowChanged({ nativeEvent: { allowed: true, generation: 1 } }));
    await act(() => jest.advanceTimersByTime(90_000));
    expect(onComplete).not.toHaveBeenCalled();
    expect(scanner().props.active).toBe(true);
    await act(() => jest.advanceTimersByTime(269_999));
    expect(onComplete).not.toHaveBeenCalled();
    await act(() => jest.advanceTimersByTime(1));
    expect(onComplete.mock.calls).toEqual([[false, 'window-timeout']]);
  } finally {
    await view.unmount();
    jest.useRealTimers();
  }
});
