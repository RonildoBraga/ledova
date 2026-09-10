import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

const mobile = path.resolve(import.meta.dirname, '../..');

function fixture(untrustedEndpoint, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-probe-tls-')));
  try {
    fs.mkdirSync(path.join(root, 'scripts'));
    for (const file of ['prepare-camera-android.mjs', 'camera-probe-source.mjs'])
      fs.copyFileSync(path.join(mobile, 'scripts', file), path.join(root, 'scripts', file));
    fs.mkdirSync(path.join(root, 'bin'));
    fs.copyFileSync(path.join(mobile, 'app.json'), path.join(root, 'app.json'));
    fs.copyFileSync(path.join(mobile, 'scripts/native-smoke.mjs'), path.join(root, 'scripts/native-smoke.mjs'));
    let server = fs.readFileSync(path.join(mobile, 'scripts/native-probe-server.mjs'), 'utf8');
    if (untrustedEndpoint) {
      const original = `https.createServer(credentials, handler('${untrustedEndpoint}'))`;
      const replacement = `https.createServer({
        key: fs.readFileSync(path.join(directory, 'untrusted.key')),
        cert: fs.readFileSync(path.join(directory, 'untrusted.pem')),
      }, handler('${untrustedEndpoint}'))`;
      assert.ok(server.includes(original));
      server = server.replace(original, replacement);
    }
    fs.writeFileSync(path.join(root, 'scripts/native-probe-server.mjs'), server);
    fs.writeFileSync(path.join(root, 'bin/xcodebuild'), '#!/bin/sh\ntouch build-reached\nexit 73\n', { mode: 0o700 });
    const ambient = path.join(root, 'ambient-openssl.cnf');
    fs.writeFileSync(
      ambient,
      '[req]\ndistinguished_name=probe_name\nx509_extensions=ambient_ca\n[probe_name]\n[ambient_ca]\nbasicConstraints=critical,CA:TRUE\n',
    );
    const output = path.join(root, 'results');
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/native-smoke.mjs'), 'ios', output], {
      cwd: root,
      env: {
        ...process.env,
        PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH}`,
        OPENSSL_CONF: ambient,
        IOS_SIMULATOR_UDID: 'synthetic-tls-control',
      },
      encoding: 'utf8',
      timeout: 150000,
      killSignal: 'SIGTERM',
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    check({ output, result, buildReached: fs.existsSync(path.join(root, 'build-reached')) });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test('strict CA and wrong-CA controls pass before a native build despite ambient CA extensions', () => {
  fixture(null, ({ output, result, buildReached }) => {
    assert.equal(buildReached, true, result.stderr);
    assert.match(result.stderr, /ordinary-release-build failed \(73\)/);
    const { controls } = JSON.parse(fs.readFileSync(path.join(output, 'host-tls-controls.json'), 'utf8'));
    assert.deepEqual(controls, [
      'probe-server-http-control',
      'probe-server-untrusted-leaf-control',
      'probe-server-api-ca-control',
      'probe-server-target-ca-control',
      'probe-server-api-wrong-ca-refusal',
      'probe-server-target-wrong-ca-refusal',
      'probe-server-untrusted-ca-refusal',
    ]);
    const tool = JSON.parse(fs.readFileSync(path.join(output, 'certificate-tool.json'), 'utf8'));
    assert.ok(path.isAbsolute(tool.executable));
    assert.match(tool.version, /^OpenSSL /);
    const ca = fs.readFileSync(path.join(output, 'ca.public.txt'), 'utf8');
    assert.equal(ca.match(/X509v3 Basic Constraints/g)?.length, 1);
    assert.match(ca, /Certificate Sign, CRL Sign/);
    for (const name of ['server', 'untrusted']) {
      const leaf = fs.readFileSync(path.join(output, `${name}.public.txt`), 'utf8');
      assert.match(leaf, /CA:FALSE/);
      assert.match(leaf, /TLS Web Server Authentication/);
      assert.match(leaf, /Digital Signature, Key Encipherment/);
      assert.match(leaf, /DNS:localhost, IP Address:127\.0\.0\.1, IP Address:10\.0\.2\.2/);
    }
    assert.ok(!fs.readdirSync(output).some((name) => name.endsWith('.key')));
  });
});

for (const [endpoint, stage] of [
  ['primary', 'api-ca-control'],
  ['target', 'target-ca-control'],
]) {
  test(`an invalid ${endpoint} certificate stops the runner before the native build`, () => {
    fixture(endpoint, ({ result, buildReached }) => {
      assert.equal(buildReached, false, result.stdout);
      assert.match(result.stderr, new RegExp(`Native validation failed during probe-server-${stage}:`));
      assert.match(result.stderr, /DEPTH_ZERO_SELF_SIGNED_CERT/);
    });
  });
}
