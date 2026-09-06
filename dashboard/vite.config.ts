import { defineConfig, loadEnv, normalizePath, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createRequire } from 'node:module';
import { dirname } from 'node:path';
import tailwindcss from '@tailwindcss/vite';

const require = createRequire(import.meta.url);
const resolvePolyfill = (moduleId: string) => normalizePath(require.resolve(moduleId));
const resolvePolyfillRoot = (moduleId: string) => normalizePath(dirname(require.resolve(`${moduleId}/package.json`)));
const TRAILING_SLASH_IMPORT = /\/$/;

const browserPolyfills: Record<string, string> = {
  buffer: resolvePolyfillRoot('buffer'),
  process: resolvePolyfill('process/browser'),
  util: resolvePolyfillRoot('util'),
  events: resolvePolyfillRoot('events'),
  stream: resolvePolyfillRoot('stream-browserify'),
};

function nodePolyfills(modules: string[]): Plugin {
  const alias: Record<string, string> = {};
  for (const mod of modules) {
    const resolved = browserPolyfills[mod];
    if (resolved) {
      alias[mod] = resolved;
      alias[`node:${mod}`] = resolved;
    }
  }

  const inject = {
    Buffer: browserPolyfills.buffer,
    process: browserPolyfills.process,
  };

  return {
    name: 'node-polyfills',
    enforce: 'pre',
    resolveId(source) {
      if (!TRAILING_SLASH_IMPORT.test(source)) return null;
      return alias[source.replace(TRAILING_SLASH_IMPORT, '')] ?? null;
    },
    config() {
      return {
        resolve: { alias },
        build: {
          rollupOptions: { transform: { inject } },
        },
        optimizeDeps: {
          rolldownOptions: { transform: { inject } },
        },
      };
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [nodePolyfills(['buffer', 'process', 'util', 'events', 'stream']), react(), tailwindcss()],
    resolve: {
      tsconfigPaths: true,
    },
    server: {
      host: env.VITE_HOST,
      port: Number(env.VITE_PORT),
      allowedHosts: env.VITE_ALLOWED_HOSTS?.split(','),
    },
    optimizeDeps: {
      include: [
        '@noble/hashes/hmac',
        '@noble/hashes/sha512',
        '@noble/hashes/sha256',
        '@noble/hashes/ripemd160',
        'ethereum-cryptography/secp256k1',
        'ethereum-cryptography/keccak',
        'bech32',
      ],
    },
  };
});
