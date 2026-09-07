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
//
// It scans everything Metro bundles: `src` recursively, plus the entry chain at the
// mobile root. A root file named `*.config.*` is tooling that runs in Node and is
// skipped; anything else there - index.ts, App.tsx, crypto-polyfill.js - is bundled
// and is exactly where the polyfill and shim packages are imported.
//
// A specifier is checked unless it is a devDependency imported from a test file, as
// jest.config.js defines test files. Anything undeclared fails: a package that lives
// only in the repository root resolves for TypeScript and not for Metro, which is the
// whole point of this gate.

import { readdir, readFile } from 'node:fs/promises';
import { createRequire, isBuiltin } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const MOBILE = path.resolve(import.meta.dirname, '..');
const REPO = path.resolve(MOBILE, '..');
const resolver = createRequire(path.join(MOBILE, 'index.ts'));

// `from '...'`, bare `import '...'`, `import('...')` and `require('...')`. The
// lookbehind and the newline exclusion matter: without them a string literal such as
// `mode === 'import'` matches, and the capture then runs to the next quote in the file.
const SPECIFIER =
  /(?<!['"`\w$])(?:from|import)\s+['"]([^'"\n]+)['"]|(?<!['"`\w$])(?:import|require)\s*\(\s*['"]([^'"\n]+)['"]/g;

const manifest = JSON.parse(await readFile(path.join(MOBILE, 'package.json'), 'utf8'));
const runtime = new Set(Object.keys(manifest.dependencies ?? {}));
const development = new Set(Object.keys(manifest.devDependencies ?? {}));
const metroConfig = await readFile(path.join(MOBILE, 'metro.config.js'), 'utf8');

const { default: jestConfig } = await import(path.join(MOBILE, 'jest.config.js'));
const TEST_FILE = new RegExp(
  (jestConfig.testMatch ?? [])
    .map((pattern) =>
      pattern
        .replace('<rootDir>/', '')
        .replace(/[.+^${}()|[\]\\]/g, String.raw`\$&`)
        .replace(/\*\*\//g, '(?:.*/)?')
        .replace(/\*/g, '[^/]*'),
    )
    .map((pattern) => `^${pattern}$`)
    .join('|'),
);

async function* sourceFiles(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* sourceFiles(full);
    else if (/\.(tsx?|js)$/.test(entry.name)) yield full;
  }
}

async function* bundledFiles() {
  yield* sourceFiles(path.join(MOBILE, 'src'));
  for (const entry of await readdir(MOBILE, { withFileTypes: true })) {
    if (!entry.isFile()) continue;
    if (/\.config\.[cm]?[jt]s$/.test(entry.name)) continue;
    if (/\.(tsx?|js)$/.test(entry.name)) yield path.join(MOBILE, entry.name);
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

for await (const file of bundledFiles()) {
  const text = await readFile(file, 'utf8');
  const isTest = TEST_FILE.test(path.relative(MOBILE, file));
  for (const match of text.matchAll(SPECIFIER)) {
    const specifier = match[1] ?? match[2];
    if (specifier.startsWith('.') || specifier.startsWith('/')) continue;
    if (isTest && development.has(packageOf(specifier))) continue;
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

  const name = packageOf(specifier);
  if (!runtime.has(name)) {
    const reason = development.has(name)
      ? `'${name}' is a devDependency, so Metro will not have it`
      : `'${name}' is not declared in mobile/package.json`;
    failures.push(`${site}: ${reason}`);
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
