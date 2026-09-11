import assert from 'node:assert/strict';

const permitted = new Set(['org.example.ledova.scanner.test', 'org.example.ledova.releaseprobe.test']);

export function createAndroidTestPackages(invoke, report) {
  const owned = new Set();
  return {
    async install(name, action) {
      assert.ok(permitted.has(name), 'Only the two scanner instrumentation packages can be tracked.');
      owned.add(name);
      await action();
    },
    forget(name) {
      owned.delete(name);
    },
    cleanup() {
      const errors = [];
      for (const name of owned) {
        try {
          const installed = invoke(['shell', 'pm', 'path', name]);
          const result = installed.trim() ? invoke(['uninstall', name]) : 'Package not installed.\n';
          report(name, result);
          owned.delete(name);
        } catch (error) {
          errors.push(error);
        }
      }
      return errors;
    },
  };
}
