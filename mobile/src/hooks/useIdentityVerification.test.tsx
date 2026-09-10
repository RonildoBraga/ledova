import React from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { getSessionEpoch, invalidateSessionScope } from '../services/sessionScope';
import { useIdentityVerification } from './useIdentityVerification';

jest.mock('../services/apiClient', () => ({ apiClient: { get: jest.fn(), post: jest.fn() } }));

const get = apiClient.get as jest.Mock;
const post = apiClient.post as jest.Mock;
let client: QueryClient;
let fakeClock = false;
const settleOutstanding: (() => void)[] = [];
const formA = { data: { accessToken: 'synthetic-token-a', formUrl: null } };
const formB = { data: { accessToken: null, formUrl: 'https://verification.example.test/form-b' } };

function deferred() {
  let resolve!: (value: typeof formA | typeof formB) => void;
  const promise = new Promise<typeof formA | typeof formB>((accept) => {
    resolve = accept;
  });
  settleOutstanding.push(() => resolve(formA));
  return { promise, resolve };
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  get.mockReset().mockResolvedValue({ data: { isVerified: false, status: 'init' } });
  post.mockReset().mockResolvedValue(formA);
});

afterEach(async () => {
  await cleanup();
  await act(() => settleOutstanding.splice(0).forEach((settle) => settle()));
  client.clear();
  if (fakeClock) {
    jest.clearAllTimers();
    jest.useRealTimers();
    fakeClock = false;
  }
});

it('keeps the current successful launch and submitted progression', async () => {
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.accessToken).toBe(formA.data.accessToken);
  expect(result.current!.formUrl).toBeNull();
  expect(result.current!.showVerificationForm).toBe(true);
  await act(() => result.current!.handleFormComplete());
  expect(result.current!.showVerificationForm).toBe(false);
  expect(result.current!.justSubmitted).toBe(true);
});

it.each(['close', 'reset', 'session'] as const)(
  'does not reopen a form after a pending launch is retired by %s',
  async (action) => {
    const pending = deferred();
    post.mockReturnValue(pending.promise);
    const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
    let launch!: Promise<void>;
    await act(() => {
      launch = result.current!.launchVerification();
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await act(() => {
      if (action === 'close') result.current!.closeFormModal();
      else if (action === 'reset') result.current!.resetState();
      else invalidateSessionScope();
    });
    await act(async () => {
      pending.resolve(formA);
      await launch;
    });
    expect(result.current!.showVerificationForm).toBe(false);
    expect(result.current!.accessToken).toBeNull();
    await act(async () => {
      post.mockResolvedValue(formB);
      await result.current!.launchVerification();
    });
    expect(result.current!.formUrl).toBe(formB.data.formUrl);
  },
);

it('preserves a new form when an older launch returns after close and a deliberate relaunch', async () => {
  const old = deferred();
  post.mockReturnValueOnce(old.promise).mockResolvedValueOnce(formB);
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  let launch!: Promise<void>;
  await act(() => {
    launch = result.current!.launchVerification();
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await act(() => result.current!.closeFormModal());
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.formUrl).toBe(formB.data.formUrl);
  await act(async () => {
    old.resolve(formA);
    await launch;
  });
  expect(result.current!.formUrl).toBe(formB.data.formUrl);
  expect(result.current!.accessToken).toBeNull();
});

it('replaces both credential fields when the provider changes', async () => {
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.accessToken).toBe(formA.data.accessToken);
  post.mockResolvedValue(formB);
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.formUrl).toBe(formB.data.formUrl);
  expect(result.current!.accessToken).toBeNull();
});

it('preserves the backend initialization error and permits an explicit retry', async () => {
  post.mockRejectedValueOnce(new Error('Synthetic backend initialization refusal'));
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.sdkError).toBe('Synthetic backend initialization refusal');
  expect(result.current!.showVerificationForm).toBe(false);
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.sdkError).toBeNull();
  expect(result.current!.accessToken).toBe(formA.data.accessToken);
});

