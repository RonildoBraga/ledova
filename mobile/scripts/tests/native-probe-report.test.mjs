import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import https from 'node:https';
import vm from 'node:vm';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { setTimeout, clearTimeout } from 'node:timers';
import { test } from 'node:test';

const mobile = path.resolve(import.meta.dirname, '../..');

function report(phase) {
  return {
    checks: [
      ...Array.from({ length: 12 }, (_, index) => ({ name: `synthetic control ${index}`, passed: true })),
      { name: 'native 307 refusal', passed: phase === 'green' },
      { name: 'native 308 refusal', passed: phase === 'green' },
    ],
    counts: {
      redirectTarget: phase === 'red' ? 2 : 0,
      redirectBody: phase === 'red' ? 2 : 0,
      redirectBearer: 0,
      direct: 1,
      targetControl: 1,
      upload: 1,
      download: 1,
      stream: 1,
      cancelled: 1,
      http: 0,
      untrusted: 0,
    },
  };
}

async function phaseFixture(context, greenCommand, { resetFailure, screenshot } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-phase-report-'));
  context.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const source = fs.readFileSync(path.join(mobile, 'scripts/native-smoke.mjs'), 'utf8');
  const start = source.indexOf('  for (const [name, source] of [');
  const end = source.indexOf("  console.log('Native Release probe passed", start);
  assert.ok(start > 0 && end > start);
  const serverReport = path.join(directory, 'server/result.json');
  fs.mkdirSync(path.dirname(serverReport));
  const phases = [];
  let resets = 0;
  const fixture = {
    assert,
    fs,
    path,
    directory,
    platform: 'android',
    bad: 'synthetic red source',
    correct: 'synthetic green source',
    nativeSource: path.join(directory, 'native-source'),
    endpoints: { apiUrl: 'https://localhost.invalid' },
    environment: {},
    ca: 'synthetic CA',
    adb: 'synthetic adb',
    adbArgs: [],
    appPath: 'synthetic apk',
    markStage() {},
    async localRequest(url, route) {
      assert.equal(route, '/reset');
      resets++;
      if (resets === 2 && resetFailure) throw resetFailure;
      fs.rmSync(serverReport, { force: true });
    },
    async build() {},
    archiveAndroidArtifact() {},
    async launch() {},
    async command(file, args, name) {
      const phase = name === 'scanner-release-red' ? 'red' : 'green';
      phases.push(phase);
      if (phase === 'green') await greenCommand({ directory, serverReport });
      else {
        fs.writeFileSync(serverReport, JSON.stringify(report('red')));
        fs.writeFileSync(path.join(directory, `${name}.log`), 'OK (1 test)');
      }
    },
    collectScannerEvidence() {},
    async waitFor(filename) {
      return JSON.parse(fs.readFileSync(filename, 'utf8'));
    },
    async delay() {},
    async screenshot() {
      await screenshot?.({ serverReport });
    },
  };
  return {
    directory,
    phases,
    run: () =>
      vm.compileFunction(
        `return (async () => { ${source.slice(start, end)} })()`,
        Object.keys(fixture),
      )(...Object.values(fixture)),
  };
}

test('a failed green instrumentation assertion preserves its report separately from red', async (context) => {
  const failed = report('green');
  failed.checks.push({
    name: 'Android scanner window bridge',
    passed: false,
    failure: { category: 'assertion', stage: 'method-native-function' },
  });
  const fixture = await phaseFixture(context, ({ directory, serverReport }) => {
    fs.writeFileSync(serverReport, JSON.stringify(failed));
    fs.writeFileSync(path.join(directory, 'scanner-release-green.log'), 'FAILURES!!!');
  });
  await assert.rejects(fixture.run(), /OK/);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(fixture.directory, 'native-green.json'), 'utf8')), failed);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(fixture.directory, 'native-red.json'), 'utf8')), report('red'));
  assert.deepEqual(fixture.phases, ['red', 'green']);
});

test('a failed instrumentation command preserves the posted report and original failure', async (context) => {
  const failure = new Error('Synthetic instrumentation command failed.');
  const fixture = await phaseFixture(context, ({ serverReport }) => {
    fs.writeFileSync(serverReport, JSON.stringify(report('green')));
    throw failure;
  });
  await assert.rejects(fixture.run(), (error) => error === failure);
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(fixture.directory, 'native-green.json'), 'utf8')),
    report('green'),
  );
});

test('a missing green report cannot be replaced with the prior red report', async (context) => {
  const failure = new Error('Synthetic command failed before reporting.');
  const fixture = await phaseFixture(context, () => {
    throw failure;
  });
  await assert.rejects(fixture.run(), (error) => error === failure);
  assert.equal(fs.existsSync(path.join(fixture.directory, 'native-green.json')), false);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(fixture.directory, 'native-red.json'), 'utf8')), report('red'));
});

test('a failed green reset cannot label the retained server red report as green', async (context) => {
  const failure = new Error('Synthetic reset failed.');
  const fixture = await phaseFixture(context, () => assert.fail('Green instrumentation must not run.'), {
    resetFailure: failure,
  });
  await assert.rejects(fixture.run(), (error) => error === failure);
  assert.equal(fs.existsSync(path.join(fixture.directory, 'native-green.json')), false);
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(fixture.directory, 'server/result.json'), 'utf8')),
    report('red'),
  );
  assert.deepEqual(fixture.phases, ['red']);
});

