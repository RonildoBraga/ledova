/* eslint-disable @typescript-eslint/no-require-imports */
/* eslint-disable no-undef */
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Add polyfills for Node.js modules
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

// Follow the file:../packages/packages/* links so a clean clone can bundle.
config.watchFolders = [workspacePackages];
config.resolver.nodeModulesPaths = [
  path.resolve(__dirname, 'node_modules'),
  path.resolve(workspacePackages, 'node_modules'),
];

module.exports = config;
