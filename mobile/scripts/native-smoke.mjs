import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import https from 'node:https';
import http from 'node:http';
import { fileURLToPath, URL } from 'node:url';
import { createHash } from 'node:crypto';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { setTimeout, clearTimeout } from 'node:timers';

const mobile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [platform, output] = process.argv.slice(2);
assert.ok(
  ['android', 'ios'].includes(platform) && output,
  'Use native-smoke.mjs android|ios ABSOLUTE_OUTPUT_DIRECTORY',
);
const directory = path.resolve(output);
assert.ok(!fs.existsSync(directory), 'Use a fresh output directory to preserve previous evidence.');
fs.mkdirSync(directory, { recursive: true });
const config = JSON.parse(fs.readFileSync(path.join(mobile, 'app.json'), 'utf8')).expo;
const device = platform === 'android' ? process.env.ANDROID_SERIAL : process.env.IOS_SIMULATOR_UDID;
assert.ok(device, 'Select the owned emulator or simulator explicitly.');
if (platform === 'android') assert.match(device, /^emulator-\d+$/);
const sdk = process.env.ANDROID_HOME;
const adb = sdk ? path.join(sdk, 'platform-tools', 'adb') : 'adb';
const adbArgs = ['-P', process.env.ANDROID_ADB_SERVER_PORT || '5037', '-s', device];
const baseEnvironment = {
  ...process.env,
  CI: '1',
  EXPO_NO_DOTENV: '1',
  EXPO_NO_TELEMETRY: '1',
  NODE_BINARY: process.execPath,
  CMAKE_BUILD_PARALLEL_LEVEL: '2',
  EXPO_PUBLIC_API_URL: 'https://api.example.test',
  EXPO_PUBLIC_MARKETING_URL: 'https://example.test',
};

const cancellation = new globalThis.AbortController();
const activeChildren = new Map();
const stoppingChildren = new Map();
const spawnFailures = new WeakMap();
let currentStage = 'initialization';
function markStage(name) {
  currentStage = name;
  console.log(name);
}
const signals = { SIGINT: 130, SIGTERM: 143 };
function interrupt(signal) {
  if (cancellation.signal.aborted) return;
  process.exitCode = signals[signal];
  cancellation.abort(new Error(`Native validation interrupted by ${signal}.`));
}
const signalHandlers = Object.fromEntries(Object.keys(signals).map((signal) => [signal, () => interrupt(signal)]));
for (const [signal, handler] of Object.entries(signalHandlers)) process.on(signal, handler);

function processTable() {
  return execFileSync('ps', ['-axo', 'pid=,ppid=,pgid=,stat='], {
    encoding: 'utf8',
    timeout: 15000,
    killSignal: 'SIGKILL',
  })
    .trim()
    .split('\n')
    .map((row) => {
      const [pid, parent, group, state] = row.trim().split(/\s+/);
      return { pid: Number(pid), parent: Number(parent), group: Number(group), state };
    });
}

function ownedSpawn(file, args, options) {
  cancellation.signal.throwIfAborted();
  const child = spawn(file, args, { ...options, detached: true });
  child.once('error', (error) => spawnFailures.set(child, error));
  activeChildren.set(child, new Promise((resolve) => child.once('close', resolve)));
  return child;
}

function stopOwned(child) {
  if (stoppingChildren.has(child)) return stoppingChildren.get(child);
  const stopping = (async () => {
    if (!child.pid) return;
    const rows = processTable();
    const owned = new Set([child.pid]);
    let previous = 0;
    while (previous !== owned.size) {
      previous = owned.size;
      for (const row of rows) if (owned.has(row.parent)) owned.add(row.pid);
    }
    const groups = new Set([child.pid, ...rows.filter((row) => owned.has(row.pid)).map((row) => row.group)]);
    assert.ok(!groups.has(rows.find((row) => row.pid === process.pid)?.group), 'Refusing to stop the runner group.');
    function remaining() {
      return processTable().some((row) => groups.has(row.group) && !row.state.startsWith('Z'));
    }
    function kill(signal) {
      for (const group of groups) {
        try {
          process.kill(-group, signal);
        } catch (error) {
          if (error.code !== 'ESRCH') throw error;
        }
      }
    }
    kill('SIGTERM');
    const graceful = Date.now() + 2000;
    while (remaining() && Date.now() < graceful) await delay(50);
    if (remaining()) kill('SIGKILL');
    const forced = Date.now() + 2000;
    while (remaining() && Date.now() < forced) await delay(50);
    assert.ok(!remaining(), 'An owned native process group did not stop.');
    await Promise.race([
      activeChildren.get(child),
      delay(2000, undefined, { ref: false }).then(() => {
        throw new Error('An owned child was not reaped.');
      }),
    ]);
  })();
  stoppingChildren.set(child, stopping);
  return stopping;
}

