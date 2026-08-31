/* eslint-disable @typescript-eslint/no-require-imports, no-undef */
// Crypto polyfills for React Native
// This must be imported before any other modules that require crypto

// Polyfill for global crypto.getRandomValues
import 'react-native-get-random-values';

// Polyfill for Buffer
const { Buffer } = require('buffer');
global.Buffer = Buffer;

// Polyfill for process — preserve Expo's EXPO_PUBLIC_* env vars (the polyfill wipes process.env).
const _savedEnv = { ...(global.process?.env || {}) };
global.process = require('process/browser');
global.process.env = { ..._savedEnv, ...global.process.env };
global.process.version = 'v16.0.0';
global.process.browser = true;

// Polyfill for stream and events (required by stream-browserify and crypto modules)
require('events');
require('stream-browserify');
require('util');
require('assert');
