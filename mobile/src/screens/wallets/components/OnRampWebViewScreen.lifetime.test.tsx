import React from 'react';
import { act, cleanup, render } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import type { NativeProps } from 'react-native-webview/lib/RNCWebViewNativeComponent';
import type { WebViewMessageEvent } from 'react-native-webview';
import { CameraAccessContext, createCameraAccess } from '../../../contexts/cameraAccess';
import { getSessionEpoch, invalidateSessionScope } from '../../../services/sessionScope';

const mockViews = new Map<number, NativeProps>();
const mockGoBack = jest.fn();
const mockInvalidate = jest.fn();
const mockLoadDecision = jest.fn();
const mockBlur = new Set<() => void>();
let mockFocused = true;
let mockViewId = 0;
let mockParams = { url: 'https://provider.example.test/form', sessionEpoch: 0 };
const listeners = new Set<(state: AppStateStatus) => void>();
const mockNavigation = {
  canGoBack: () => true,
  goBack: mockGoBack,
  isFocused: () => mockFocused,
  addListener: (event: string, listener: () => void) => {
    if (event === 'blur') mockBlur.add(listener);
    return () => mockBlur.delete(listener);
  },
};

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: mockParams }),
  useNavigation: () => mockNavigation,
  useIsFocused: () => mockFocused,
}));
jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: mockInvalidate }) }));
jest.mock('../../../contexts', () => ({
  useAppTheme: () => ({ colors: { interactive: { active: '#fff' } } }),
  useThemedStyles: () => ({}),
}));
jest.mock('../../../components/GradientBackground', () => ({
  GradientBackground: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('react-native-webview', () => jest.requireActual('react-native-webview/src/WebView.ios'));
jest.mock('react-native-webview/src/NativeRNCWebViewModule', () => ({
  __esModule: true,
  default: { shouldStartLoadWithLockIdentifier: (...args: unknown[]) => mockLoadDecision(...args) },
}));
jest.mock('react-native-webview/src/RNCWebViewNativeComponent', () => {
  const { useLayoutEffect, useState } = jest.requireActual<typeof import('react')>('react');
  const { View } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    __esModule: true,
    Commands: {},
    default: function MockNativeWebView(props: NativeProps) {
      const [id] = useState(() => ++mockViewId);
      useLayoutEffect(() => {
        mockViews.set(id, props);
      });
      useLayoutEffect(
        () => () => {
          mockViews.delete(id);
        },
        [id],
      );
      return <View testID="onramp-native-view" />;
    },
  };
});

import { OnRampWebViewScreen } from './OnRampWebViewScreen';

let access = createCameraAccess();

function screen() {
  return (
    <CameraAccessContext.Provider value={access}>
      <OnRampWebViewScreen />
    </CameraAccessContext.Provider>
  );
}

function nativeView() {
  expect(mockViews.size).toBe(1);
  return [...mockViews.values()][0];
}

function message(view: NativeProps, eventId = 'TRANSAK_ORDER_SUCCESSFUL') {
  return view.onMessage?.({ nativeEvent: { data: JSON.stringify({ event_id: eventId }) } } as WebViewMessageEvent);
}

async function appState(state: AppStateStatus) {
  await act(() => {
    AppState.currentState = state;
    [...listeners].forEach((listener) => listener(state));
  });
}

beforeEach(() => {
  access = createCameraAccess();
  access.setAllowed(true);
  AppState.currentState = 'active';
  mockFocused = true;
  mockParams = { url: 'https://provider.example.test/form', sessionEpoch: getSessionEpoch() };
  listeners.clear();
  mockBlur.clear();
  mockViews.clear();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') listeners.add(listener);
    return { remove: () => listeners.delete(listener) };
  });
});

afterEach(async () => {
  await cleanup();
  expect(mockViews.size).toBe(0);
});

it('delivers one current completion and removes its native view', async () => {
  await render(screen());
  const current = nativeView();
  await act(async () => {
    await message(current);
    await message(current);
  });
  expect(mockGoBack).toHaveBeenCalledTimes(1);
  expect(mockInvalidate).toHaveBeenCalled();
  expect(mockViews.size).toBe(0);
});

it('withholds the native view until app-lock admission succeeds', async () => {
  access.setAllowed(false);
  await render(screen());
  expect(mockViews.size).toBe(0);
  await act(() => access.setAllowed(true));
  expect(nativeView().newSource).toEqual(expect.objectContaining({ uri: mockParams.url }));
});

