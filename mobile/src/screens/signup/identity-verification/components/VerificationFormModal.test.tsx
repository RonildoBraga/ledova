import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import type { NativeProps } from 'react-native-webview/lib/RNCWebViewNativeComponent';
import type { WebViewMessageEvent } from 'react-native-webview';
import { CameraAccessContext, createCameraAccess } from '../../../../contexts/cameraAccess';
import { getSessionEpoch, invalidateSessionScope } from '../../../../services/sessionScope';

const mockViews = new Map<number, NativeProps>();
const mockMounts = jest.fn();
const mockUnmounts = jest.fn();
const mockLoadDecision = jest.fn();
const mockReadPreference = jest.fn();
const mockReadSession = jest.fn();
const mockAuthenticate = jest.fn();
let mockViewId = 0;
const listeners = new Set<(state: AppStateStatus) => void>();
const settleOutstanding: (() => void)[] = [];
let fakeClock = false;

jest.mock('expo-secure-store', () => ({ getItemAsync: () => mockReadPreference() }));
jest.mock('expo-local-authentication', () => ({
  AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2 },
  hasHardwareAsync: async () => true,
  isEnrolledAsync: async () => true,
  supportedAuthenticationTypesAsync: async () => [1],
  authenticateAsync: () => mockAuthenticate(),
}));
jest.mock('../../../../services/tokenStorage', () => ({
  getAccessToken: () => mockReadSession(),
  getBiometricLoginState: async () => ({ enabled: false, ready: false }),
}));

jest.unmock('react-native/Libraries/Modal/Modal');
jest.mock('react-native-webview', () => jest.requireActual('react-native-webview/src/WebView.ios'));
jest.mock('react-native-webview/src/NativeRNCWebViewModule', () => ({
  __esModule: true,
  default: {
    shouldStartLoadWithLockIdentifier: (...args: unknown[]) => mockLoadDecision(...args),
  },
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
      useLayoutEffect(() => {
        mockMounts(id);
        return () => {
          mockViews.delete(id);
          mockUnmounts(id);
        };
      }, [id]);
      return <View testID="identity-provider-native-view" />;
    },
  };
});

import { VerificationFormModal } from './VerificationFormModal';
import { AppLockProvider, useAppLock } from '../../../../contexts/AppLockContext';

let currentLock: ReturnType<typeof useAppLock>;

function LockControl() {
  const lock = useAppLock();
  React.useLayoutEffect(() => {
    currentLock = lock;
  }, [lock]);
  return null;
}

function lockedForm() {
  return (
    <AppLockProvider>
      <LockControl />
      <VerificationFormModal
        visible
        accessToken={token}
        formUrl={null}
        sessionEpoch={getSessionEpoch()}
        onComplete={complete}
        onClose={close}
      />
    </AppLockProvider>
  );
}

let access = createCameraAccess();
const complete = jest.fn();
const close = jest.fn();
const token = 'synthetic-provider-token-a';
const formUrl = 'https://verification.example.test/form-a';

function form(
  props: Partial<React.ComponentProps<typeof VerificationFormModal>> & { sessionEpoch?: number | null } = {},
) {
  return (
    <CameraAccessContext.Provider value={access}>
      <VerificationFormModal
        visible
        accessToken={token}
        formUrl={null}
        onComplete={complete}
        onClose={close}
        {...{ sessionEpoch: getSessionEpoch(), ...props }}
      />
    </CameraAccessContext.Provider>
  );
}

function nativeView() {
  expect(mockViews.size).toBe(1);
  return [...mockViews.values()][0];
}

function message(view: NativeProps, data: unknown) {
  return view.onMessage?.({ nativeEvent: { data: JSON.stringify(data) } } as WebViewMessageEvent);
}

function navigate(view: NativeProps, url: string) {
  return view.onLoadingStart?.({ nativeEvent: { url } } as Parameters<NonNullable<NativeProps['onLoadingStart']>>[0]);
}

async function appState(state: AppStateStatus, reverse = false) {
  await act(() => {
    AppState.currentState = state;
    const ordered = [...listeners];
    if (reverse) ordered.reverse();
    ordered.forEach((listener) => listener(state));
  });
}

beforeEach(() => {
  access = createCameraAccess();
  access.setAllowed(true);
  AppState.currentState = 'active';
  listeners.clear();
  mockViews.clear();
  mockReadPreference.mockReset().mockResolvedValue('true');
  mockReadSession.mockReset().mockResolvedValue('synthetic-session');
  mockAuthenticate.mockReset().mockResolvedValue({ success: true });
  jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') listeners.add(listener);
    return { remove: () => listeners.delete(listener) };
  });
});