test('successful red and green phases retain both reports and their existing assertions', async (context) => {
  const fixture = await phaseFixture(context, ({ directory, serverReport }) => {
    fs.writeFileSync(serverReport, JSON.stringify(report('green')));
    fs.writeFileSync(path.join(directory, 'scanner-release-green.log'), 'OK (1 test)');
  });
  await fixture.run();
  for (const phase of ['red', 'green']) {
    assert.deepEqual(
      JSON.parse(fs.readFileSync(path.join(fixture.directory, `native-${phase}.json`), 'utf8')),
      report(phase),
    );
  }
  assert.deepEqual(fixture.phases, ['red', 'green']);
});

test('a later server report cannot replace the snapshot actually evaluated by a phase', async (context) => {
  const fixture = await phaseFixture(
    context,
    ({ directory, serverReport }) => {
      fs.writeFileSync(serverReport, JSON.stringify(report('green')));
      fs.writeFileSync(path.join(directory, 'scanner-release-green.log'), 'OK (1 test)');
    },
    {
      screenshot({ serverReport }) {
        fs.writeFileSync(serverReport, JSON.stringify({ checks: [], counts: {} }));
      },
    },
  );
  await fixture.run();
  for (const phase of ['red', 'green']) {
    assert.deepEqual(
      JSON.parse(fs.readFileSync(path.join(fixture.directory, `native-${phase}.json`), 'utf8')),
      report(phase),
    );
  }
});

async function serverFixture(context) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-server-report-'));
  const child = spawn(process.execPath, [path.join(mobile, 'scripts/native-probe-server.mjs'), directory, 'ios'], {
    stdio: 'ignore',
  });
  const closed = once(child, 'close');
  context.after(async () => {
    const forced = setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    child.kill('SIGTERM');
    try {
      await closed;
    } finally {
      clearTimeout(forced);
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });
  const config = path.join(directory, 'config.json');
  const deadline = Date.now() + 15000;
  while (!fs.existsSync(config) && child.exitCode === null && Date.now() < deadline) await delay(20);
  assert.ok(fs.existsSync(config), 'Synthetic report server must become ready.');
  const { apiUrl } = JSON.parse(fs.readFileSync(config, 'utf8'));
  const ca = fs.readFileSync(path.join(directory, 'ca.pem'));
  return {
    result: () => JSON.parse(fs.readFileSync(path.join(directory, 'result.json'), 'utf8')),
    async post(payload) {
      return await new Promise((resolve, reject) => {
        const request = https.request(`${apiUrl}/report`, { method: 'POST', ca, timeout: 2000 }, (response) => {
          response.resume();
          response.on('end', () => resolve(response.statusCode));
        });
        request.on('timeout', () => request.destroy(new Error('Synthetic report request timed out.')));
        request.on('error', reject);
        request.end(JSON.stringify(payload));
      });
    },
  };
}

test('the report server retains only allowlisted failure category and stage values', async (context) => {
  const server = await serverFixture(context);
  const check = {
    name: 'Android scanner window bridge',
    passed: false,
    failure: {
      category: 'assertion',
      stage: 'method-native-function',
      message: 'synthetic-secret',
      provider: 'synthetic-secret',
      stack: 'synthetic-secret',
      credential: { value: 'synthetic-secret' },
    },
  };
  assert.equal(await server.post({ checks: [check], ignored: 'synthetic-secret' }), 200);
  assert.deepEqual(server.result().checks, [
    { name: check.name, passed: false, failure: { category: 'assertion', stage: 'method-native-function' } },
  ]);
  assert.ok(!JSON.stringify(server.result()).includes('synthetic-secret'));
  const controls = [
    { name: 'native 307 refusal', passed: false, failure: { category: 'assertion', stage: 'check' } },
    { name: 'native 308 refusal', passed: false, failure: { category: 'assertion', stage: 'check' } },
    { name: 'native entropy and mnemonic', passed: true },
    {
      name: 'legacy session migration and ordinary storage',
      passed: false,
      failure: { category: 'native-function', stage: 'initial-sign-out' },
    },
    { name: 'sign-out removes the native session', passed: false },
  ];
  assert.equal(await server.post({ checks: controls }), 200);
  assert.deepEqual(server.result().checks, controls);
  for (const category of ['native-keychain', 'unknown']) {
    const control = {
      name: 'sign-out removes the native session',
      passed: false,
      failure: { category, stage: 'signed-out-session-read' },
    };
    assert.equal(await server.post({ checks: [control] }), 200);
    assert.deepEqual(server.result().checks, [control]);
  }
  for (const failure of [
    { category: 'synthetic-secret', stage: 'check' },
    { category: 'unknown', stage: 'synthetic-secret' },
    { category: null, stage: ['check'] },
    'synthetic-secret',
  ]) {
    assert.equal(await server.post({ checks: [{ name: check.name, passed: false, failure }] }), 200);
    assert.deepEqual(server.result().checks, [{ name: check.name, passed: false }]);
    assert.ok(!JSON.stringify(server.result()).includes('synthetic-secret'));
  }
  assert.equal(await server.post({ checks: [{ ...check, passed: true }] }), 200);
  assert.deepEqual(server.result().checks, [{ name: check.name, passed: true }]);
});
