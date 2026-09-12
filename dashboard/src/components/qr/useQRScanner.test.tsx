// @vitest-environment jsdom

import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useQRScanner } from './useQRScanner';

const pendingCleanups: (() => void)[] = [];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  pendingCleanups.push(() => resolve(undefined as T));
  return { promise, resolve, reject };
}

const camera = vi.hoisted(() => ({
  discover: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  instances: [] as {
    success: (value: string) => void;
    state: number;
    stop: () => Promise<void>;
  }[],
}));
vi.mock('html5-qrcode', () => ({
  Html5Qrcode: class {
    static getCameras = camera.discover;
    success: (value: string) => void = () => {};
    state = 1;
    constructor() {
      camera.instances.push(this);
    }
    getState() {
      return this.state;
    }
    async start(_id: string, _configuration: unknown, success: (value: string) => void) {
      this.success = success;
      await camera.start(this);
      this.state = 2;
    }
    async stop() {
      await camera.stop(this);
      this.state = 1;
    }
  },
}));

function Scanner({ enabled = true, onScan = () => {} }: { enabled?: boolean; onScan?: (value: string) => void }) {
  const scanner = useQRScanner({ scannerId: 'synthetic-scanner', enabled, onScanSuccess: onScan });
  return (
    <>
      <div id="synthetic-scanner" />
      <p role="status">{scanner.isScanning ? 'scanning' : 'idle'}</p>
      {scanner.error && <p role="alert">{scanner.error}</p>}
      <button onClick={scanner.stopScanner}>Stop</button>
    </>
  );
}

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(101);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  camera.instances.length = 0;
  camera.discover.mockResolvedValue([{ id: 'synthetic-camera' }]);
  camera.start.mockResolvedValue(undefined);
  camera.stop.mockResolvedValue(undefined);
});
afterEach(async () => {
  cleanup();
  await act(async () => {
    for (const finish of pendingCleanups.splice(0)) finish();
  });
  vi.useRealTimers();
  vi.resetAllMocks();
});

it('uses the latest live callback once and stops only the scanner that delivered it', async () => {
  const previous = vi.fn();
  const current = vi.fn();
  const view = render(<Scanner onScan={previous} />);
  await tick();
  view.rerender(<Scanner onScan={current} />);
  const scanner = camera.instances[0]!;
  await act(async () => {
    scanner.success('live');
    scanner.success('duplicate');
  });
  expect(previous).not.toHaveBeenCalled();
  expect(current).toHaveBeenCalledExactlyOnceWith('live');
  expect(camera.start).toHaveBeenCalledOnce();
  expect(camera.stop).toHaveBeenCalledExactlyOnceWith(scanner);
  expect(screen.getByRole('status').textContent).toBe('idle');
});

it('drops a stopped run callback after reopening and preserves its live replacement', async () => {
  const onScan = vi.fn();
  const view = render(<Scanner onScan={onScan} />);
  await tick();
  const old = camera.instances[0]!;
  view.rerender(<Scanner enabled={false} onScan={onScan} />);
  view.rerender(<Scanner onScan={onScan} />);
  await tick();
  const current = camera.instances[1]!;
  expect(camera.stop).toHaveBeenCalledExactlyOnceWith(old);
  await act(async () => old.success('retired'));
  expect(onScan).not.toHaveBeenCalled();
  expect(camera.stop).toHaveBeenCalledExactlyOnceWith(old);
  expect(screen.getByRole('status').textContent).toBe('scanning');
  await act(async () => current.success('current'));
  expect(onScan).toHaveBeenCalledExactlyOnceWith('current');
  expect(camera.stop).toHaveBeenLastCalledWith(current);
});

it('never starts a retired discovery after a new run has become active', async () => {
  const discovered = deferred<{ id: string }[]>();
  camera.discover.mockReturnValueOnce(discovered.promise);
  const onScan = vi.fn();
  const view = render(<Scanner onScan={onScan} />);
  await tick();
  view.rerender(<Scanner enabled={false} onScan={onScan} />);
  view.rerender(<Scanner onScan={onScan} />);
  await tick();
  expect(camera.start).toHaveBeenCalledOnce();
  const current = camera.start.mock.calls[0]![0];
  await act(async () => discovered.resolve([{ id: 'old-camera' }]));
  expect(camera.start).toHaveBeenCalledOnce();
  await act(async () => current.success('current'));
  expect(onScan).toHaveBeenCalledExactlyOnceWith('current');
});

