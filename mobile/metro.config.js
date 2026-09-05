/* eslint-disable @typescript-eslint/no-require-imports */
/* eslint-disable no-undef */
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.resolver.extraNodeModules = {
  crypto: require.resolve('crypto-browserify'),
  stream: require.resolve('stream-browserify'),
  buffer: require.resolve('buffer'),
  process: require.resolve('process/browser'),
  events: require.resolve('events'),
  assert: require.resolve('assert'),
  util: require.resolve('util'),
};

const path = require('path');
const workspacePackages = path.resolve(__dirname, '../packages');

config.watchFolders = [workspacePackages];

module.exports = config;
