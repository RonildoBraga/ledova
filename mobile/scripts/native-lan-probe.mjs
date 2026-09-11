import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { isIPv4 } from 'node:net';
import { createHash, randomUUID } from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { installLANTestTarget } from './ios-lan-target.mjs';

const mobile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = process.argv[2];
const host = process.env.EXPO_PUBLIC_DEV_API_HOST;
const device = process.env.IOS_SIMULATOR_UDID;
assert.equal(process.platform, 'darwin', 'This probe requires macOS and Xcode.');
assert.ok(output && path.isAbsolute(output), 'Supply a fresh absolute output directory.');
assert.ok(!fs.existsSync(output), 'Existing evidence must be preserved.');
assert.ok(path.relative(mobile, output).split(path.sep).includes('..'), 'Keep evidence outside mobile/.');
const [first, second] = String(host).split('.').map(Number);
assert.ok(
  isIPv4(String(host)) &&
    (first === 10 || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168)),
  'EXPO_PUBLIC_DEV_API_HOST must select one private IPv4 address.',
);
assert.ok(
  Object.values(os.networkInterfaces())
    .flat()
    .some((entry) => entry?.address === host && !entry.internal),
  'Select an address assigned to a local non-loopback interface.',
);
assert.match(String(device), /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i);
const config = JSON.parse(fs.readFileSync(path.join(mobile, 'app.json'), 'utf8')).expo;
const plist = createRequire(import.meta.url)('@expo/plist').default;
const ios = path.join(mobile, 'ios');
const saved = path.join(output, 'native-before');
const derived = path.join(output, 'DerivedData');
const nonce = randomUUID();
const counts = {};
const reports = [];
let stage = 'preflight';
let interrupted;
let child;
let movedOriginal = false;
let generated = false;
let attemptedInstall = false;
let failure;
const environment = {
  ...process.env,
  CI: '1',
  EXPO_NO_DOTENV: '1',
  EXPO_NO_TELEMETRY: '1',
  NODE_BINARY: process.execPath,
  EXPO_PUBLIC_API_URL: 'https://api.example.test',
  EXPO_PUBLIC_MARKETING_URL: 'https://example.test',
  FORCE_BUNDLING: '1',
  ENTRY_FILE: 'native-tests/NetworkProbeHost.tsx',
};
delete environment.SKIP_BUNDLING;

function sync(file, args, options = {}) {
  return execFileSync(file, args, { cwd: mobile, encoding: 'utf8', timeout: 30000, killSignal: 'SIGKILL', ...options });
}

function save(name, value) {
  fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2) + '\n');
}

function hash(filename) {
  return createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
}

function processes() {
  return sync('ps', ['-axo', 'pid=,ppid=,pgid=,stat='])
    .trim()
    .split('\n')
    .map((row) => {
      const [pid, parent, group, state] = row.trim().split(/\s+/);
      return { pid: Number(pid), parent: Number(parent), group: Number(group), state };
    });
}

async function stopOwned(ownedProcess) {
  if (!ownedProcess?.pid) return;
  const rows = processes();
  const owned = new Set([ownedProcess.pid]);
  let previous = 0;
  while (previous !== owned.size) {
    previous = owned.size;
    for (const row of rows) if (owned.has(row.parent)) owned.add(row.pid);
  }
  const groups = new Set([ownedProcess.pid, ...rows.filter((row) => owned.has(row.pid)).map((row) => row.group)]);
  assert.ok(!groups.has(rows.find((row) => row.pid === process.pid)?.group));
  const alive = () => processes().some((row) => groups.has(row.group) && !row.state.startsWith('Z'));
  for (const signal of ['SIGTERM', 'SIGKILL']) {
    for (const group of groups) {
      try {
        process.kill(-group, signal);
      } catch (error) {
        if (error.code !== 'ESRCH') throw error;
      }
    }
    const deadline = Date.now() + 2000;
    while (alive() && Date.now() < deadline) await delay(50);
    if (!alive()) return;
  }
  throw new Error('An owned native process group did not stop.');
}

const handlers = Object.fromEntries(
  ['SIGINT', 'SIGTERM'].map((signal) => [
    signal,
    () => {
      interrupted = signal;
    },
  ]),
);
for (const [signal, handler] of Object.entries(handlers)) process.on(signal, handler);

