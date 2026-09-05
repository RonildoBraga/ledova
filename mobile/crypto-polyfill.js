/* eslint-disable @typescript-eslint/no-require-imports, no-undef */

import 'react-native-get-random-values';

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
