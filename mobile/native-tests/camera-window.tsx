import '../crypto-polyfill';
import { registerRootComponent, requireNativeModule } from 'expo';
import { CameraView } from 'expo-camera';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AppState, Modal, StyleSheet, Text, View } from 'react-native';
import { apiClient } from '../src/services/apiClient';
import { CameraAccessContext, createCameraAccess } from '../src/contexts/cameraAccess';
import { CameraWindow } from '../src/components/qr/CameraWindow';
import { useCameraScanner } from '../src/components/qr/useCameraScanner';
import { failureCategory, NativeProbeAssertion } from './diagnostics';

type Entry = {
  id: number;
  waiting: boolean;
  awaitedRatio: string;
  attempts: number;
  binds: number;
  ready: number;
  barcodes: number;
  state: string;
  bound: boolean;
  attached: boolean;
  focused: boolean;
  detachedByProbe: boolean;
};
type Snapshot = { activityState: string; activityFocused: boolean; entries: Entry[] };
type Cycle = {
  lost: boolean;
  focused: boolean;
  bound: boolean;
  binds: number;
  attachedAtStart: boolean;
  attachedAtReturn: boolean;
};
type Probe = {
  cameraProbeSnapshot(): Promise<Snapshot>;
  cameraProbeArm(): Promise<void>;
  cameraProbeRelease(id: number): Promise<void>;
  cameraProbeRetire(id: number): Promise<void>;
  cameraProbePause(id: number): Promise<void>;
  cameraProbeScan(id: number): Promise<void>;
  cameraProbeDetach(id: number): Promise<void>;
  cameraProbeReattach(id: number): Promise<void>;
  cameraProbeVisibility(id: number, visible: boolean): Promise<void>;
  cameraProbeCover(): Promise<void>;
  cameraProbeUncover(): Promise<void>;
  cameraProbeReset(): Promise<void>;
  cameraProbeCycle(id: number): Promise<Cycle>;
};
const probe = requireNativeModule<Probe>('ExpoCamera');
const access = createCameraAccess();
access.setAllowed(true);
const pause = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
const completed = new Set<number>();
const changedRatio = new Set<number>();
const scans = new Map<number, number>();
let afterScan: (() => void) | undefined;
let currentSurface = 0;
let renderSurfaces: (values: number[]) => Promise<void>;
let surfaces: number[] = [];

function expect(value: unknown): asserts value {
  if (!value) throw new NativeProbeAssertion();
}

async function waitFor<T>(read: () => Promise<T>, accepts: (value: T) => boolean): Promise<T> {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const value = await read();
    if (accepts(value)) return value;
    await pause(25);
  }
  throw new NativeProbeAssertion();
}

async function state(id: number) {
  const result = (await probe.cameraProbeSnapshot()).entries.find((entry) => entry.id === id);
  expect(result);
  return result;
}

async function mount() {
  const before = (await probe.cameraProbeSnapshot()).entries.map((entry) => entry.id);
  const surface = ++currentSurface;
  surfaces = [...surfaces, surface];
  await renderSurfaces(surfaces);
  const result = await waitFor(
    () => probe.cameraProbeSnapshot(),
    (value) => value.entries.some((entry) => !before.includes(entry.id)),
  );
  return { surface, id: result.entries.find((entry) => !before.includes(entry.id))!.id };
}

async function open() {
  const value = await mount();
  await waitFor(
    () => state(value.id),
    (entry) => entry.bound && entry.state === 'OPEN' && entry.ready > 0,
  );
  return value;
}

async function close(surface: number) {
  surfaces = surfaces.filter((value) => value !== surface);
  await renderSurfaces(surfaces);
}

function stallJavaScript() {
  const deadline = Date.now() + 1500;
  while (Date.now() < deadline) Math.sqrt(2);
}

function Scanner({ surface }: { surface: number }) {
  const camera = useCameraScanner(
    true,
    (_data, finish) => {
      scans.set(surface, (scans.get(surface) || 0) + 1);
      if (completed.has(surface)) finish();
      afterScan?.();
    },
    String(surface),
  );
  return (
    <Modal visible transparent animationType="none">
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <CameraWindow access={camera.windowAccess} style={{ width: 300, height: 300 }}>
          {camera.message ? (
            <Text>{camera.message}</Text>
          ) : (
            <CameraView
              key={camera.previewKey}
              style={StyleSheet.absoluteFillObject}
              facing="back"
              ratio={changedRatio.has(surface) ? '4:3' : undefined}
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
              onBarcodeScanned={camera.onBarcodeScanned}
            />
          )}
        </CameraWindow>
      </View>
    </Modal>
  );
}

