// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTradingEvents } from './useTradingEvents';

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readonly withCredentials: boolean;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  closeCalls = 0;
  private readonly listeners = new Map<string, Set<EventListenerOrEventListenerObject>>();

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = url.toString();
    this.withCredentials = init?.withCredentials ?? false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const listeners = this.listeners.get(type) ?? new Set<EventListenerOrEventListenerObject>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  close() {
    this.closed = true;
    this.closeCalls += 1;
  }

  emit(type: string) {
    const event = new Event(type);
    for (const listener of this.listeners.get(type) ?? []) {
      if (typeof listener === 'function') {
        listener(event);
      } else {
        listener.handleEvent(event);
      }
    }
  }

  fail() {
    this.onerror?.();
  }
}

function createWrapper(queryClient: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useTradingEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
    vi.stubEnv('VITE_API_URL', 'https://api.example.test/');
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('opens a credentialed stream with only the public market token parameter', () => {
    const queryClient = new QueryClient();
    const tokenUuid = '123e4567-e89b-12d3-a456-426614174000';

    const { unmount } = renderHook(() => useTradingEvents(tokenUuid), {
      wrapper: createWrapper(queryClient),
    });

    expect(FakeEventSource.instances).toHaveLength(1);
    const source = FakeEventSource.instances[0];
    const streamUrl = new URL(source.url);
    expect(`${streamUrl.origin}${streamUrl.pathname}`).toBe('https://api.example.test/api/v1/trading/events/stream/');
    expect([...streamUrl.searchParams.keys()]).toEqual(['token']);
    expect(streamUrl.searchParams.get('token')).toBe(tokenUuid);
    expect(source.withCredentials).toBe(true);

    unmount();
    queryClient.clear();
  });

  it('invalidates the mapped queries for a known event', () => {
    const queryClient = new QueryClient();
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined);

    const { unmount } = renderHook(() => useTradingEvents('123e4567-e89b-12d3-a456-426614174000'), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      FakeEventSource.instances[0].emit('order_created');
    });

    expect(invalidateQueries).toHaveBeenNthCalledWith(1, { queryKey: ['trading', 'orderBook'] });
    expect(invalidateQueries).toHaveBeenNthCalledWith(2, { queryKey: ['trading', 'userOrders'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(2);

    unmount();
    queryClient.clear();
  });

  it('closes replaced and unmounted streams without reconnecting after unmount', () => {
    const queryClient = new QueryClient();
    const { rerender, unmount } = renderHook(({ tokenUuid }) => useTradingEvents(tokenUuid), {
      initialProps: { tokenUuid: '123e4567-e89b-12d3-a456-426614174000' },
      wrapper: createWrapper(queryClient),
    });
    const firstSource = FakeEventSource.instances[0];

    rerender({ tokenUuid: '223e4567-e89b-12d3-a456-426614174000' });

    expect(firstSource.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(2);
    const secondSource = FakeEventSource.instances[1];

    act(() => {
      secondSource.fail();
    });
    expect(secondSource.closed).toBe(true);
    expect(secondSource.closeCalls).toBe(1);

    unmount();
    expect(secondSource.closeCalls).toBe(2);
    act(() => {
      vi.runAllTimers();
    });

    expect(FakeEventSource.instances).toHaveLength(2);
    queryClient.clear();
  });
});