async function command(file, args, name, extraEnvironment = {}, cwd = mobile) {
  cancellation.signal.throwIfAborted();
  markStage(name);
  const log = fs.openSync(path.join(directory, `${name}.log`), 'w');
  let child;
  let timedOut = false;
  const milliseconds = (file === 'xcodebuild' ? 45 : 30) * 60 * 1000;
  try {
    await new Promise((resolve, reject) => {
      child = ownedSpawn(file, args, {
        cwd,
        env: { ...baseEnvironment, ...extraEnvironment },
        stdio: ['ignore', log, log],
      });
      const timeout = setTimeout(() => {
        timedOut = true;
        stopOwned(child).catch(reject);
      }, milliseconds);
      const abort = () => {
        stopOwned(child).catch(reject);
      };
      cancellation.signal.addEventListener('abort', abort, { once: true });
      child.once('error', (error) => {
        clearTimeout(timeout);
        cancellation.signal.removeEventListener('abort', abort);
        reject(error);
      });
      child.once('exit', (code, signal) => {
        clearTimeout(timeout);
        cancellation.signal.removeEventListener('abort', abort);
        if (timedOut) reject(new Error(`${name} timed out after ${milliseconds / 1000} seconds; read its log.`));
        else if (code === 0) resolve();
        else reject(new Error(`${name} failed (${signal ?? code}); read its log.`));
      });
    });
    cancellation.signal.throwIfAborted();
  } finally {
    try {
      if (child && (cancellation.signal.aborted || timedOut)) await stopOwned(child);
    } finally {
      if (child) activeChildren.delete(child);
      fs.closeSync(log);
    }
  }
}

async function waitFor(filename, milliseconds, child) {
  const deadline = Date.now() + milliseconds;
  while (!fs.existsSync(filename)) {
    cancellation.signal.throwIfAborted();
    if (child) {
      if (spawnFailures.has(child)) throw spawnFailures.get(child);
      assert.ok(
        child.exitCode === null && child.signalCode === null,
        `Probe server exited (${child.exitCode ?? child.signalCode}); read server.log.`,
      );
    }
    assert.ok(Date.now() < deadline, `Timed out waiting for ${path.basename(filename)}.`);
    await delay(250);
  }
  return JSON.parse(fs.readFileSync(filename, 'utf8'));
}

async function localRequest(url, route, ca) {
  const target = new URL(url);
  target.hostname = '127.0.0.1';
  target.pathname = route;
  return new Promise((resolve, reject) => {
    const client = target.protocol === 'http:' ? http : https;
    const request = client.get(target, { ca, timeout: 5000, signal: cancellation.signal }, (response) => {
      response.resume();
      response.on('end', () =>
        response.statusCode === 200 ? resolve() : reject(new Error('Probe server control failed.')),
      );
    });
    request.on('error', reject);
    request.on('timeout', () => request.destroy(new Error('Probe server control timed out.')));
  });
}

const derived = path.join(directory, 'DerivedData');
const appPath =
  platform === 'android'
    ? path.join(mobile, 'android/app/build/outputs/apk/release/app-release.apk')
    : path.join(derived, 'Build/Products/Release-iphonesimulator', `${config.name}.app`);

async function build(name, environment) {
  const temporary = path.join(directory, 'build-temporary', name);
  fs.mkdirSync(temporary, { recursive: true });
  const buildEnvironment = { ...environment, TMPDIR: temporary, TMP: temporary, TEMP: temporary };
  if (platform === 'android') {
    await command(
      './gradlew',
      [
        ':app:assembleRelease',
        '--no-daemon',
        '--max-workers=2',
        '-Dorg.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=1g',
        `-PreactNativeArchitectures=${process.env.NATIVE_ANDROID_ABIS || 'x86_64,arm64-v8a'}`,
      ],
      name,
      buildEnvironment,
      path.join(mobile, 'android'),
    );
  } else {
    await command(
      'xcodebuild',
      [
        '-workspace',
        `ios/${config.name}.xcworkspace`,
        '-scheme',
        config.name,
        '-configuration',
        'Release',
        '-sdk',
        'iphonesimulator',
        '-destination',
        `id=${device}`,
        '-derivedDataPath',
        derived,
        '-jobs',
        '2',
        'CODE_SIGNING_ALLOWED=YES',
        'CODE_SIGN_IDENTITY=-',
        'build',
      ],
      name,
      buildEnvironment,
    );
  }
}

