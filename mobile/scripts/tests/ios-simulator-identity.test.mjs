import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { simulatorIdentity } from '../check-ios-simulator-identity.mjs';

const plist = createRequire(import.meta.url)('@expo/plist').default;
const bundle = 'org.example.ledova';

function section(identifier = bundle) {
  const entitlements = { 'application-identifier': identifier, 'aps-environment': 'development' };
  const xml = Buffer.from(plist.build(entitlements));
  return {
    entitlements,
    binary: Buffer.concat([Buffer.alloc(32), xml]),
    headers: `Load command 0\nSection\n  sectname __entitlements\n   segname __TEXT\n      size 0x${xml.length.toString(16)}\n    offset 32\n`,
  };
}

test('the simulator section supplies the bundle identity with or without an Xcode prefix', () => {
  for (const identifier of [bundle, `SYNTHETIC.${bundle}`]) {
    const { binary, headers, entitlements } = section(identifier);
    const actual = simulatorIdentity(binary, headers, bundle);
    assert.equal(actual.source, '__TEXT,__entitlements');
    assert.deepEqual({ ...actual.entitlements }, entitlements);
  }
});

test('a code-signature entitlement is insufficient without the simulator section', () => {
  const { binary } = section();
  assert.throws(
    () => simulatorIdentity(binary, 'Load command 0\n      cmd LC_CODE_SIGNATURE\n', bundle),
    /one __TEXT,__entitlements simulator section/,
  );
});

test('a wrong segment or duplicate section cannot supply the simulator identity', () => {
  const { binary, headers } = section();
  for (const invalid of [headers.replace('__TEXT', '__DATA'), `${headers}${headers}`]) {
    assert.throws(() => simulatorIdentity(binary, invalid, bundle), /one __TEXT,__entitlements simulator section/);
  }
});

test('section bounds and a different application identity fail closed', () => {
  const { binary, headers } = section();
  assert.throws(() => simulatorIdentity(binary.subarray(0, 40), headers, bundle), /fit inside the binary/);
  assert.throws(() => simulatorIdentity(binary, headers.replace('offset 32', 'offset 9999999'), bundle), /fit inside/);
  const wrong = section('org.example.unrelated');
  assert.throws(() => simulatorIdentity(wrong.binary, wrong.headers, bundle), /identity must match/);
});

function inspection(behavior, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-inspection-timeout-')));
  try {
    fs.mkdirSync(path.join(root, 'bin'));
    const source = path.resolve(import.meta.dirname, '../check-ios-simulator-identity.mjs');
    let checker = fs.readFileSync(source, 'utf8');
    assert.equal(checker.match(/timeout: \d+/g)?.length, 1);
    checker = checker.replace(/timeout: (\d+)/, (_, value) => `timeout: ${Number(value) / 10}`);
    fs.writeFileSync(path.join(root, 'checker.mjs'), checker);
    fs.symlinkSync(path.resolve(import.meta.dirname, '../../node_modules'), path.join(root, 'node_modules'));
    const { binary, headers } = section();
    const artifact = path.join(root, 'structural-binary');
    fs.writeFileSync(artifact, binary);
    const script = `#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const args = process.argv.slice(2);
if (args[0] === 'lipo') {
  if (args[1] === '-archs') process.stdout.write('x86_64 arm64');
  else fs.copyFileSync(args[1], args[args.indexOf('-output') + 1]);
} else {
  fs.appendFileSync('inspections.jsonl', JSON.stringify({ pid: process.pid, architecture: path.basename(args.at(-1)) }) + '\\n');
  ${behavior}
}
`;
    fs.writeFileSync(path.join(root, 'bin/xcrun'), script, { mode: 0o700 });
    fs.writeFileSync(path.join(root, 'headers.txt'), headers);
    const output = path.join(root, 'identity.json');
    const result = spawnSync(process.execPath, [path.join(root, 'checker.mjs'), artifact, bundle, output], {
      cwd: root,
      env: { ...process.env, PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH}` },
      encoding: 'utf8',
      timeout: 20000,
      killSignal: 'SIGKILL',
    });
    assert.equal(result.error, undefined);
    const inspections = fs
      .readFileSync(path.join(root, 'inspections.jsonl'), 'utf8')
      .trim()
      .split('\n')
      .map(JSON.parse);
    for (const { pid } of inspections) assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
    assert.ok(!fs.existsSync(`${output}.slices`), 'Owned slice files must be removed after success or failure.');
    check({ result, inspections, output });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test('both actual checker inspections can succeed after the former per-tool deadline', () => {
  inspection(
    "setTimeout(() => process.stdout.write(fs.readFileSync('headers.txt')), 1500);",
    ({ result, inspections, output }) => {
      assert.equal(result.status, 0, result.stderr);
      assert.deepEqual(
        inspections.map(({ architecture }) => architecture),
        ['x86_64', 'arm64'],
      );
      const identity = JSON.parse(fs.readFileSync(output, 'utf8'));
      assert.equal(identity.identities.length, 2);
      assert.ok(identity.identities.every(({ entitlements }) => entitlements['application-identifier'] === bundle));
    },
  );
});

test('a hung inspection is killed and reaped within its deadline and removes owned slices', () => {
  inspection('setInterval(() => {}, 1000);', ({ result, inspections, output }) => {
    assert.equal(result.status, 1);
    assert.match(result.stderr, /ETIMEDOUT/);
    assert.match(result.stderr, /SIGKILL/);
    assert.equal(inspections.length, 1);
    assert.ok(!fs.existsSync(output));
  });
});
