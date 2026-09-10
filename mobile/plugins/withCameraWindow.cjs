const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { withFinalizedMod } = require('expo/config-plugins');

module.exports = function withCameraWindow(config) {
  return withFinalizedMod(config, [
    'android',
    async (config) => {
      const source = pathToFileURL(path.join(__dirname, '../scripts/prepare-camera-android.mjs'));
      const { prepareCamera } = await import(source.href);
      prepareCamera('apply', config.modRequest.projectRoot);
      return config;
    },
  ]);
};