async function launch(name) {
  if (platform === 'android') {
    await command(adb, [...adbArgs, 'install', '-r', appPath], `${name}-install`);
    await command(adb, [...adbArgs, 'shell', 'am', 'force-stop', config.android.package], `${name}-stop`);
    await command(
      adb,
      [...adbArgs, 'shell', 'am', 'start', '-W', '-n', `${config.android.package}/.MainActivity`],
      `${name}-launch`,
    );
  } else {
    await command(
      process.execPath,
      [
        path.join(mobile, 'scripts/check-ios-simulator-identity.mjs'),
        path.join(appPath, config.name),
        config.ios.bundleIdentifier,
        path.join(directory, `${name}-simulator-identity.json`),
      ],
      `${name}-simulator-identity`,
    );
    await command('xcrun', ['simctl', 'install', device, appPath], `${name}-install`);
    spawnSync('xcrun', ['simctl', 'terminate', device, config.ios.bundleIdentifier], {
      stdio: 'ignore',
      timeout: 10000,
      killSignal: 'SIGKILL',
    });
    await command('xcrun', ['simctl', 'launch', device, config.ios.bundleIdentifier], `${name}-launch`);
  }
}

async function screenshot(name) {
  if (platform === 'android') {
    fs.writeFileSync(
      path.join(directory, `${name}.png`),
      execFileSync(adb, [...adbArgs, 'exec-out', 'screencap', '-p'], { timeout: 10000, killSignal: 'SIGKILL' }),
    );
  } else {
    await command(
      'xcrun',
      ['simctl', 'io', device, 'screenshot', path.join(directory, `${name}.png`)],
      `${name}-screenshot`,
    );
  }
}

function checkAndroidArtifact(artifact) {
  const aapt = path.join(sdk, 'build-tools/36.0.0/aapt2');
  const resources = execFileSync(aapt, ['dump', 'resources', artifact], {
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
    timeout: 10000,
    killSignal: 'SIGKILL',
  });
  const manifest = execFileSync(aapt, ['dump', 'xmltree', artifact, '--file', 'AndroidManifest.xml'], {
    encoding: 'utf8',
    timeout: 10000,
    killSignal: 'SIGKILL',
  });
  assert.match(manifest, /usesCleartextTraffic\([^\n]+\)=false/);
  assert.doesNotMatch(manifest, /debuggable\([^\n]+\)=true/);
  fs.writeFileSync(path.join(directory, 'release-manifest.txt'), manifest);
  for (const resource of [
    'ledova_network_security_config',
    'secure_store_backup_rules',
    'secure_store_data_extraction_rules',
  ]) {
    const match = resources.match(new RegExp(`xml/${resource}\\n[^\\n]+\\(file\\) ([^ ]+)`));
    assert.ok(match, `Packaged ${resource} is missing.`);
    const xml = execFileSync(aapt, ['dump', 'xmltree', artifact, '--file', match[1]], {
      encoding: 'utf8',
      timeout: 10000,
      killSignal: 'SIGKILL',
    });
    fs.writeFileSync(path.join(directory, `${resource}.txt`), xml);
    if (resource === 'ledova_network_security_config') {
      assert.match(xml, /cleartextTrafficPermitted=false/);
      assert.doesNotMatch(xml, /domain-config|trust-anchors/);
    } else {
      assert.match(xml, /E: exclude/);
      assert.match(xml, /path="SecureStore"/);
    }
  }
  execFileSync(path.join(sdk, 'build-tools/36.0.0/zipalign'), ['-c', '-P', '16', '4', artifact], {
    timeout: 10000,
    killSignal: 'SIGKILL',
  });
}

