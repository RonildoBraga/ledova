import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const expoMetro = createRequire(require.resolve('expo/metro-config'));
const { resolve } = expoMetro('@expo/metro/metro-resolver');

function fileSystemLookup(file) {
  try {
    const stat = fs.statSync(file);
    return { exists: true, type: stat.isDirectory() ? 'd' : 'f', realPath: fs.realpathSync(file) };
  } catch {
    return { exists: false };
  }
}

function getPackage(file) {
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;
}

function getPackageForModule(file) {
  let root = path.dirname(file);
  while (root !== path.dirname(root)) {
    const packageJson = getPackage(path.join(root, 'package.json'));
    if (packageJson) return { rootPath: root, packageJson, packageRelativePath: path.relative(root, file) };
    root = path.dirname(root);
  }
  return null;
}

export function resolveSharedPeer(config, originModulePath, moduleName, platform) {
  const context = {
    ...config.resolver,
    originModulePath,
    allowHaste: false,
    assetExts: new Set(config.resolver.assetExts),
    mainFields: config.resolver.resolverMainFields,
    preferNativePlatform: true,
    fileSystemLookup,
    doesFileExist: (file) => fileSystemLookup(file).type === 'f',
    getPackage,
    getPackageForModule,
    isAssetFile: () => false,
    resolveAsset: () => null,
    customResolverOptions: {},
    resolveRequest: resolve,
    unstable_isESMImport: true,
    unstable_logWarning: () => {},
  };
  return (config.resolver.resolveRequest ?? resolve)(context, moduleName, platform).filePath;
}

export function checkSharedPeers(config, mobile) {
  const results = [];
  const shared = path.resolve(mobile, '../packages/shared/src/hooks/useOrderSubmissions.ts');
  for (const platform of ['ios', 'android']) {
    for (const name of ['react', 'react/jsx-runtime', '@tanstack/react-query']) {
      const native = resolveSharedPeer(config, path.join(mobile, 'App.tsx'), name, platform);
      const peer = resolveSharedPeer(config, shared, name, platform);
      if (native !== peer || !native.startsWith(path.join(mobile, 'node_modules') + path.sep)) {
        throw new Error(`Shared mobile peer mismatch: ${platform} ${name}: ${native} != ${peer}`);
      }
      results.push({ platform, name, file: native });
    }
  }
  return results;
}