it('does not apply an older launch refusal to a newer form', async () => {
  let reject!: (error: Error) => void;
  const pending = new Promise<never>((_, refuse) => {
    reject = refuse;
  });
  settleOutstanding.push(() => reject(new Error('Synthetic retired refusal')));
  post.mockReturnValueOnce(pending).mockResolvedValueOnce(formB);
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  let launch!: Promise<void>;
  await act(() => {
    launch = result.current!.launchVerification();
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await act(() => result.current!.closeFormModal());
  await act(async () => {
    await result.current!.launchVerification();
  });
  await act(async () => {
    reject(new Error('Synthetic retired refusal'));
    await launch;
  });
  expect(result.current!.formUrl).toBe(formB.data.formUrl);
  expect(result.current!.sdkError).toBeNull();
});

it('retires credentials immediately on session change while preserving normal fresh launches', async () => {
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  await act(async () => {
    await result.current!.launchVerification();
  });
  const previous = getSessionEpoch();
  expect(result.current!.showVerificationForm).toBe(true);
  await act(() => invalidateSessionScope());
  expect(getSessionEpoch()).not.toBe(previous);
  expect(result.current!.showVerificationForm).toBe(false);
  await act(async () => {
    post.mockResolvedValue(formB);
    await result.current!.launchVerification();
  });
  expect(result.current!.showVerificationForm).toBe(true);
});

it('does not install or invalidate queries for a launch whose owner unmounted', async () => {
  const pending = deferred();
  post.mockReturnValue(pending.promise);
  const invalidate = jest.spyOn(client, 'invalidateQueries');
  const { result, unmount } = await renderHook(() => useIdentityVerification(), { wrapper });
  let launch!: Promise<void>;
  await act(() => {
    launch = result.current!.launchVerification();
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await unmount();
  await act(async () => {
    pending.resolve(formA);
    await launch;
  });
  expect(invalidate).not.toHaveBeenCalled();
});

it('keeps hidden owners idle and retires a launch when visibility or focus is lost', async () => {
  const pending = deferred();
  const { result, rerender } = await renderHook(
    ({ enabled }: { enabled: boolean }) => useIdentityVerification(enabled),
    {
      wrapper,
      initialProps: { enabled: false },
    },
  );
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(post).not.toHaveBeenCalled();
  post.mockReturnValue(pending.promise);
  await rerender({ enabled: true });
  let launch!: Promise<void>;
  await act(() => {
    launch = result.current!.launchVerification();
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await rerender({ enabled: false });
  await act(async () => {
    pending.resolve(formA);
    await launch;
  });
  await rerender({ enabled: true });
  expect(result.current!.showVerificationForm).toBe(false);
  post.mockResolvedValue(formB);
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(result.current!.formUrl).toBe(formB.data.formUrl);
});

it('latches duplicate launch presses without blocking a later deliberate launch', async () => {
  const pending = deferred();
  post.mockReturnValue(pending.promise);
  const { result } = await renderHook(() => useIdentityVerification(), { wrapper });
  let launches!: Promise<void[]>;
  await act(() => {
    launches = Promise.all([result.current!.launchVerification(), result.current!.launchVerification()]);
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await act(async () => {
    pending.resolve(formA);
    await launches;
  });
  await act(() => result.current!.closeFormModal());
  await act(async () => {
    await result.current!.launchVerification();
  });
  expect(post).toHaveBeenCalledTimes(2);
});

it('keeps submitted status polling when the owner hides and retires it on session change', async () => {
  jest.useFakeTimers();
  fakeClock = true;
  const { result, rerender } = await renderHook(
    ({ enabled }: { enabled: boolean }) => useIdentityVerification(enabled),
    {
      wrapper,
      initialProps: { enabled: true },
    },
  );
  await act(async () => {
    await result.current!.launchVerification();
  });
  await act(() => result.current!.handleFormComplete());
  expect(result.current!.justSubmitted).toBe(true);
  await rerender({ enabled: false });
  expect(result.current!.justSubmitted).toBe(true);
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  get.mockClear();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(5000);
  });
  expect(get).toHaveBeenCalledTimes(1);
  await act(() => invalidateSessionScope());
  expect(result.current!.justSubmitted).toBe(false);
  get.mockClear();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(5000);
  });
  expect(get).not.toHaveBeenCalled();
});
