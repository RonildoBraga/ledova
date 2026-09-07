import { readdir, readFile } from 'node:fs/promises';
import { createRequire, isBuiltin } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const MOBILE = path.resolve(import.meta.dirname, '..');
const REPO = path.resolve(MOBILE, '..');
const WORKSPACE = path.join(REPO, 'packages');
const resolver = createRequire(path.join(MOBILE, 'index.ts'));

const SOURCE_FILE = /\.(tsx?|jsx?|mjs|cjs)$/;

const SPECIFIER =
  /(?<!['"`\w$])(?:from|import)\s+['"]([^'"\n]+)['"]|(?<!['"`\w$])(?:import|require)\s*\(\s*['"]([^'"\n]+)['"]/g;

const manifest = JSON.parse(await readFile(path.join(MOBILE, 'package.json'), 'utf8'));
const runtime = new Set(Object.keys(manifest.dependencies ?? {}));
const development = new Set(Object.keys(manifest.devDependencies ?? {}));
const metroConfig = await readFile(path.join(MOBILE, 'metro.config.js'), 'utf8');

const { default: jestConfig } = await import(path.join(MOBILE, 'jest.config.js'));

const { default: metro } = await import(path.join(MOBILE, 'metro.config.js'));
const aliases = metro.resolver?.extraNodeModules ?? {};

if (!Array.isArray(jestConfig.testMatch) || jestConfig.testMatch.length === 0) {
  console.error('jest.config.js declares no testMatch, so a test file cannot be told from bundled code.');
  process.exit(1);
}

const TEST_FILE = new RegExp(
  jestConfig.testMatch
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
    else if (SOURCE_FILE.test(entry.name)) yield full;
  }
}

async function* workspaceFiles() {
  for (const entry of await readdir(WORKSPACE, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const src = path.join(WORKSPACE, entry.name, 'src');
    try {
      yield* sourceFiles(src);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
}

async function* bundledFiles() {
  yield* sourceFiles(path.join(MOBILE, 'src'));
  for (const entry of await readdir(MOBILE, { withFileTypes: true })) {
    if (!entry.isFile()) continue;
    if (/\.config\.[cm]?[jt]s$/.test(entry.name)) continue;
    if (SOURCE_FILE.test(entry.name)) yield path.join(MOBILE, entry.name);
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

const workspaceSites = new Map();

for await (const file of workspaceFiles()) {
  const text = await readFile(file, 'utf8');
  for (const match of text.matchAll(SPECIFIER)) {
    const specifier = match[1] ?? match[2];
    if (specifier.startsWith('.') || specifier.startsWith('/')) continue;
    if (!workspaceSites.has(specifier)) {
      workspaceSites.set(specifier, `${path.relative(REPO, file)}:${lineOf(text, match.index)}`);
    }
  }
}

for (const [specifier, site] of [...workspaceSites].sort()) {
  const name = packageOf(specifier);
  if (isBuiltin(specifier) || aliases[name] !== undefined) {
    const target = aliases[name];
    if (target !== undefined && !path.resolve(target).startsWith(path.join(MOBILE, 'node_modules') + path.sep)) {
      failures.push(
        `${site}: '${name}' is aliased to ${path.relative(REPO, path.resolve(target))}, outside mobile/node_modules`,
      );
    }
    continue;
  }
  failures.push(
    `${site}: '${name}' has no metro.config.js extraNodeModules alias, so Metro cannot resolve it from packages/`,
  );
}

if (failures.length > 0) {
  console.error(`Mobile imports that mobile/node_modules cannot satisfy (${failures.length}):\n`);
  for (const failure of failures) console.error(`  ${failure}`);
  console.error(
    '\nMetro walks up from the importing file, so a file in packages/ reaches neither mobile/node_modules' +
      '\nnor the repo root. A green tsc does not mean the bundle resolves; only an export does.',
  );
  process.exit(1);
}

console.log(
  `Mobile resolution clean: ${sites.size} runtime specifiers from mobile/, ` +
    `${workspaceSites.size} from packages/, all reaching mobile/node_modules.`,
);