it.each(['disable', 'unmount'] as const)(
  'waits for an old pending start and owned teardown across %s before starting at the same element ID',
  async (retirement) => {
    const started = deferred<void>();
    const stopped = deferred<void>();
    camera.start.mockReturnValueOnce(started.promise);
    camera.stop.mockReturnValueOnce(stopped.promise);
    const onScan = vi.fn();
    let view = render(<Scanner onScan={onScan} />);
    await tick();
    const old = camera.instances[0]!;
    expect(camera.start).toHaveBeenCalledOnce();
    if (retirement === 'unmount') {
      view.unmount();
      view = render(<Scanner onScan={onScan} />);
    } else {
      view.rerender(<Scanner enabled={false} onScan={onScan} />);
      view.rerender(<Scanner onScan={onScan} />);
    }
    await tick();
    expect(camera.start).toHaveBeenCalledOnce();
    await act(async () => started.resolve());
    expect(camera.stop).toHaveBeenCalledExactlyOnceWith(old);
    expect(camera.start).toHaveBeenCalledOnce();
    await act(async () => old.success('retired'));
    expect(onScan).not.toHaveBeenCalled();
    await act(async () => stopped.resolve());
    expect(camera.start).toHaveBeenCalledTimes(2);
    const current = camera.start.mock.calls[1]![0];
    expect(screen.getByRole('status').textContent).toBe('scanning');
    await act(async () => current.success('current'));
    expect(onScan).toHaveBeenCalledExactlyOnceWith('current');
    expect(camera.stop).toHaveBeenLastCalledWith(current);
  },
);

it('does not publish a retired discovery rejection over the replacement state', async () => {
  const discovered = deferred<{ id: string }[]>();
  camera.discover.mockReturnValueOnce(discovered.promise);
  const view = render(<Scanner />);
  await tick();
  view.rerender(<Scanner enabled={false} />);
  view.rerender(<Scanner />);
  await tick();
  await act(async () => discovered.reject(new Error('old discovery rejected')));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByRole('status').textContent).toBe('scanning');
});

it('retains a current discovery error and does not start a camera', async () => {
  camera.discover.mockResolvedValue([]);
  render(<Scanner />);
  await tick();
  expect(screen.getByRole('alert').textContent).toBe('No cameras found');
  expect(camera.start).not.toHaveBeenCalled();
});

it('keeps the replacement fence when its predecessor cleanup finishes', async () => {
  const firstStop = deferred<void>();
  const secondStop = deferred<void>();
  camera.stop.mockReturnValueOnce(firstStop.promise).mockReturnValueOnce(secondStop.promise);
  const onScan = vi.fn();
  const view = render(<Scanner onScan={onScan} />);
  await tick();
  view.rerender(<Scanner enabled={false} onScan={onScan} />);
  view.rerender(<Scanner onScan={onScan} />);
  await tick();
  expect(camera.start).toHaveBeenCalledOnce();
  await act(async () => firstStop.resolve());
  expect(camera.start).toHaveBeenCalledTimes(2);
  view.rerender(<Scanner enabled={false} onScan={onScan} />);
  view.rerender(<Scanner onScan={onScan} />);
  await tick();
  expect(camera.start).toHaveBeenCalledTimes(2);
  await act(async () => secondStop.resolve());
  expect(camera.start).toHaveBeenCalledTimes(3);
  await act(async () => camera.instances[2]!.success('third'));
  expect(onScan).toHaveBeenCalledExactlyOnceWith('third');
});

it('the locked Html5Qrcode decode can finish after actual stop resolves', async () => {
  const { Html5Qrcode } = await vi.importActual<typeof import('html5-qrcode')>('html5-qrcode');
  const pending = deferred<{ text: string; format: { formatName: string } }>();
  const success = vi.fn();
  const scanner = Object.create(Html5Qrcode.prototype) as InstanceType<typeof Html5Qrcode>;
  Object.assign(scanner, {
    shouldScan: true,
    stateManagerProxy: {
      isPaused: () => false,
      isScanning: () => true,
      startTransition: () => ({ execute() {} }),
    },
    qrcode: { decodeAsync: () => pending.promise },
    canvasElement: {},
    possiblyUpdateShaders: () => {},
    renderedCamera: { close: async () => {} },
    hidePausedState: () => {},
  });
  const completion = (
    scanner as unknown as {
      scanContext: (success: (value: string) => void, failure: () => void) => Promise<boolean>;
    }
  ).scanContext(success, () => {});
  await scanner.stop();
  expect((scanner as unknown as { shouldScan: boolean }).shouldScan).toBe(false);
  pending.resolve({ text: 'synthetic-completed-decode', format: { formatName: 'QR_CODE' } });
  await completion;
  expect(success).toHaveBeenCalledWith('synthetic-completed-decode', expect.any(Object));
});
