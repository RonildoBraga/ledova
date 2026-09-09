import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { test } from 'node:test';
import { createRequire } from 'node:module';
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
