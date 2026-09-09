import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';

const plist = createRequire(import.meta.url)('@expo/plist').default;

export function simulatorIdentity(binary, headers, bundleIdentifier) {
  const sections = headers.split(/\r?\nSection\r?\n/).slice(1);
  const matches = sections.filter(
    (section) =>
      section.match(/^\s*sectname (\S+)\s*$/m)?.[1] === '__entitlements' &&
      section.match(/^\s*segname (\S+)\s*$/m)?.[1] === '__TEXT',
  );
  assert.equal(matches.length, 1, 'The binary needs one __TEXT,__entitlements simulator section.');
  const offset = Number(matches[0].match(/^\s*offset (\d+)\s*$/m)?.[1]);
  const size = Number(matches[0].match(/^\s*size (0x[\da-f]+)\s*$/im)?.[1]);
  assert.ok(
    Number.isSafeInteger(offset) &&
      Number.isSafeInteger(size) &&
      offset >= 0 &&
      size > 0 &&
      offset + size <= binary.length,
    'The simulator entitlement section must fit inside the binary.',
  );
  const entitlements = plist.parse(
    binary
      .subarray(offset, offset + size)
      .toString('utf8')
      .replace(/\0+$/, ''),
  );
  const identifier = entitlements['application-identifier'] ?? entitlements['com.apple.application-identifier'];
  assert.ok(
    typeof identifier === 'string' && (identifier === bundleIdentifier || identifier.endsWith(`.${bundleIdentifier}`)),
    'The simulator application identity must match the built bundle.',
  );
  return { source: '__TEXT,__entitlements', entitlements };
}

function tool(args) {
  return execFileSync('xcrun', args, { encoding: 'utf8', timeout: 10000, killSignal: 'SIGKILL' });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [binary, bundleIdentifier, output] = process.argv.slice(2);
  assert.ok(binary && bundleIdentifier && output, 'Use check-ios-simulator-identity.mjs BINARY BUNDLE_ID OUTPUT_JSON');
  const architectures = tool(['lipo', '-archs', binary]).trim().split(/\s+/);
  assert.deepEqual(
    [...architectures].sort(),
    ['arm64', 'x86_64'],
    'Both declared simulator architectures are required.',
  );
  const temporary = `${output}.slices`;
  fs.mkdirSync(temporary);
  try {
    const identities = architectures.map((architecture) => {
      const slice = path.join(temporary, architecture);
      tool(['lipo', binary, '-thin', architecture, '-output', slice]);
      const headers = tool(['otool', '-l', slice]);
      return { architecture, ...simulatorIdentity(fs.readFileSync(slice), headers, bundleIdentifier) };
    });
    const sha256 = createHash('sha256').update(fs.readFileSync(binary)).digest('hex');
    fs.writeFileSync(output, JSON.stringify({ sha256, identities }, null, 2));
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}