afterEach(async () => {
  await cleanup();
  await act(() => settleOutstanding.splice(0).forEach((settle) => settle()));
  if (fakeClock) {
    jest.clearAllTimers();
    jest.useRealTimers();
    fakeClock = false;
  }
  expect(mockViews.size).toBe(0);
});

it('delivers one current provider completion and retires its native view', async () => {
  const view = await render(form());
  const current = nativeView();
  expect(current.newSource).toEqual(expect.objectContaining({ html: expect.stringContaining(token) }));
  await act(() =>
    Promise.all([message(current, { event: 'FORM_COMPLETED' }), message(current, { event: 'FORM_COMPLETED' })]),
  );
  expect(complete).toHaveBeenCalledTimes(1);
  expect(view.queryByTestId('identity-provider-native-view')).toBeNull();
});

it('keeps a never-opened form idle, then admits the visible positive control', async () => {
  const view = await render(form({ visible: false }));
  expect(mockMounts).not.toHaveBeenCalled();
  await view.rerender(form());
  expect(nativeView().newSource).toBeTruthy();
});

it('removes the provider during iOS modal dismissal and retires the old opening', async () => {
  const view = await render(form());
  const old = nativeView();
  await view.rerender(form({ visible: false }));
  expect(mockViews.size).toBe(0);
  await view.rerender(form());
  await act(() => message(old, { event: 'FORM_COMPLETED' }));
  expect(complete).not.toHaveBeenCalled();
  await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  expect(complete).toHaveBeenCalledTimes(1);
});

it.each(['token', 'url'] as const)(
  'retires a replaced %s callback while the replacement remains usable',
  async (kind) => {
    const initial = kind === 'token' ? {} : { accessToken: null, formUrl };
    const view = await render(form(initial));
    const old = nativeView();
    const next =
      kind === 'token' ? { accessToken: 'synthetic-provider-token-b' } : { accessToken: null, formUrl: `${formUrl}-b` };
    await view.rerender(form(next));
    await act(() => message(old, { event: 'FORM_COMPLETED' }));
    expect(complete).not.toHaveBeenCalled();
    expect(mockMounts).toHaveBeenCalledTimes(2);
    await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
    expect(complete).toHaveBeenCalledTimes(1);
  },
);

it.each(['background', 'inactive'] as const)(
  'unmounts on %s and refuses pre-pause callbacks after resume',
  async (state) => {
    const view = await render(form());
    const old = nativeView();
    await appState(state);
    expect(mockViews.size).toBe(0);
    await act(() => message(old, { event: 'FORM_COMPLETED' }));
    expect(complete).not.toHaveBeenCalled();
    await appState('active');
    const resumed = nativeView();
    expect(resumed.newSource).toEqual(old.newSource);
    await act(async () => {
      await message(old, { event: 'FORM_COMPLETED' });
      await message(resumed, { event: 'FORM_COMPLETED' });
    });
    expect(complete).toHaveBeenCalledTimes(1);
    expect(view.queryByTestId('identity-provider-native-view')).toBeNull();
  },
);

it('refuses a retained callback before the app-lock subscriber or React handles the pause', async () => {
  const notifications: (Promise<void> | void)[] = [];
  const unsubscribe = access.subscribe(() => {
    if (!access.getSnapshot().allowed) notifications.push(message(retained, { event: 'FORM_COMPLETED' }));
  });
  const view = await render(form());
  const retained = nativeView();
  await act(() => access.setAllowed(false));
  await Promise.all(notifications);
  expect(complete).not.toHaveBeenCalled();
  expect(mockViews.size).toBe(0);
  await act(() => access.setAllowed(true));
  await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  expect(complete).toHaveBeenCalledTimes(1);
  unsubscribe();
  await view.unmount();
});

it('withholds an initially locked form and admits it after evaluation allows access', async () => {
  access.setAllowed(false);
  await render(form());
  expect(mockMounts).not.toHaveBeenCalled();
  await act(() => access.setAllowed(true));
  expect(nativeView().newSource).toBeTruthy();
});

it('retires session-owned credentials and callbacks without silently rebinding them on reopen', async () => {
  const epoch = getSessionEpoch();
  const view = await render(form({ sessionEpoch: epoch }));
  const old = nativeView();
  await act(() => invalidateSessionScope());
  expect(mockViews.size).toBe(0);
  await view.rerender(form({ visible: false, sessionEpoch: epoch }));
  await view.rerender(form({ sessionEpoch: epoch }));
  expect(mockViews.size).toBe(0);
  await act(() => message(old, { event: 'FORM_COMPLETED' }));
  expect(complete).not.toHaveBeenCalled();
  await view.rerender(form({ accessToken: 'synthetic-new-session-token' }));
  await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  expect(complete).toHaveBeenCalledTimes(1);
});