type Check = {
  name: string;
  passed: boolean;
  observations: (Snapshot & { cycle?: Cycle })[];
  failure?: { category: string; stage: string };
};
async function run() {
  const checks: Check[] = [];
  async function check(name: string, action: (record: (cycle?: Cycle) => Promise<void>) => Promise<void>) {
    const observations: (Snapshot & { cycle?: Cycle })[] = [];
    let failure: Check['failure'];
    try {
      await action(async (cycle) => {
        observations.push({ ...(await probe.cameraProbeSnapshot()), ...(cycle ? { cycle } : {}) });
      });
    } catch (error) {
      failure = { category: failureCategory(error), stage: name };
    } finally {
      observations.push(await probe.cameraProbeSnapshot());
      afterScan = undefined;
      for (const entry of (await probe.cameraProbeSnapshot()).entries) {
        if (entry.waiting) await probe.cameraProbeRelease(entry.id);
      }
      await waitFor(
        () => probe.cameraProbeSnapshot(),
        (value) => value.entries.every((entry) => !entry.waiting),
      );
      for (const entry of (await probe.cameraProbeSnapshot()).entries) {
        if (entry.detachedByProbe) await probe.cameraProbeReattach(entry.id);
      }
      surfaces = [];
      await renderSurfaces([]);
      await probe.cameraProbeReset();
    }
    checks.push({ name, passed: !failure, observations, ...(failure ? { failure } : {}) });
  }

  await check('scanner modal opens while its Activity is unfocused and active', async (record) => {
    const opened = await open();
    const snapshot = await probe.cameraProbeSnapshot();
    expect(snapshot.activityState === 'RESUMED' && !snapshot.activityFocused && AppState.currentState === 'active');
    expect((await state(opened.id)).focused);
    await probe.cameraProbeScan(opened.id);
    await waitFor(
      async () => scans.get(opened.surface) || 0,
      (count) => count === 1,
    );
    await record();
  });

  await check('owning window cover releases bound use cases and reaches CLOSED', async (record) => {
    const opened = await open();
    await record();
    await probe.cameraProbeCover();
    await waitFor(
      () => state(opened.id),
      (entry) => !entry.bound && entry.state === 'CLOSED',
    );
    const covered = await probe.cameraProbeSnapshot();
    expect(covered.activityState === 'RESUMED' && AppState.currentState === 'active');
    const retired = await state(opened.id);
    await probe.cameraProbeScan(opened.id);
    expect((await state(opened.id)).barcodes === retired.barcodes);
    await record();
    await probe.cameraProbeUncover();
    await waitFor(
      () => probe.cameraProbeSnapshot(),
      (value) => value.entries.some((entry) => entry.id !== opened.id && entry.bound && entry.state === 'OPEN'),
    );
    await record();
  });

  await check('ancestor visibility loss releases the actual camera', async (record) => {
    const opened = await open();
    await record();
    await probe.cameraProbeVisibility(opened.id, false);
    await waitFor(
      () => state(opened.id),
      (entry) => !entry.bound && entry.state === 'CLOSED',
    );
    await record();
    await probe.cameraProbeVisibility(opened.id, true);
    await waitFor(
      () => probe.cameraProbeSnapshot(),
      (value) => value.entries.some((entry) => entry.id !== opened.id && entry.bound && entry.state === 'OPEN'),
    );
  });

  await check('first-create held body resumes live and opens the real camera', async (record) => {
    await probe.cameraProbeArm();
    const opened = await mount();
    await waitFor(
      () => state(opened.id),
      (entry) => entry.waiting,
    );
    expect((await state(opened.id)).attempts === 0);
    await record();
    await probe.cameraProbeRelease(opened.id);
    await waitFor(
      () => state(opened.id),
      (entry) => entry.bound && entry.state === 'OPEN' && entry.ready > 0,
    );
    await record();
  });

  for (const outcome of ['live', 'loss', 'close', 'detach', 'pause'] as const) {
    await check(`post-await ${outcome} continuation retains its original admission`, async (record) => {
      const opened = await open();
      const before = await state(opened.id);
      await probe.cameraProbeArm();
      changedRatio.add(opened.surface);
      await renderSurfaces(surfaces);
      await waitFor(
        () => state(opened.id),
        (entry) => entry.waiting,
      );
      const held = await state(opened.id);
      expect(held.binds === before.binds && held.awaitedRatio === 'FOUR_THREE');
      await record();
      if (outcome === 'loss') {
        await probe.cameraProbeCover();
        await waitFor(
          () => state(opened.id),
          (entry) => !entry.focused,
        );
      }
      if (outcome === 'close' || outcome === 'detach') {
        if (outcome === 'close') await close(opened.surface);
        else await probe.cameraProbeDetach(opened.id);
        await waitFor(
          () => state(opened.id),
          (entry) => !entry.attached,
        );
      }
      if (outcome === 'pause') await probe.cameraProbePause(opened.id);
      await probe.cameraProbeRelease(opened.id);
      await waitFor(
        () => state(opened.id),
        (entry) => !entry.waiting,
      );
      if (outcome === 'live') {
        await waitFor(
          () => state(opened.id),
          (entry) => entry.binds > before.binds && entry.bound && entry.state === 'OPEN',
        );
      } else {
        const retired = await state(opened.id);
        expect(
          retired.attempts === before.attempts &&
            retired.binds === before.binds &&
            retired.ready === before.ready &&
            !retired.bound,
        );
        await waitFor(
          () => state(opened.id),
          (entry) => !entry.bound && entry.state === 'CLOSED',
        );
      }
      await record();
    });
  }

  await check('superseded pending owner and its later teardown preserve replacement OPEN', async (record) => {
    const first = await open();
    const before = await state(first.id);
    await probe.cameraProbeArm();
    changedRatio.add(first.surface);
    await renderSurfaces(surfaces);
    await waitFor(
      () => state(first.id),
      (entry) => entry.waiting,
    );
    expect((await state(first.id)).awaitedRatio === 'FOUR_THREE');
    const second = await open();
    await record();
    await close(first.surface);
    await waitFor(
      () => state(first.id),
      (entry) => !entry.attached,
    );
    await probe.cameraProbeRelease(first.id);
    await waitFor(
      () => state(first.id),
      (entry) => !entry.waiting,
    );
    await probe.cameraProbeRetire(first.id);
    await pause(300);
    const retired = await state(first.id);
    const replacement = await state(second.id);
    expect(
      !retired.bound &&
        retired.attempts === before.attempts &&
        retired.binds === before.binds &&
        retired.ready === before.ready,
    );
    expect(replacement.bound && replacement.state === 'OPEN');
    await record();
  });

  await check('late teardown and barcode delivery from an opened owner preserve replacement OPEN', async (record) => {
    const first = await open();
    const before = await state(first.id);
    const second = await open();
    await close(first.surface);
    await probe.cameraProbeRetire(first.id);
    await probe.cameraProbeScan(first.id);
    await pause(300);
    const replacement = await state(second.id);
    expect(replacement.bound && replacement.state === 'OPEN');
    const retired = await state(first.id);
    expect(retired.ready === before.ready && retired.barcodes === before.barcodes);
    await record();
  });

  for (const complete of [false, true]) {
    await check(
      `quick native focus cycle before JS delivery keeps ${complete ? 'completed' : 'live'} old owner revoked`,
      async (record) => {
        const opened = await open();
        let cycle: Promise<Cycle> | undefined;
        if (complete) {
          completed.add(opened.surface);
          afterScan = () => {
            cycle = probe.cameraProbeCycle(opened.id);
            stallJavaScript();
          };
          await probe.cameraProbeScan(opened.id);
          await waitFor(
            async () => cycle,
            (value) => value !== undefined,
          );
          afterScan = undefined;
        } else {
          cycle = probe.cameraProbeCycle(opened.id);
          stallJavaScript();
        }
        const result = await cycle!;
        await record(result);
        expect(
          result.attachedAtStart &&
            result.attachedAtReturn &&
            result.lost &&
            result.focused &&
            !result.bound &&
            result.binds === 1,
        );
        await waitFor(
          () => state(opened.id),
          (entry) => !entry.bound && entry.state === 'CLOSED',
        );
        if (complete) {
          await pause(300);
          expect(!(await probe.cameraProbeSnapshot()).entries.some((entry) => entry.bound));
          expect(scans.get(opened.surface) === 1);
        } else {
          await waitFor(
            () => probe.cameraProbeSnapshot(),
            (value) => value.entries.some((entry) => entry.id !== opened.id && entry.bound && entry.state === 'OPEN'),
          );
        }
        await record();
      },
    );
  }
  await apiClient.post('/report', { checks });
  return checks;
}

function CameraProbe() {
  const [owners, setOwners] = useState<number[]>([]);
  const [status, setStatus] = useState('Camera native probe running');
  const committed = useRef<(() => void) | undefined>(undefined);
  useLayoutEffect(() => {
    committed.current?.();
    committed.current = undefined;
  }, [owners]);
  useEffect(() => {
    renderSurfaces = (values) =>
      new Promise<void>((resolve) => {
        committed.current = resolve;
        setOwners([...values]);
      });
    run()
      .then((checks) => setStatus(checks.every((check) => check.passed) ? 'CAMERA_PROBE_PASS' : 'CAMERA_PROBE_FAIL'))
      .catch(() => setStatus('CAMERA_PROBE_REPORT_FAILED'));
  }, []);
  return (
    <CameraAccessContext.Provider value={access}>
      <Text>{status}</Text>
      {owners.map((surface) => (
        <Scanner key={surface} surface={surface} />
      ))}
    </CameraAccessContext.Provider>
  );
}

registerRootComponent(CameraProbe);
