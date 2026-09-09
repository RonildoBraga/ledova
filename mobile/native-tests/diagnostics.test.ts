import { failureCategory, NativeProbeAssertion } from './diagnostics';
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

it('distinguishes an actual assertion from fixed native error categories', () => {
  expect(failureCategory(new NativeProbeAssertion())).toBe('assertion');
  expect(failureCategory({ code: 'ERR_KEY_CHAIN' })).toBe('native-keychain');
  expect(failureCategory({ code: 'ERR_FUNCTION_CALL' })).toBe('native-function');
});

it('never copies secret-bearing messages, arbitrary codes or object values into diagnostics', () => {
  for (const error of [
    new Error('synthetic-secret'),
    { code: 'synthetic-secret', message: 'synthetic-secret', value: 'synthetic-secret' },
    'synthetic-secret',
    null,
    undefined,
  ]) {
    expect(failureCategory(error)).toBe('unknown');
  }
  expect(failureCategory({ code: 'ERR_FUNCTION_CALL', message: 'synthetic-secret' })).toBe('native-function');
});

it('the actual probe retains the fixed failure stage and category while successful controls pass', async () => {
  const source = fs.readFileSync(path.join(__dirname, 'index.tsx'), 'utf8');
  const start = source.indexOf('  async function check(');
  const end = source.indexOf('\n  await check(', start);
  expect(start).toBeGreaterThan(0);
  expect(end).toBeGreaterThan(start);
  const code = ts.transpileModule(source.slice(start, end), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const checks: unknown[] = [];
  const check = new Function('checks', 'failureCategory', `${code}\nreturn check;`)(checks, failureCategory) as (
    name: string,
    action: (stage: (name: string) => void) => void,
  ) => Promise<void>;
  await check('synthetic-native-failure', (stage) => {
    stage('initial-sign-out');
    throw { code: 'ERR_FUNCTION_CALL', message: 'synthetic-secret' };
  });
  await check('synthetic-assertion', () => {
    throw new NativeProbeAssertion();
  });
  await check('synthetic-success', () => undefined);
  expect(checks).toEqual([
    {
      name: 'synthetic-native-failure',
      passed: false,
      failure: { category: 'native-function', stage: 'initial-sign-out' },
    },
    { name: 'synthetic-assertion', passed: false, failure: { category: 'assertion', stage: 'check' } },
    { name: 'synthetic-success', passed: true },
  ]);
});