it('retires callbacks on full unmount while a new instance remains usable', async () => {
  const view = await render(form());
  const old = nativeView();
  await view.unmount();
  await render(form());
  await act(() => message(old, { event: 'FORM_COMPLETED' }));
  expect(complete).not.toHaveBeenCalled();
  await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  expect(complete).toHaveBeenCalledTimes(1);
});

it('retains the current KYCAID redirect convention without accepting an old navigation callback', async () => {
  const view = await render(form({ accessToken: null, formUrl }));
  const old = nativeView();
  await act(() => navigate(old, 'https://unrelated.example.test/'));
  expect(complete).not.toHaveBeenCalled();
  await view.rerender(form({ accessToken: null, formUrl: `${formUrl}-new` }));
  await act(() => navigate(old, 'https://localhost/verification-result'));
  expect(complete).not.toHaveBeenCalled();
  await act(() => navigate(nativeView(), 'https://localhost/verification-result'));
  expect(complete).toHaveBeenCalledTimes(1);
});

it('keeps raw SDK errors out of native logs', async () => {
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  await render(form());
  const current = nativeView();
  const secret = 'synthetic-provider-secret-in-error-url';
  await act(() => message(current, { event: 'SDK_ERROR', message: secret }));
  expect(warn).toHaveBeenCalledWith('Identity verification form reported an error.');
  expect(JSON.stringify(warn.mock.calls)).not.toContain(secret);
});

it('keeps raw native loading errors out of logs and rendered error text', async () => {
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  const view = await render(form());
  const current = nativeView();
  const secret = 'synthetic-provider-secret-in-error-url';
  const error = {
    nativeEvent: { url: `${formUrl}?token=${secret}`, description: secret, code: -1, domain: secret },
    persist: jest.fn(),
    isDefaultPrevented: () => false,
  } as unknown as Parameters<NonNullable<NativeProps['onLoadingError']>>[0];
  await act(() => current.onLoadingError?.(error));
  expect(JSON.stringify(warn.mock.calls)).not.toContain(secret);
  expect(view.queryByText(secret, { exact: false })).toBeNull();
  expect(view.getByText('Could not load verification. Close this form and try again.')).toBeTruthy();
});

it('does not allow a retained load decision after pause and keeps current HTTPS navigation working', async () => {
  await render(form());
  const old = nativeView();
  const event = { nativeEvent: { url: formUrl, lockIdentifier: 7 } } as Parameters<
    NonNullable<NativeProps['onShouldStartLoadWithRequest']>
  >[0];
  await act(() => old.onShouldStartLoadWithRequest?.(event));
  expect(mockLoadDecision).toHaveBeenLastCalledWith(true, 7);
  await appState('background');
  await act(() => old.onShouldStartLoadWithRequest?.(event));
  expect(mockLoadDecision).toHaveBeenLastCalledWith(false, 7);
});

it('retires completion synchronously when close is pressed before the parent hides it', async () => {
  const view = await render(form());
  const old = nativeView();
  await fireEvent.press(view.getByTestId('phosphor-react-native-x-bold'));
  await act(() => message(old, { event: 'FORM_COMPLETED' }));
  expect(close).toHaveBeenCalledTimes(1);
  expect(complete).not.toHaveBeenCalled();
  expect(mockViews.size).toBe(0);
});

it.each(['completed', 'closed'] as const)('keeps a %s form retired across a lock pause', async (state) => {
  const view = await render(form());
  if (state === 'completed') await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  else await fireEvent.press(view.getByTestId('phosphor-react-native-x-bold'));
  await act(() => access.setAllowed(false));
  await appState('background');
  await appState('active');
  await act(() => access.setAllowed(true));
  expect(mockViews.size).toBe(0);
  expect(mockMounts).toHaveBeenCalledTimes(1);
  await view.rerender(form({ accessToken: 'synthetic-next-form-token' }));
  expect(nativeView().newSource).toBeTruthy();
});

function deferred<T>(fallback: T) {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  settleOutstanding.push(() => resolve(fallback));
  return { promise, resolve };
}

function startClock() {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-09-10T00:00:00Z'));
  fakeClock = true;
}

async function leaveAndReturn(reverse = false) {
  await appState('background', reverse);
  jest.setSystemTime(Date.now() + 3001);
  await appState('active', reverse);
}

it('withholds the WebView during actual app-lock provider initialization', async () => {
  const preference = deferred<string | null>('false');
  mockReadPreference.mockReturnValue(preference.promise);
  await render(lockedForm());
  expect(mockMounts).not.toHaveBeenCalled();
  await act(() => preference.resolve('false'));
  expect(nativeView().newSource).toBeTruthy();
});

