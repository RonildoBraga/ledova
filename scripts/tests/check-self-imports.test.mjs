import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { checkSelfImports } from '../check-self-imports.mjs';
import { sourceImports } from '../source-imports.mjs';

const require = createRequire(new URL('../../packages/shared/package.json', import.meta.url));
const ts = require('typescript');

test('imports, re-exports, require and import types are all source references', () => {
  const source = [
    'import "@sample/own";',
    'import { value } from "@sample/own/subpath";',
    'export * from "@sample/own";',
    'const lazy = import("@sample/own");',
    'const required = require(`@sample/own`);',
    'import alias = require("@sample/own");',
    'type Value = import("@sample/own").Value;',
  ].join('\n');
  assert.deepEqual(sourceImports(ts, source, 'test.ts').map(({ line }) => line), [1, 2, 3, 4, 5, 6, 7]);
});

test('comments, strings, templates, regexes and JSX text do not invent imports', () => {
  const source = [
    '// import { value } from "@sample/own";',
    '/* require("@sample/own") */',
    'const quoted = \'import { value } from "@sample/own"\';',
    'const template = `import "@sample/own"`;',
    'const regex = /import "@sample\\/own"/;',
    'const element = <p>import "@sample/own"</p>;',
    'const real = import("another-package");',
  ].join('\n');
  assert.deepEqual(sourceImports(ts, source, 'test.tsx'), [{ specifier: 'another-package', line: 7 }]);
});

test('an actual import inside a template expression is still an import', () => {
  assert.deepEqual(sourceImports(ts, 'const value = `${import("@sample/own")}`;', 'test.ts'), [
    { specifier: '@sample/own', line: 1 },
  ]);
});

test('the package manifest supplies its name and tests are checked alongside source', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'ledova-self-import-'));
  try {
    const pkg = path.join(root, 'packages', 'different-directory');
    await mkdir(path.join(pkg, 'tests'), { recursive: true });
    await mkdir(path.join(pkg, 'node_modules'), { recursive: true });
    await writeFile(path.join(pkg, 'package.json'), JSON.stringify({ name: '@renamed/package' }));
    await writeFile(path.join(pkg, 'index.ts'), 'export * from "./local";');
    await writeFile(path.join(pkg, 'tests', 'example.test.ts'), 'import "@renamed/package/subpath";');
    await writeFile(path.join(pkg, 'node_modules', 'ignored.ts'), 'import "@renamed/package";');
    const result = await checkSelfImports(root);
    assert.equal(result.scanned, 2);
    assert.deepEqual(result.failures, [
      "packages/different-directory/tests/example.test.ts:1: '@renamed/package/subpath' imports its own package; use a relative path.",
    ]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
