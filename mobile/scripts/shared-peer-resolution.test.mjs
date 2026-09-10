import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import config from '../metro.config.js';
import { checkSharedPeers, resolveSharedPeer } from './shared-peer-resolution.mjs';

const mobile = path.resolve(import.meta.dirname, '..');
const shared = path.resolve(mobile, '../packages/shared/src/hooks/useOrderSubmissions.ts');
const unpinned = { ...config, resolver: { ...config.resolver, resolveRequest: undefined } };

test('the actual mobile and shared imports reach the same mobile peers on both platforms', () => {
  assert.equal(checkSharedPeers(config, mobile).length, 6);
});

test('root-installed peers are detected when the scoped override is removed', () => {
  assert.throws(() => checkSharedPeers(unpinned, mobile), /Shared mobile peer mismatch/);
});

test('unrelated package and relative imports preserve inherited resolution', () => {
  for (const platform of ['ios', 'android'])
    for (const specifier of ['axios', '../utils/order-submission']) {
      assert.equal(
        resolveSharedPeer(config, shared, specifier, platform),
        resolveSharedPeer(unpinned, shared, specifier, platform),
      );
    }
});
