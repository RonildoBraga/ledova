import React from 'react';
import { act, fireEvent, render, within } from '@testing-library/react-native';
import { AppState, Platform, View } from 'react-native';
import type { PermissionResponse } from 'expo-camera';
import { UR, UREncoder, URDecoder } from '@ngraveio/bc-ur';

const mockGetPermission = jest.fn<Promise<PermissionResponse>, []>();
const mockRequestPermission = jest.fn<Promise<PermissionResponse>, []>();
let mockScan: ((result: { data: string }) => void) | undefined;

jest.mock('expo-camera', () => {
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    Camera: {
      getCameraPermissionsAsync: () => mockGetPermission(),
      requestCameraPermissionsAsync: () => mockRequestPermission(),
    },
    CameraView: ({ onBarcodeScanned }: { onBarcodeScanned?: typeof mockScan }) => {
      const { useId } = jest.requireActual<typeof import('react')>('react');
      const instance = useId();
      mockScan = onBarcodeScanned;
      return <View testID="camera-preview" accessibilityLabel={instance} />;
    },
  };
});
jest.mock('expo', () => {
  const actual = jest.requireActual<typeof import('expo')>('expo');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    ...actual,
    requireNativeView: () => View,
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
import { AnimatedQRScanner } from './AnimatedQRScanner';
import { CameraAccessContext, createCameraAccess } from '../../contexts/cameraAccess';

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

beforeEach(() => {
  jest.replaceProperty(Platform, 'OS', 'android');
  AppState.currentState = 'active';
  mockGetPermission.mockReset().mockResolvedValue(granted);
  mockRequestPermission.mockReset().mockResolvedValue(granted);
  mockScan = undefined;
});

async function open(onScan = jest.fn(), visible = true) {
  const access = createCameraAccess();
  access.setAllowed(true);
  const screen = await render(<QRScanner visible={visible} onClose={jest.fn()} onScan={onScan} />, {
    wrapper: ({ children }) => <CameraAccessContext.Provider value={access}>{children}</CameraAccessContext.Provider>,
  });
  return { screen, access };
}

async function focus(screen: Awaited<ReturnType<typeof open>>['screen'], generation: number, allowed: boolean) {
  const owner = screen.getByTestId('camera-window');
  await fireEvent(owner, 'windowChange', { nativeEvent: { ownerId: owner.props.ownerId, generation, allowed } });
}

it('waits for the owning window before any initial Android permission read or preview', async () => {
  const { screen } = await open();
  expect(mockGetPermission).not.toHaveBeenCalled();
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  await focus(screen, 1, true);
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('camera-preview')).toBeTruthy();
});

it('retains one explicit request until first admission and does not repeat it after permission-dialog focus loss', async () => {
  let resolve!: (permission: PermissionResponse) => void;
  mockGetPermission.mockResolvedValue(undetermined);
  mockRequestPermission.mockReturnValue(
    new Promise((accept) => {
      resolve = accept;
    }),
  );
  const { screen } = await open();
  expect(mockRequestPermission).not.toHaveBeenCalled();
  await focus(screen, 1, true);
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  await focus(screen, 2, false);
  await act(() => resolve(granted));
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  mockGetPermission.mockResolvedValue(granted);
  await focus(screen, 3, true);
  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('camera-preview')).toBeTruthy();
});

it('unmounts on focus loss while active and refuses old callbacks, generations and foreign owners', async () => {
  const onScan = jest.fn();
  const { screen } = await open(onScan);
  await focus(screen, 1, true);
  const retained = mockScan!;
  const owner = screen.getByTestId('camera-window');
  await focus(screen, 3, false);
  expect(AppState.currentState).toBe('active');
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  await act(() => retained({ data: 'retired-window' }));
  await fireEvent(owner, 'windowChange', {
    nativeEvent: { ownerId: owner.props.ownerId, generation: 2, allowed: true },
  });
  await fireEvent(owner, 'windowChange', { nativeEvent: { ownerId: 'another-window', generation: 99, allowed: true } });
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  expect(onScan).not.toHaveBeenCalled();
  await focus(screen, 4, true);
  expect(screen.getByTestId('camera-preview')).toBeTruthy();
  await act(() => mockScan!({ data: 'current-window' }));
  expect(onScan.mock.calls).toEqual([['current-window']]);
  await focus(screen, 5, false);
  await focus(screen, 6, true);
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  expect(mockRequestPermission).not.toHaveBeenCalled();
});

