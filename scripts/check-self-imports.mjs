import { readdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sourceImports } from './source-imports.mjs';

const ROOT = path.resolve(import.meta.dirname, '..');
const require = createRequire(path.join(ROOT, 'packages/shared/package.json'));
const ts = require('typescript');
const SOURCE_FILE = /\.(tsx?|jsx?|mjs|cjs)$/;
const NOT_SOURCE = new Set(['node_modules', 'dist', 'build', 'coverage', '.turbo', '.git']);

async function* sourceFiles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (NOT_SOURCE.has(entry.name)) continue;
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) yield* sourceFiles(full);
    else if (entry.isFile() && SOURCE_FILE.test(entry.name)) yield full;
  }
}

export async function checkSelfImports(root = ROOT) {
  const packages = path.join(root, 'packages');
  const failures = [];
  let scanned = 0;
  for (const entry of await readdir(packages, { withFileTypes: true })) {
    if (!entry.isDirectory() || NOT_SOURCE.has(entry.name)) continue;
    const directory = path.join(packages, entry.name);
    let manifest;
    try {
      manifest = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
    } catch (error) {
      if (error.code === 'ENOENT') continue;
      throw error;
    }
    if (!manifest.name) continue;
    for await (const file of sourceFiles(directory)) {
      scanned += 1;
      const text = await readFile(file, 'utf8');
      for (const { specifier, line } of sourceImports(ts, text, file)) {
        if (specifier === manifest.name || specifier.startsWith(`${manifest.name}/`)) {
          failures.push(`${path.relative(root, file)}:${line}: '${specifier}' imports its own package; use a relative path.`);
        }
      }
    }
  }
  return { failures: failures.sort(), scanned };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { failures, scanned } = await checkSelfImports();
  if (failures.length) {
    console.error(`Packages importing themselves (${failures.length}):\n${failures.join('\n')}`);
    process.exitCode = 1;
  } else {
    console.log(`No package imports itself by name in ${scanned} workspace files.`);
  }
}
