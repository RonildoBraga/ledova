import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createAndroidTestPackages } from '../android-test-packages.mjs';

const packages = ['org.example.ledova.scanner.test', 'org.example.ledova.releaseprobe.test'];

for (const name of packages) {
  for (const stage of ['install', 'instrumentation', 'cancelled instrumentation']) {
    test(`${name} is removed after ${stage} fails`, async () => {
      const calls = [];
      const reports = [];
      const failure = new Error(stage);
      const cancellation = new globalThis.AbortController();
      const owned = createAndroidTestPackages(
        (args) => {
          assert.equal(cancellation.signal.aborted, stage === 'cancelled instrumentation');
          calls.push(args);
          return args[0] === 'uninstall' ? 'Success\n' : 'package:/synthetic/test.apk\n';
        },
        (...args) => reports.push(args),
      );
      let observed;
      try {
        await owned.install(name, async () => {
          if (stage === 'install') throw failure;
        });
        if (stage === 'cancelled instrumentation') {
          cancellation.abort(failure);
          cancellation.signal.throwIfAborted();
        }
        throw failure;
      } catch (error) {
        observed = error;
      } finally {
        assert.deepEqual(owned.cleanup(), []);
      }
      assert.equal(observed, failure);
      assert.deepEqual(calls, [
        ['shell', 'pm', 'path', name],
        ['uninstall', name],
      ]);
      assert.deepEqual(reports, [[name, 'Success\n']]);
      assert.deepEqual(owned.cleanup(), []);
      assert.equal(calls.length, 2);
    });
  }
}

test('successful explicit removal is forgotten while another owned package is cleaned', async () => {
  const calls = [];
  const owned = createAndroidTestPackages(
    (args) => {
      calls.push(args);
      return 'present';
    },
    () => {},
  );
  for (const name of packages) await owned.install(name, async () => {});
  owned.forget(packages[0]);
  assert.deepEqual(owned.cleanup(), []);
  assert.deepEqual(calls, [
    ['shell', 'pm', 'path', packages[1]],
    ['uninstall', packages[1]],
  ]);
});

test('cleanup failure is retained and does not prevent removal of the other owned package', async () => {
  const calls = [];
  const failure = new Error('synthetic uninstall failure');
  const owned = createAndroidTestPackages(
    (args) => {
      calls.push(args);
      if (args[0] === 'uninstall' && args[1] === packages[0]) throw failure;
      return 'present';
    },
    () => {},
  );
  for (const name of packages) await owned.install(name, async () => {});
  assert.deepEqual(owned.cleanup(), [failure]);
  assert.deepEqual(calls.at(-1), ['uninstall', packages[1]]);
});

test('an absent package is reported without uninstalling it', async () => {
  const calls = [];
  const reports = [];
  const owned = createAndroidTestPackages(
    (args) => {
      calls.push(args);
      return '';
    },
    (...args) => reports.push(args),
  );
  await owned.install(packages[0], async () => {});
  assert.deepEqual(owned.cleanup(), []);
  assert.deepEqual(calls, [['shell', 'pm', 'path', packages[0]]]);
  assert.deepEqual(reports, [[packages[0], 'Package not installed.\n']]);
});

test('unknown application packages cannot be installed through the owned test tracker', async () => {
  const calls = [];
  const owned = createAndroidTestPackages(
    (args) => calls.push(args),
    () => {},
  );
  let installed = false;
  await assert.rejects(
    owned.install('org.example.ledova', async () => {
      installed = true;
    }),
    /two scanner instrumentation packages/,
  );
  assert.equal(installed, false);
  assert.deepEqual(owned.cleanup(), []);
  assert.deepEqual(calls, []);
});