it('invalidates a pending read on loss and does not request permission when it resolves', async () => {
  let resolve!: (permission: PermissionResponse) => void;
  mockGetPermission.mockReturnValue(
    new Promise((accept) => {
      resolve = accept;
    }),
  );
  const { screen } = await open();
  await focus(screen, 1, true);
  await focus(screen, 2, false);
  await act(() => resolve(undetermined));
  expect(mockRequestPermission).not.toHaveBeenCalled();
  mockGetPermission.mockResolvedValue(undetermined);
  await focus(screen, 3, true);
  expect(mockRequestPermission).not.toHaveBeenCalled();
  expect(screen.getByText(/Please enable it in settings/)).toBeTruthy();
});

it('keeps independent owners separate and preserves app-lock denial on later focus', async () => {
  const accesses = [createCameraAccess(), createCameraAccess()];
  accesses.forEach((access) => access.setAllowed(true));
  const screen = await render(
    <>
      {accesses.map((access, index) => (
        <View key={index} testID={`scanner-${index}`}>
          <CameraAccessContext.Provider value={access}>
            <QRScanner visible onClose={jest.fn()} onScan={jest.fn()} />
          </CameraAccessContext.Provider>
        </View>
      ))}
    </>,
  );
  const first = within(screen.getByTestId('scanner-0'));
  const second = within(screen.getByTestId('scanner-1'));
  const emit = async (index: number, generation: number, allowed: boolean) => {
    const owner = screen.getAllByTestId('camera-window')[index];
    await fireEvent(owner, 'windowChange', { nativeEvent: { ownerId: owner.props.ownerId, generation, allowed } });
  };
  await emit(0, 1, true);
  expect(first.getByTestId('camera-preview')).toBeTruthy();
  expect(second.queryByTestId('camera-preview')).toBeNull();
  await emit(1, 1, true);
  await emit(0, 2, false);
  expect(second.getByTestId('camera-preview')).toBeTruthy();
  await act(() => accesses[1].setAllowed(false));
  await emit(1, 2, false);
  await emit(1, 3, true);
  expect(second.queryByTestId('camera-preview')).toBeNull();
  await act(() => accesses[1].setAllowed(true));
  expect(second.getByTestId('camera-preview')).toBeTruthy();
});

it('mounts a fresh preview after loss and regain arrive in one JS batch', async () => {
  const { screen } = await open();
  await focus(screen, 1, true);
  const first = screen.getByTestId('camera-preview').props.accessibilityLabel;
  const owner = screen.getByTestId('camera-window');
  await act(() => {
    owner.props.onWindowChange({ nativeEvent: { ownerId: owner.props.ownerId, generation: 2, allowed: false } });
    owner.props.onWindowChange({ nativeEvent: { ownerId: owner.props.ownerId, generation: 3, allowed: true } });
  });
  expect(screen.getByTestId('camera-preview').props.accessibilityLabel).not.toBe(first);
  expect(mockRequestPermission).not.toHaveBeenCalled();
});

it('keeps the iOS scanner behavior independent of the Android bridge', async () => {
  jest.replaceProperty(Platform, 'OS', 'ios');
  const { screen } = await open();
  expect(mockGetPermission).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('camera-preview')).toBeTruthy();
  expect(screen.queryByTestId('camera-window')).toBeNull();
});

it('keeps real animated UR progress and completion across owning-window loss', async () => {
  const access = createCameraAccess();
  access.setAllowed(true);
  const complete = jest.fn();
  const screen = await render(
    <CameraAccessContext.Provider value={access}>
      <AnimatedQRScanner onComplete={complete} />
    </CameraAccessContext.Provider>,
  );
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  expect(mockGetPermission).not.toHaveBeenCalled();
  await focus(screen, 1, true);
  const payload = Buffer.from('synthetic-camera-window-'.repeat(8));
  const encoder = new UREncoder(UR.fromBuffer(payload), 40);
  const parts = Array.from({ length: encoder.fragmentsLength }, () => encoder.nextPart());
  expect(parts.length).toBeGreaterThan(2);
  const previous = mockScan!;
  await act(() => previous({ data: parts[0] }));
  expect(screen.getByText(/^Scanning: 1\//)).toBeTruthy();
  await focus(screen, 2, false);
  await act(() => previous({ data: parts[1] }));
  expect(complete).not.toHaveBeenCalled();
  await focus(screen, 3, true);
  expect(screen.getByText(/^Scanning: 1\//)).toBeTruthy();
  await act(() => parts.slice(1).forEach((data) => mockScan!({ data })));
  expect(complete).toHaveBeenCalledTimes(1);
  const decoder = new URDecoder();
  decoder.receivePart(complete.mock.calls[0][0]);
  expect(decoder.resultUR().decodeCBOR()).toEqual(payload);
  await focus(screen, 4, false);
  await focus(screen, 5, true);
  expect(screen.queryByTestId('camera-preview')).toBeNull();
  expect(complete).toHaveBeenCalledTimes(1);
});