it.each([false, true])('waits for the real foreground lock evaluation in listener order %s', async (reverse) => {
  startClock();
  const session = deferred<string | null>(null);
  mockReadSession.mockReturnValue(session.promise);
  await render(lockedForm());
  const old = nativeView();
  await leaveAndReturn(reverse);
  expect(mockReadSession).toHaveBeenCalledTimes(1);
  expect(mockViews.size).toBe(0);
  expect(mockMounts).toHaveBeenCalledTimes(1);
  await act(() => message(old, { event: 'FORM_COMPLETED' }));
  expect(complete).not.toHaveBeenCalled();
  await act(() => session.resolve(null));
  expect(mockMounts).toHaveBeenCalledTimes(2);
  await act(() => message(nativeView(), { event: 'FORM_COMPLETED' }));
  expect(complete).toHaveBeenCalledTimes(1);
});

it.each(['refused', 'rejected'] as const)(
  'stays unmounted through a %s unlock and resumes only after success',
  async (result) => {
    startClock();
    await render(lockedForm());
    const old = nativeView();
    await leaveAndReturn();
    expect(currentLock.isLocked).toBe(true);
    expect(mockViews.size).toBe(0);
    if (result === 'refused') mockAuthenticate.mockResolvedValueOnce({ success: false });
    else mockAuthenticate.mockRejectedValueOnce(new Error('synthetic native authentication refusal'));
    await act(async () => {
      expect(await currentLock.unlock()).toBe(false);
    });
    expect(mockViews.size).toBe(0);
    await act(async () => {
      expect(await currentLock.unlock()).toBe(true);
    });
    expect(nativeView().newSource).toEqual(old.newSource);
    await act(async () => {
      await message(old, { event: 'FORM_COMPLETED' });
      await message(nativeView(), { event: 'FORM_COMPLETED' });
    });
    expect(complete).toHaveBeenCalledTimes(1);
  },
);

it('keeps an authentication success in the background paused until the app returns', async () => {
  startClock();
  const authentication = deferred({ success: false });
  mockAuthenticate.mockReturnValue(authentication.promise);
  await render(lockedForm());
  await leaveAndReturn();
  let unlock!: Promise<boolean>;
  await act(() => {
    unlock = currentLock.unlock();
  });
  await appState('background');
  await act(async () => {
    authentication.resolve({ success: true });
    expect(await unlock).toBe(true);
  });
  expect(mockViews.size).toBe(0);
  await appState('active');
  expect(nativeView().newSource).toBeTruthy();
});

it.each(['sdk', 'startup', 'script-load'] as const)(
  'executes the SDK %s error path without exposing its payload',
  async (failure) => {
    await render(form());
    const html = nativeView().newSource?.html;
    expect(typeof html).toBe('string');
    const source = html!.match(/<script>([\s\S]*?)<\/script>/)![1];
    const elements = {
      loading: { style: {} as Record<string, string> },
      error: { style: {} as Record<string, string>, textContent: '' },
    };
    const script = { src: '', onload: () => {}, onerror: () => {} };
    const events = new Map<string, (...args: unknown[]) => void>();
    const posted = jest.fn();
    const secret = 'synthetic-raw-sdk-error-secret';
    const sdk = {
      init: () => {
        if (failure === 'startup') throw new Error(secret);
        return {
          withConf: () => ({
            on(name: string, handler: (...args: unknown[]) => void) {
              events.set(name, handler);
              return this;
            },
            build: () => ({ launch: jest.fn() }),
          }),
        };
      },
    };
    const execute = new Function('document', 'window', 'snsWebSdk', source);
    execute(
      {
        getElementById: (id: keyof typeof elements) => elements[id],
        createElement: () => script,
        head: { appendChild: () => {} },
      },
      { ReactNativeWebView: { postMessage: posted } },
      sdk,
    );
    if (failure === 'script-load') script.onerror();
    else script.onload();
    if (failure === 'sdk') {
      expect(events.has('idCheck.onApplicantSubmitted')).toBe(true);
      events.get('idCheck.onApplicantSubmitted')!();
      expect(JSON.parse(posted.mock.calls[0][0])).toEqual({ event: 'FORM_COMPLETED' });
      posted.mockClear();
      events.get('idCheck.onError')!({ message: secret });
    }
    expect(elements.error.textContent).toBe('Verification could not continue. Close this form and try again.');
    expect(posted.mock.calls.map(([payload]) => JSON.parse(payload))).toEqual([{ event: 'SDK_ERROR' }]);
    expect(JSON.stringify([elements, posted.mock.calls])).not.toContain(secret);
  },
);
