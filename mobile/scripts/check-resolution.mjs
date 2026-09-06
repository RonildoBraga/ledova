// Fail when something mobile/src imports does not resolve from mobile/node_modules.
//
// `tsc --noEmit` does not answer this question. TypeScript walks up the directory
// tree when a lookup fails, so an import can type-check against a copy of a package
// in the repository root that `make install` put there for the dashboard. Metro
// never sees that copy: metro.config.js watches only ../packages, so the root is
// outside its roots. The type-check goes green and the bundle breaks.
//
// This resolves each specifier the way Node does - honouring the package's own
// `exports` map - and then asserts the answer came from inside mobile. Nothing here
// replaces a real bundle; it catches the resolution half of that cheaply.

import { readdir, readFile } from 'node:fs/promises';
import { createRequire, isBuiltin } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const MOBILE = path.resolve(import.meta.dirname, '..');
const REPO = path.resolve(MOBILE, '..');
const resolver = createRequire(path.join(MOBILE, 'index.ts'));

// `from '...'`, bare `import '...'`, and `require('...')`.
const SPECIFIER = /(?:from|import|require)\s*\(?\s*['"]([^'"]+)['"]/g;

const manifest = JSON.parse(await readFile(path.join(MOBILE, 'package.json'), 'utf8'));
const runtime = new Set(Object.keys(manifest.dependencies ?? {}));
const metroConfig = await readFile(path.join(MOBILE, 'metro.config.js'), 'utf8');

async function* sourceFiles(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* sourceFiles(full);
    else if (/\.tsx?$/.test(entry.name)) yield full;
  }
}

function packageOf(specifier) {
  const segments = specifier.split('/');
  return specifier.startsWith('@') ? segments.slice(0, 2).join('/') : segments[0];
}

function lineOf(text, index) {
  return text.slice(0, index).split('\n').length;
}

const sites = new Map();

for await (const file of sourceFiles(path.join(MOBILE, 'src'))) {
  const text = await readFile(file, 'utf8');
  for (const match of text.matchAll(SPECIFIER)) {
    const specifier = match[1];
    if (specifier.startsWith('.') || specifier.startsWith('/')) continue;
    if (!runtime.has(packageOf(specifier))) continue;
    if (!sites.has(specifier)) {
      sites.set(specifier, `${path.relative(REPO, file)}:${lineOf(text, match.index)}`);
    }
  }
}

const failures = [];

for (const [specifier, site] of [...sites].sort()) {
  // A Node builtin name is a runtime dependency only because Metro maps it to a
  // browser shim. Node resolves it to the builtin, so check the alias instead.
  if (isBuiltin(specifier)) {
    if (!new RegExp(`^\\s*${specifier}\\s*:`, 'm').test(metroConfig)) {
      failures.push(`${site}: '${specifier}' shadows a Node builtin with no extraNodeModules alias in metro.config.js`);
    }
    continue;
  }

  let resolved;
  try {
    resolved = resolver.resolve(specifier);
  } catch (error) {
    failures.push(`${site}: '${specifier}' does not resolve (${error.code ?? error.message})`);
    continue;
  }

  const insideMobile = resolved.startsWith(path.join(MOBILE, 'node_modules') + path.sep);
  const insideWorkspace = resolved.startsWith(path.join(REPO, 'packages') + path.sep);
  if (!insideMobile && !insideWorkspace) {
    failures.push(`${site}: '${specifier}' resolves outside mobile, to ${path.relative(REPO, resolved)}`);
  }
}

if (failures.length > 0) {
  console.error(`Mobile imports that mobile/node_modules cannot satisfy (${failures.length}):\n`);
  for (const failure of failures) console.error(`  ${failure}`);
  console.error('\nMetro resolves from mobile/ and ../packages only. A green tsc does not mean the bundle resolves.');
  process.exit(1);
}

console.log(`Mobile resolution clean: ${sites.size} runtime specifiers resolve from mobile/node_modules.`);
