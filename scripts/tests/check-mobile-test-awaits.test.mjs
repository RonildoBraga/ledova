import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';

const MOBILE = path.resolve(import.meta.dirname, '../../mobile');
const require = createRequire(path.join(MOBILE, 'package.json'));
const { ESLint } = require('eslint');

test('a missing press await before an absence assertion is rejected by the real mobile lint config', async () => {
  const filePath = path.join(MOBILE, 'src/screens/home/components/AssetAllocationCard.test.tsx');
  const source = await readFile(filePath, 'utf8');
  const awaited = "await fireEvent.press(view.getByLabelText('Hide USDC by chain'));";
  assert.equal(source.split(awaited).length, 2, 'the toggle must await its closing press');
  const eslint = new ESLint({ cwd: MOBILE });
  const positive = await eslint.lintText(source, { filePath });
  assert.equal(positive[0].errorCount, 0, JSON.stringify(positive[0].messages));

  const negative = await eslint.lintText(source.replace(awaited, awaited.replace('await ', '')), { filePath });
  const failures = negative[0].messages.filter(({ ruleId }) => ruleId === '@typescript-eslint/no-floating-promises');
  assert.equal(failures.length, 1, JSON.stringify(negative[0].messages));
  assert.equal(failures[0].line, source.slice(0, source.indexOf(awaited)).split('\n').length);
});