it('removes the locked provider and refuses its callbacks after unlock', async () => {
  await render(screen());
  const old = nativeView();
  await act(() => access.setAllowed(false));
  expect(mockViews.size).toBe(0);
  await act(() => access.setAllowed(true));
  const current = nativeView();
  await act(() => message(old));
  expect(mockGoBack).not.toHaveBeenCalled();
  expect(mockInvalidate).not.toHaveBeenCalled();
  await act(() => message(current));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('fences an old callback during a quick lock and unlock before rendering', async () => {
  await render(screen());
  const old = nativeView();
  await act(async () => {
    access.setAllowed(false);
    access.setAllowed(true);
    await message(old);
  });
  expect(mockGoBack).not.toHaveBeenCalled();
  await act(() => message(nativeView()));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('removes a background provider and only accepts the new foreground view', async () => {
  await render(screen());
  const old = nativeView();
  await appState('background');
  expect(mockViews.size).toBe(0);
  await appState('active');
  await act(() => message(old));
  expect(mockGoBack).not.toHaveBeenCalled();
  await act(() => message(nativeView()));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('does not reopen an old session URL after the session changes', async () => {
  const view = await render(screen());
  const old = nativeView();
  await act(() => invalidateSessionScope());
  expect(mockViews.size).toBe(0);
  await act(() => message(old));
  expect(mockGoBack).not.toHaveBeenCalled();
  await view.rerender(screen());
  expect(mockViews.size).toBe(0);
  mockParams = { ...mockParams, sessionEpoch: getSessionEpoch() };
  await view.rerender(screen());
  await act(() => message(nativeView()));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('removes the provider on navigation blur and rejects pre-blur callbacks', async () => {
  const view = await render(screen());
  const old = nativeView();
  await act(async () => {
    mockFocused = false;
    [...mockBlur].forEach((listener) => listener());
    await message(old);
  });
  await view.rerender(screen());
  expect(mockViews.size).toBe(0);
  mockFocused = true;
  await view.rerender(screen());
  await act(() => message(old));
  expect(mockGoBack).not.toHaveBeenCalled();
  await act(() => message(nativeView()));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('does not reuse a view after a quick navigation blur and return', async () => {
  await render(screen());
  const old = nativeView();
  await act(async () => {
    mockFocused = false;
    [...mockBlur].forEach((listener) => listener());
    mockFocused = true;
    await message(old);
  });
  expect(mockGoBack).not.toHaveBeenCalled();
  await act(() => message(nativeView()));
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('rejects callbacks from a replaced route and an unmounted view', async () => {
  const view = await render(screen());
  const old = nativeView();
  mockParams = { ...mockParams, url: 'https://provider.example.test/form-b' };
  await view.rerender(screen());
  await act(() => message(old));
  expect(mockGoBack).not.toHaveBeenCalled();
  const current = nativeView();
  await view.unmount();
  await act(() => message(current));
  expect(mockGoBack).not.toHaveBeenCalled();
  expect(mockInvalidate).not.toHaveBeenCalled();
});

it('handles widget close once without reporting a purchase', async () => {
  await render(screen());
  const current = nativeView();
  await act(async () => {
    await message(current, 'TRANSAK_WIDGET_CLOSE');
    await message(current);
  });
  expect(mockGoBack).toHaveBeenCalledTimes(1);
  expect(mockInvalidate).not.toHaveBeenCalled();
  expect(mockViews.size).toBe(0);
});

it('keeps a completed provider retired across later focus changes', async () => {
  const view = await render(screen());
  await act(() => message(nativeView()));
  mockFocused = false;
  await view.rerender(screen());
  mockFocused = true;
  await view.rerender(screen());
  expect(mockViews.size).toBe(0);
  expect(mockGoBack).toHaveBeenCalledTimes(1);
});

it('reports load errors without logging or displaying the provider URL or native details', async () => {
  const warning = jest.spyOn(console, 'warn').mockImplementation(() => {});
  mockParams = { ...mockParams, url: 'https://provider.example.test/form?secret=synthetic-private-value' };
  const view = await render(screen());
  const error = {
    persist: jest.fn(),
    isDefaultPrevented: () => false,
    nativeEvent: {
      url: mockParams.url,
      description: 'synthetic-private-value',
      domain: 'private-provider-detail',
      code: -1,
    },
  } as unknown as Parameters<NonNullable<NativeProps['onLoadingError']>>[0];
  await act(() => nativeView().onLoadingError?.(error));
  expect(warning).toHaveBeenCalledWith('The purchase provider could not load.');
  expect(JSON.stringify(warning.mock.calls)).not.toContain('synthetic-private-value');
  expect(JSON.stringify(view.toJSON())).not.toContain('synthetic-private-value');
  expect(view.getByText('Could not load the purchase provider. Go back and try again.')).toBeTruthy();
});
