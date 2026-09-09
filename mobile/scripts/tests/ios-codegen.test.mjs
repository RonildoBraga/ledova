import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { test } from 'node:test';

const mobile = path.resolve(import.meta.dirname, '../..');
const require = createRequire(path.join(mobile, 'package.json'));
const withMobileSecurity = require(path.join(mobile, 'plugins/withMobileSecurity.cjs'));
const native = path.dirname(require.resolve('react-native/package.json'));
const generator = path.join(native, 'scripts/codegen/generate-artifacts-executor');
const { generateReactCodegenPodspec } = require(path.join(generator, 'generateReactCodegenPodspec'));
const { generateCustomURLHandlers } = require(path.join(generator, 'generateCustomURLHandlers'));
const { generateSchemaInfos } = require(path.join(generator, 'generateSchemaInfos'));
const manifest = JSON.parse(fs.readFileSync(path.join(mobile, 'package.json'), 'utf8'));
const helper = path.join(mobile, 'plugins/native/codegen-inputs.rb');

function fixture(hasSpec, run) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-codegen-')));
  const previous = process.cwd();
  try {
    const ios = path.join(root, 'ios');
    const output = path.join(ios, 'build/generated/ios');
    fs.mkdirSync(path.join(ios, 'Ledova.xcodeproj'), { recursive: true });
    fs.mkdirSync(path.join(root, 'src'), { recursive: true });
    fs.mkdirSync(output, { recursive: true });
    const packageJson = { name: 'codegen-fixture', codegenConfig: manifest.codegenConfig };
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify(packageJson));
    if (hasSpec) {
      fs.writeFileSync(
        path.join(root, 'src/NativeProbe.ts'),
        `import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';
export interface Spec extends TurboModule { ping(): string; }
export default TurboModuleRegistry.getEnforcing<Spec>('NativeProbe');
`,
      );
    }
    process.chdir(ios);
    generateReactCodegenPodspec(root, packageJson, output, ios);
    const libraries = [{ name: packageJson.name, config: manifest.codegenConfig, libraryPath: root }];
    generateCustomURLHandlers(libraries, output);
    const schemas = generateSchemaInfos(libraries);
    const podspec = fs.readFileSync(path.join(output, 'ReactCodegen.podspec'), 'utf8');
    const inputs = JSON.parse(podspec.match(/'input_files' => (\[[\s\S]*?\]),/)[1]);
    const provider = fs.readFileSync(path.join(output, 'RCTModulesConformingToProtocolsProvider.mm'), 'utf8');
    run({ inputs, schemaModules: Object.keys(schemas[0].schema.modules), provider });
  } finally {
    process.chdir(previous);
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function correctTargets(targets) {
  const script = `require 'json'
require ARGV.fetch(0)
Phase = Struct.new(:name, :input_paths, :output_paths, :shell_script)
Target = Struct.new(:name, :shell_script_build_phases)
Project = Struct.new(:targets)
Installer = Struct.new(:pods_project)
targets = JSON.parse(STDIN.read).map do |target|
  phases = target.fetch('phases').map { |phase| Phase.new(*phase.values_at('name', 'inputs', 'outputs', 'script')) }
  Target.new(target.fetch('name'), phases)
end
installer = Installer.new(Project.new(targets))
2.times { LedovaCodegen.remove_directory_input(installer) }
puts JSON.generate(targets.map do |target|
  { name: target.name, phases: target.shell_script_build_phases.map do |phase|
    { name: phase.name, inputs: phase.input_paths, outputs: phase.output_paths, script: phase.shell_script }
  end }
end)
`;
  return JSON.parse(execFileSync('ruby', ['-e', script, helper], { input: JSON.stringify(targets), timeout: 10000 }));
}

function target(inputs, name = 'ReactCodegen', phaseName = '[CP-User] Generate Specs') {
  return {
    name,
    phases: [{ name: phaseName, inputs, outputs: ['${DERIVED_FILE_DIR}/react-codegen.log'], script: 'generate-specs' }],
  };
}

async function podfile(contents) {
  const config = withMobileSecurity({ name: 'Ledova', slug: 'ledova' });
  const result = await config.mods.ios.podfile({ ...config, modResults: { contents }, modRequest: {} });
  return result.modResults.contents;
}

test('registration-only codegen drops the accidental directory and retains the native handler provider', () => {
  fixture(false, ({ inputs, schemaModules, provider }) => {
    assert.deepEqual(schemaModules, []);
    assert.match(provider, /@"LedovaHTTPRequestHandler"/);
    const [corrected] = correctTargets([target(inputs)]);
    assert.deepEqual(corrected, target([]));
  });
});

test('a genuine native spec retains its dependency and handler registration', () => {
  fixture(true, ({ inputs, schemaModules, provider }) => {
    assert.deepEqual(schemaModules, ['NativeProbe']);
    assert.deepEqual(inputs, ['${PODS_ROOT}/../../src/NativeProbe.ts']);
    assert.match(provider, /@"LedovaHTTPRequestHandler"/);
    const original = target(inputs);
    assert.deepEqual(correctTargets([original]), [original]);
  });
});

test('only the exact directory input in the selected target and phase changes', () => {
  const directory = '${PODS_ROOT}/..';
  const realInputs = ['${PODS_ROOT}/../../src/NativeProbe.ts', '${PODS_ROOT}/../..', '${PODS_ROOT}/../input.json'];
  const unrelatedTarget = target([directory], 'OtherTarget');
  const unrelatedPhase = target([directory], 'ReactCodegen', 'OtherPhase');
  const [corrected, otherTarget, otherPhase] = correctTargets([
    target([directory, ...realInputs]),
    unrelatedTarget,
    unrelatedPhase,
  ]);
  assert.deepEqual(corrected, target(realInputs));
  assert.deepEqual(otherTarget, unrelatedTarget);
  assert.deepEqual(otherPhase, unrelatedPhase);
});

test('the Podfile hook is inserted once and retains the existing post-install body', async () => {
  const original = 'target "Ledova" do\n  post_install do |installer|\n    existing_hook(installer)\n  end\nend\n';
  const first = await podfile(original);
  const second = await podfile(first);
  assert.equal(second, first);
  assert.equal(first.match(/LedovaCodegen\.remove_directory_input\(installer\)/g)?.length, 1);
  assert.match(first, /post_install do \|installer\|\n[\s\S]*require_relative '\.\.\/plugins\/native\/codegen-inputs'/);
  assert.match(first, /existing_hook\(installer\)\n {2}end\nend\n$/);
  execFileSync('ruby', ['-c'], { input: first, timeout: 10000 });
});

test('missing or ambiguous Podfile hooks fail clearly, including after an earlier insertion', async () => {
  const hook = 'post_install do |installer|\nend\n';
  const message = /expected one post_install hook/;
  await assert.rejects(podfile('target "Ledova" do\nend\n'), message);
  await assert.rejects(podfile(hook + hook), message);
  const previous = await podfile(hook);
  await assert.rejects(
    podfile(previous.replace('post_install do |installer|', 'unsupported_hook do |installer|')),
    message,
  );
});
