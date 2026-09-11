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

it('the live native admission calls the real finish callback once and stays complete while mounted', async () => {
  const onComplete = jest.fn();
  const view = await render(<ScannerBridgeProbe onComplete={onComplete} />);
  const scanner = () => view.getAllByTestId('native-scanner').find((item) => item.props.onWindowChanged)!;
  const inactive = view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  await act(() => inactive.props.onLayout());
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
  const inactive = view.getAllByTestId('native-scanner').find((item) => !item.props.onWindowChanged)!;
  await act(() => inactive.props.onLayout());
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
  await fireEvent.press(view.getByLabelText('scanner-probe-complete'));
  expect(onComplete.mock.calls).toEqual([[true]]);
});
