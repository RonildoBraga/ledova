/* eslint-disable @typescript-eslint/no-require-imports, no-undef */

const { getRandomValues } = require('expo-crypto');

global.crypto ??= {};
global.crypto.getRandomValues = (bytes) => {
  if (
    ![Int8Array, Uint8Array, Uint8ClampedArray, Int16Array, Uint16Array, Int32Array, Uint32Array].some(
      (type) => bytes instanceof type,
    )
  ) {
    throw new TypeError('Random values require an integer typed array.');
  }
  if (bytes.byteLength > 65536) throw new RangeError('Random values are limited to 65536 bytes.');
  return getRandomValues(bytes);
};

const { Buffer } = require('buffer');
global.Buffer = Buffer;

const _savedEnv = { ...(global.process?.env || {}) };
global.process = require('process/browser');
global.process.env = { ..._savedEnv, ...global.process.env };
global.process.version = 'v16.0.0';
global.process.browser = true;

require('events');
require('stream-browserify');
require('util');
require('assert');