const serverLog = fs.openSync(path.join(directory, 'server.log'), 'w');
markStage('probe-server-start');
const server = ownedSpawn(
  process.execPath,
  [path.join(mobile, 'scripts/native-probe-server.mjs'), path.join(directory, 'server'), platform],
  { stdio: ['ignore', serverLog, serverLog] },
);
const restored = new Map();
function preserve(filename) {
  restored.set(filename, fs.existsSync(filename) ? fs.readFileSync(filename) : null);
}
let failure;
try {
  const endpoints = await waitFor(path.join(directory, 'server/config.json'), 120000, server);
  const ca = fs.readFileSync(path.join(directory, 'server/ca.pem'));
  const untrusted = fs.readFileSync(path.join(directory, 'server/untrusted.pem'));
  for (const filename of ['certificate-tool.json', 'ca.public.txt', 'server.public.txt', 'untrusted.public.txt'])
    fs.copyFileSync(path.join(directory, 'server', filename), path.join(directory, filename));
  const controls = [];
  markStage('probe-server-http-control');
  await localRequest(endpoints.httpUrl, '/direct');
  controls.push(currentStage);
  for (const [name, url, trust] of [
    ['untrusted-leaf-control', endpoints.untrustedUrl, untrusted],
    ['api-ca-control', endpoints.apiUrl, ca],
    ['target-ca-control', endpoints.targetUrl, ca],
  ]) {
    markStage(`probe-server-${name}`);
    await localRequest(url, '/direct', trust);
    controls.push(currentStage);
  }
  for (const [name, url, trust] of [
    ['api-wrong-ca-refusal', endpoints.apiUrl, untrusted],
    ['target-wrong-ca-refusal', endpoints.targetUrl, untrusted],
    ['untrusted-ca-refusal', endpoints.untrustedUrl, ca],
  ]) {
    markStage(`probe-server-${name}`);
    await assert.rejects(localRequest(url, '/direct', trust), (error) =>
      [
        'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
        'DEPTH_ZERO_SELF_SIGNED_CERT',
        'SELF_SIGNED_CERT_IN_CHAIN',
        'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
      ].includes(error.code),
    );
    controls.push(currentStage);
  }
  fs.writeFileSync(path.join(directory, 'host-tls-controls.json'), JSON.stringify({ controls }, null, 2));
  await build('ordinary-release-build', { ENTRY_FILE: 'index.ts' });
  const artifact = path.join(directory, platform === 'android' ? 'ordinary-release.apk' : 'ordinary-release.app');
  fs.cpSync(appPath, artifact, { recursive: true });
  if (platform === 'android') checkAndroidArtifact(artifact);
  else {
    const plist = JSON.parse(
      execFileSync('plutil', ['-convert', 'json', '-o', '-', path.join(artifact, 'Info.plist')], {
        encoding: 'utf8',
        timeout: 10000,
        killSignal: 'SIGKILL',
      }),
    );
    assert.equal(plist.NSAppTransportSecurity.NSAllowsArbitraryLoads, false);
    assert.equal(plist.NSAppTransportSecurity.NSAllowsLocalNetworking, false);
    assert.equal(plist.LedovaDevelopmentHTTPHosts, undefined);
  }
  const binary = platform === 'android' ? artifact : path.join(artifact, config.name);
  fs.writeFileSync(
    path.join(directory, 'artifact-sha256.txt'),
    `${createHash('sha256').update(fs.readFileSync(binary)).digest('hex')}  ${path.basename(binary)}\n`,
  );
  if (platform === 'android') {
    const inventory = execFileSync(
      process.env.PYTHON || 'python3',
      [
        path.join(mobile, 'scripts/check-android-binary.py'),
        artifact,
        process.env.NATIVE_ANDROID_ABIS || 'x86_64,arm64-v8a',
      ],
      { timeout: 10000, killSignal: 'SIGKILL' },
    );
    fs.writeFileSync(path.join(directory, 'native-library-alignment.json'), inventory);
    await command(
      './gradlew',
      [':app:dependencies', '--configuration', 'releaseRuntimeClasspath', '--no-daemon', '--max-workers=2'],
      'native-dependencies',
      {},
      path.join(mobile, 'android'),
    );
    fs.copyFileSync(path.join(mobile, 'android/build.gradle'), path.join(directory, 'native-repositories.txt'));
  } else {
    const provider = path.join(mobile, 'ios/build/generated/ios/RCTModulesConformingToProtocolsProvider.mm');
    assert.match(fs.readFileSync(provider, 'utf8'), /LedovaHTTPRequestHandler/);
  }
  await launch('ordinary');
  await delay(3000);
  await screenshot('ordinary');
  let nativeSource;
  if (platform === 'android') {
    const resource = path.join(mobile, 'android/app/src/main/res/xml/ledova_network_security_config.xml');
    const certificate = path.join(mobile, 'android/app/src/main/res/raw/ledova_probe_ca.pem');
    preserve(resource);
    preserve(certificate);
    fs.mkdirSync(path.dirname(certificate), { recursive: true });
    fs.writeFileSync(certificate, ca);
    fs.writeFileSync(
      resource,
      '<network-security-config><base-config cleartextTrafficPermitted="false"><trust-anchors><certificates src="system"/><certificates src="@raw/ledova_probe_ca"/></trust-anchors></base-config></network-security-config>',
    );
    nativeSource = path.join(
      mobile,
      'android/app/src/main/java',
      ...config.android.package.split('.'),
      'MainApplication.kt',
    );
  } else {
    await command(
      'xcrun',
      ['simctl', 'keychain', device, 'add-root-cert', path.join(directory, 'server/ca.pem')],
      'simulator-trust-probe-ca',
    );
    nativeSource = path.join(mobile, 'ios', config.name, 'LedovaHTTPRequestHandler.m');
  }
  preserve(nativeSource);
  const correct = fs.readFileSync(nativeSource, 'utf8');
  const bad =
    platform === 'android'
      ? correct
          .replace('.followRedirects(false)', '.followRedirects(true)')
          .replace('.followSslRedirects(false)', '.followSslRedirects(true)')
      : correct.replace('completionHandler(nil);', 'completionHandler(request);');
  assert.notEqual(bad, correct, 'The native redirect mutation must change the built source.');
  const environment = {
    ENTRY_FILE: 'native-tests/index.tsx',
    EXPO_PUBLIC_API_URL: endpoints.apiUrl,
    EXPO_PUBLIC_NATIVE_PROBE_TARGET: endpoints.targetUrl,
    EXPO_PUBLIC_NATIVE_PROBE_HTTP: endpoints.httpUrl,
    EXPO_PUBLIC_NATIVE_PROBE_UNTRUSTED: endpoints.untrustedUrl,
  };
  for (const [name, source] of [
    ['red', bad],
    ['green', correct],
  ]) {
    fs.writeFileSync(nativeSource, source);
    markStage(`probe-${name}-reset`);
    await localRequest(endpoints.apiUrl, '/reset', ca);
    await build(`probe-${name}-build`, environment);
    await launch(`probe-${name}`);
    markStage(`probe-${name}-report`);
    const result = await waitFor(path.join(directory, 'server/result.json'), 120000);
    fs.writeFileSync(path.join(directory, `native-${name}.json`), JSON.stringify(result, null, 2));
    await delay(500);
    await screenshot(`probe-${name}`);
    const failed = result.checks
      .filter((check) => !check.passed)
      .map((check) => check.name)
      .sort();
    assert.ok(result.checks.length >= 12);
    assert.deepEqual(failed, name === 'red' ? ['native 307 refusal', 'native 308 refusal'] : []);
    assert.equal(result.counts.redirectTarget, name === 'red' ? 2 : 0);
    assert.equal(result.counts.redirectBody, name === 'red' ? 2 : 0);
    if (name === 'green') assert.equal(result.counts.redirectBearer, 0);
    for (const count of ['direct', 'targetControl', 'upload', 'download', 'stream', 'cancelled'])
      assert.ok(result.counts[count] > 0, `${count} needs a positive control.`);
    for (const count of ['http', 'untrusted']) assert.equal(result.counts[count], 0);
  }
  console.log('Native Release probe passed with observed redirect failures before the fix.');
} catch (error) {
  failure = error;
  console.error(`Native validation failed during ${currentStage}: ${error.message}`);
} finally {
  const cleanup = await Promise.allSettled([...activeChildren.keys()].map(stopOwned));
  const cleanupErrors = cleanup.filter((result) => result.status === 'rejected').map((result) => result.reason);
  for (const [filename, contents] of restored) {
    try {
      if (contents === null) fs.rmSync(filename, { force: true });
      else fs.writeFileSync(filename, contents);
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  try {
    fs.closeSync(serverLog);
  } catch (error) {
    cleanupErrors.push(error);
  }
  for (const [signal, handler] of Object.entries(signalHandlers)) process.off(signal, handler);
  for (const error of cleanupErrors) console.error(`Native cleanup failed: ${error.message}`);
  if (!failure && cleanupErrors.length) failure = new AggregateError(cleanupErrors, 'Native cleanup failed.');
}
if (cancellation.signal.aborted) console.error(cancellation.signal.reason.message);
else if (failure) throw failure;