async function command(file, args, name, cwd = mobile) {
  assert.ok(!interrupted, 'The probe was interrupted.');
  stage = name;
  console.log(name);
  const descriptor = fs.openSync(path.join(output, name + '.log'), 'w');
  const started = Date.now();
  const deadline = started + 45 * 60 * 1000;
  let exited = false;
  let code;
  let signal;
  let spawnError;
  try {
    child = spawn(file, args, { cwd, env: environment, detached: true, stdio: ['ignore', descriptor, descriptor] });
    const closed = new Promise((resolve) => child.once('close', resolve));
    child.once('error', (error) => {
      spawnError = error;
    });
    child.once('exit', (value, reason) => {
      exited = true;
      code = value;
      signal = reason;
    });
    while (!exited && !spawnError && !interrupted && Date.now() < deadline) await delay(100);
    if (!exited && !spawnError) await stopOwned(child);
    await Promise.race([
      closed,
      delay(2000).then(() => {
        throw new Error('Native child was not reaped.');
      }),
    ]);
    assert.ok(!interrupted, 'The probe was interrupted.');
    assert.ok(Date.now() < deadline, `${name} exceeded its 45-minute deadline.`);
    if (spawnError) throw spawnError;
    const result = { code, signal, seconds: (Date.now() - started) / 1000 };
    save(name + '-command.json', result);
    return result;
  } finally {
    if (child && child.exitCode === null && child.signalCode === null) await stopOwned(child);
    child = undefined;
    fs.closeSync(descriptor);
  }
}

async function successful(file, args, name, cwd) {
  const result = await command(file, args, name, cwd);
  assert.equal(result.code, 0, `${name} failed; read its retained log.`);
}

const server = http.createServer((request, response) => {
  const run = request.headers['x-ledova-probe-run'];
  if (
    request.headers['x-ledova-probe'] !== nonce ||
    request.method !== 'POST' ||
    !['/baseline', '/handler', '/host-control'].includes(request.url) ||
    typeof run !== 'string'
  ) {
    response.writeHead(404).end();
    return;
  }
  let body = '';
  request.on('data', (chunk) => {
    body += chunk;
    if (body.length > 4096) request.destroy();
  });
  request.on('end', () => {
    if (body !== 'synthetic-local-network-control') {
      response.writeHead(400).end();
      return;
    }
    counts[run] ??= {};
    counts[run][request.url] = (counts[run][request.url] ?? 0) + 1;
    save('server-counts.json', counts);
    response.writeHead(200, { 'Content-Type': 'text/plain' }).end('ledova-local-network-control');
  });
});

try {
  const devices = Object.values(
    JSON.parse(sync('xcrun', ['simctl', 'list', 'devices', 'available', '-j'])).devices,
  ).flat();
  assert.equal(devices.find((entry) => entry.udid === device)?.state, 'Booted', 'Boot the selected owned simulator.');
  const apps = JSON.parse(
    sync('plutil', ['-convert', 'json', '-o', '-', '--', '-'], {
      input: sync('xcrun', ['simctl', 'listapps', device]),
    }),
  );
  assert.equal(
    apps[config.ios.bundleIdentifier],
    undefined,
    'Use an owned simulator without an existing Ledova installation.',
  );
  fs.mkdirSync(output, { recursive: true });
  const filesystem = fs.statSync(mobile).dev;
  assert.equal(
    fs.statSync(output).dev,
    filesystem,
    'Keep the output on the checkout filesystem so the original iOS project can be restored atomically.',
  );
  if (fs.existsSync(ios)) {
    assert.ok(!fs.lstatSync(ios).isSymbolicLink(), 'Preserve the generated iOS project as a directory.');
    assert.equal(fs.statSync(ios).dev, filesystem, 'Keep the generated iOS project on the checkout filesystem.');
  }
  const tracked = sync('git', ['ls-files', '-z']).split('\0').filter(Boolean);
  const before = Object.fromEntries(tracked.map((name) => [name, hash(path.join(mobile, name))]));
  save('source-before.json', before);
  save('environment.json', {
    head: sync('git', ['rev-parse', 'HEAD']).trim(),
    xcode: sync('xcodebuild', ['-version']).trim(),
    sdk: sync('xcrun', ['--sdk', 'iphonesimulator', '--show-sdk-version']).trim(),
    device: devices.find((entry) => entry.udid === device),
    scope: 'Simulator handler policy and reachability; physical local-network privacy is not exercised.',
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, host, resolve);
  });
  const baseURL = `http://${host}:${server.address().port}`;
  const hostControl = await globalThis.fetch(baseURL + '/host-control', {
    method: 'POST',
    body: 'synthetic-local-network-control',
    signal: globalThis.AbortSignal.timeout(8000),
    headers: { 'X-Ledova-Probe': nonce, 'X-Ledova-Probe-Run': 'host-control' },
  });
  assert.equal(hostControl.status, 200);
  assert.equal(await hostControl.text(), 'ledova-local-network-control');
  if (fs.existsSync(ios)) {
    fs.renameSync(ios, saved);
    movedOriginal = true;
  }
  generated = true;
  await successful(
    path.join(mobile, 'node_modules/.bin/expo'),
    ['prebuild', '--clean', '--no-install', '--platform', 'ios'],
    'prebuild',
  );
  save(
    'test-target.json',
    installLANTestTarget(ios, config.name, path.join(mobile, 'native-tests/ios/LedovaNetworkTests.m')),
  );
  await successful('pod', ['install'], 'pods', ios);
  const sourceRoot = path.join(ios, config.name);
  const handlerFile = path.join(sourceRoot, 'LedovaHTTPRequestHandler.m');
  const originalHandler = fs.readFileSync(handlerFile, 'utf8');
  assert.equal(
    originalHandler,
    fs.readFileSync(path.join(mobile, 'plugins/native/LedovaHTTPRequestHandler.m'), 'utf8'),
  );
  const plists = Object.fromEntries(
    ['Info.plist', 'Info-Debug.plist'].map((name) => [
      name,
      plist.parse(fs.readFileSync(path.join(sourceRoot, name), 'utf8')),
    ]),
  );
  assert.ok(plists['Info-Debug.plist'].LedovaDevelopmentHTTPHosts.includes(host));
  assert.equal(plists['Info-Debug.plist'].NSAppTransportSecurity.NSAllowsLocalNetworking, true);
  assert.equal(plists['Info.plist'].NSAppTransportSecurity.NSAllowsLocalNetworking, false);
  assert.equal(plists['Info.plist'].LedovaDevelopmentHTTPHosts, undefined);
  const delegateFile = path.join(sourceRoot, 'AppDelegate.swift');
  const delegate = fs.readFileSync(delegateFile, 'utf8');
  const bundle = /#if DEBUG\n {4}return RCTBundleURLProvider[^\n]+\n#else\n( {4}return Bundle.main.url[^\n]+)\n#endif/g;
  assert.equal([...delegate.matchAll(bundle)].length, 1, 'Expected one generated bundle URL override.');
  fs.writeFileSync(delegateFile, delegate.replace(bundle, '$1'));
  for (const [mode, label, bypass] of [
    ['configured-debug', 'configured-debug', false],
    ['unconfigured-debug', 'unconfigured-bypass-control', true],
    ['unconfigured-debug', 'unconfigured-debug', false],
    ['release', 'release', false],
  ]) {
    const run = randomUUID();
    const configuration = mode === 'release' ? 'Release' : 'Debug';
    for (const [filename, original] of Object.entries(plists)) {
      const contents = globalThis.structuredClone(original);
      if (filename === 'Info-Debug.plist' && mode === 'unconfigured-debug') {
        contents.LedovaDevelopmentHTTPHosts = contents.LedovaDevelopmentHTTPHosts.filter((entry) => entry !== host);
      }
      contents.LedovaNetworkProbe = { baseURL, nonce, run, mode };
      fs.writeFileSync(path.join(sourceRoot, filename), plist.build(contents));
    }
    const guard = 'if ([hosts containsObject:request.URL.host.lowercaseString])';
    assert.equal(originalHandler.split(guard).length, 2);
    fs.writeFileSync(handlerFile, bypass ? originalHandler.replace(guard, 'if (YES)') : originalHandler);
    attemptedInstall = true;
    const result = await command(
      'xcodebuild',
      [
        '-workspace',
        path.join(ios, `${config.name}.xcworkspace`),
        '-scheme',
        config.name,
        '-configuration',
        configuration,
        '-sdk',
        'iphonesimulator',
        '-destination',
        `id=${device}`,
        '-derivedDataPath',
        derived,
        '-resultBundlePath',
        path.join(output, `${label}.xcresult`),
        '-jobs',
        '2',
        '-parallel-testing-enabled',
        'NO',
        'CODE_SIGNING_ALLOWED=YES',
        'CODE_SIGN_IDENTITY=-',
        'test',
        '-only-testing:LedovaNetworkTests',
      ],
      label,
    );
    const app = path.join(derived, 'Build/Products', `${configuration}-iphonesimulator`, `${config.name}.app`);
    const container = sync('xcrun', [
      'simctl',
      'get_app_container',
      device,
      config.ios.bundleIdentifier,
      'data',
    ]).trim();
    const observed = JSON.parse(
      fs.readFileSync(path.join(container, 'Documents/ledova-debug-network-result.json'), 'utf8'),
    );
    save(`${label}-observed.json`, observed);
    assert.equal(observed.run, run, 'Reject a native result left by an earlier run.');
    assert.equal(observed.mode, mode);
    const built = JSON.parse(sync('plutil', ['-convert', 'json', '-o', '-', path.join(app, 'Info.plist')]));
    save(`${label}-plist.json`, built);
    const binaries = {};
    for (const name of [config.name, `${config.name}.debug.dylib`]) {
      const binary = path.join(app, name);
      if (!fs.existsSync(binary)) continue;
      binaries[name] = { sha256: hash(binary), architectures: sync('xcrun', ['lipo', '-archs', binary]).trim() };
      fs.writeFileSync(
        path.join(output, `${label}-${name}-build-version.txt`),
        sync('xcrun', ['vtool', '-show-build', binary]),
      );
    }
    const report = {
      mode,
      label,
      ...result,
      binaries,
      handlerSHA256: hash(handlerFile),
      handlerUnchanged: !bypass && fs.readFileSync(handlerFile, 'utf8') === originalHandler,
      observed,
      requests: counts[run] ?? {},
    };
    reports.push(report);
    save(`${label}-result.json`, report);
    assert.equal(result.code, bypass ? 65 : 0, `${label} has an unexpected build/test result.`);
    assert.equal(observed.actual.handler, 'LedovaHTTPRequestHandler');
    assert.equal(observed.actual.priority, 1);
    const expectedActual = bypass || mode === 'configured-debug' ? 1 : 0;
    assert.equal(counts[run]?.['/handler'] ?? 0, expectedActual);
    assert.equal(counts[run]?.['/baseline'] ?? 0, observed.baseline.status === 200 ? 1 : 0);
    if (bypass) {
      assert.equal(observed.actual.status, 200);
      assert.equal(observed.actual.body, 'ledova-local-network-control');
      assert.equal(observed.actual.errorDomain, '');
      assert.equal(observed.baseline.status, 200);
      assert.match(fs.readFileSync(path.join(output, `${label}.log`), 'utf8'), /Executed 1 test, with 4 failures/);
    }
  }
  fs.writeFileSync(handlerFile, originalHandler);
  const after = Object.fromEntries(tracked.map((name) => [name, hash(path.join(mobile, name))]));
  save('source-after.json', after);
  assert.deepEqual(after, before, 'Tracked mobile source changed during the probe.');
} catch (error) {
  failure = { stage, message: error.message };
  process.exitCode = 1;
} finally {
  const cleanupErrors = [];
  let commandStopped = false;
  async function cleanup(name, operation) {
    try {
      await operation();
    } catch (error) {
      cleanupErrors.push({ name, message: error.message });
    }
  }
  await cleanup('native-command', async () => {
    await stopOwned(child);
    commandStopped = true;
  });
  await cleanup('server', async () => {
    server.closeAllConnections();
    if (server.listening)
      await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  });
  if (commandStopped) {
    if (attemptedInstall)
      await cleanup('test-app', () => sync('xcrun', ['simctl', 'uninstall', device, config.ios.bundleIdentifier]));
    await cleanup('generated-project', () => {
      if (generated) fs.rmSync(ios, { recursive: true, force: true });
      if (movedOriginal) fs.renameSync(saved, ios);
    });
  } else {
    cleanupErrors.push({
      name: 'generated-project',
      message: 'Restoration deferred while the owned native command remains active.',
    });
  }
  for (const [signal, handler] of Object.entries(handlers)) process.removeListener(signal, handler);
  if (cleanupErrors.length) process.exitCode = 1;
  if (fs.existsSync(output))
    save('result.json', { success: !failure && cleanupErrors.length === 0, failure, cleanupErrors, reports });
  if (failure || cleanupErrors.length) console.error('Native LAN probe failed; retained results identify the stage.');
  else console.log('Configured Debug success, unconfigured Debug refusal, bypass failure and Release refusal passed.');
}
