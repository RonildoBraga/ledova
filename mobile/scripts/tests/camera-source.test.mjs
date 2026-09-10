import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import {
  cameraSources,
  mobileRoot,
  prepareCamera,
  installCameraProbe,
  restoreCameraProbe,
} from '../prepare-camera-android.mjs';

const hash = (value) => createHash('sha256').update(value).digest('hex');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-camera-source-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const { camera, manifest } = cameraSources();
  fs.mkdirSync(path.join(root, 'patches'), { recursive: true });
  fs.copyFileSync(
    path.join(mobileRoot, 'patches/expo-camera-17.0.10.json'),
    path.join(root, 'patches/expo-camera-17.0.10.json'),
  );
  fs.copyFileSync(path.join(mobileRoot, 'package.json'), path.join(root, 'package.json'));
  const target = path.join(root, 'node_modules/expo-camera');
  fs.mkdirSync(target, { recursive: true });
  fs.copyFileSync(path.join(camera, 'package.json'), path.join(target, 'package.json'));
  fs.copyFileSync(path.join(camera, 'expo-module.config.json'), path.join(target, 'expo-module.config.json'));
  fs.mkdirSync(path.join(target, 'android'), { recursive: true });
  fs.copyFileSync(path.join(camera, 'android/build.gradle'), path.join(target, 'android/build.gradle'));
  fs.cpSync(
    path.join(mobileRoot, 'native-tests/android/camera-window'),
    path.join(root, 'native-tests/android/camera-window'),
    { recursive: true },
  );
  for (const file of manifest.files) {
    let source = fs.readFileSync(path.join(camera, file.path), 'utf8');
    if (hash(source) === file.afterSha256) {
      for (const change of [...file.replacements].reverse()) source = source.replace(change.after, change.before);
    }
    assert.equal(hash(source), file.beforeSha256);
    fs.mkdirSync(path.dirname(path.join(target, file.path)), { recursive: true });
    fs.writeFileSync(path.join(target, file.path), source);
  }
  return { root, target, manifest };
}

test('direct verification refuses pristine source; explicit application is exact and repeatable', (t) => {
  const { root, target, manifest } = fixture(t);
  assert.throws(() => prepareCamera('verify', root), /Run Android prebuild/);
  const applied = prepareCamera('apply', root);
  assert.deepEqual(prepareCamera('verify', root), applied);
  assert.deepEqual(prepareCamera('apply', root), applied);
  for (const file of manifest.files)
    assert.equal(hash(fs.readFileSync(path.join(target, file.path))), file.afterSha256);
});

test('the reviewable unified patch produces the same declared source bytes', (t) => {
  const { target, manifest } = fixture(t);
  const patch = path.join(mobileRoot, 'patches/expo-camera-17.0.10.patch');
  const result = spawnSync('git', ['apply', patch], { cwd: target, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  for (const file of manifest.files)
    assert.equal(hash(fs.readFileSync(path.join(target, file.path))), file.afterSha256);
});

test('publication default cannot certify patched source', (t) => {
  const { root } = fixture(t);
  prepareCamera('apply', root);
  const packagePath = path.join(root, 'package.json');
  const pkg = JSON.parse(fs.readFileSync(packagePath));
  delete pkg.expo.autolinking.android.buildFromSource;
  fs.writeFileSync(packagePath, JSON.stringify(pkg));
  assert.throws(() => prepareCamera('verify', root), /must build from reviewed source/);
});

test('unexpected source refuses without partially applying another file', (t) => {
  const { root, target, manifest } = fixture(t);
  const first = path.join(target, manifest.files[0].path);
  const original = fs.readFileSync(first);
  fs.appendFileSync(path.join(target, manifest.files[1].path), '\n');
  assert.throws(() => prepareCamera('apply', root), /differs from the reviewed upstream/);
  assert.deepEqual(fs.readFileSync(first), original);
});

test('package version drift refuses even with unchanged Kotlin', (t) => {
  const { root, target } = fixture(t);
  const pkg = JSON.parse(fs.readFileSync(path.join(target, 'package.json')));
  pkg.version = '17.0.11';
  fs.writeFileSync(path.join(target, 'package.json'), JSON.stringify(pkg));
  assert.throws(() => prepareCamera('apply', root), /before changing its version/);
});

test('an external camera installation is never patched', (t) => {
  const { root, target } = fixture(t);
  const other = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-camera-external-'));
  t.after(() => fs.rmSync(other, { recursive: true, force: true }));
  fs.renameSync(target, path.join(other, 'camera'));
  fs.symlinkSync(path.join(other, 'camera'), target);
  assert.throws(() => prepareCamera('apply', root), /owned local installation/);
});

test('an external dependency directory is never patched', (t) => {
  const { root } = fixture(t);
  const other = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-camera-modules-'));
  t.after(() => fs.rmSync(other, { recursive: true, force: true }));
  fs.renameSync(path.join(root, 'node_modules'), path.join(other, 'node_modules'));
  fs.symlinkSync(path.join(other, 'node_modules'), path.join(root, 'node_modules'));
  assert.throws(() => prepareCamera('apply', root), /shared dependency directory/);
});

test('ordinary artifact inspection requires camera markers and refuses probe hooks', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-camera-dex-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const artifact = path.join(root, 'synthetic-markers.apk');
  const markers = [
    'Lexpo/modules/camera/ExpoCameraView;',
    'Lexpo/modules/ledovacamerawindow/LedovaCameraWindowView;',
    'cameraWindowRevoked',
    'hasCameraWindow',
  ];
  for (const [values, exit, message] of [
    [markers, 0, 'camera_class_descriptors'],
    [markers.slice(1), 1, 'missing native class descriptor'],
    [markers.slice(0, 3), 1, 'reviewed native guard'],
    [[...markers, 'LedovaCameraWindowProbe'], 1, 'native test hooks'],
  ]) {
    const create = spawnSync(
      'python3',
      [
        '-c',
        'import sys, zipfile\nwith zipfile.ZipFile(sys.argv[1], "w") as z:\n z.writestr("classes.dex", sys.argv[2])',
        artifact,
        values.join('\n'),
      ],
      { encoding: 'utf8' },
    );
    assert.equal(create.status, 0, create.stderr);
    const inspect = spawnSync('python3', [path.join(mobileRoot, 'scripts/check-camera-binary.py'), artifact], {
      encoding: 'utf8',
    });
    assert.equal(inspect.status, exit, inspect.stderr);
    assert.ok(`${inspect.stdout}${inspect.stderr}`.includes(message));
  }
});

for (const mode of ['red', 'green']) {
  test(`only the exact ${mode} native body and probe entrypoint are accepted`, (t) => {
    const { root } = fixture(t);
    prepareCamera('apply', root);
    const files = installCameraProbe(mode, root);
    const environment = { LEDOVA_CAMERA_PROBE: mode, ENTRY_FILE: 'native-tests/camera-window.tsx' };
    assert.equal(prepareCamera('verify', root, environment).length, 2);
    assert.throws(() => prepareCamera('verify', root, {}), /absent from ordinary/);
    assert.throws(
      () => prepareCamera('verify', root, { ...environment, ENTRY_FILE: 'index.ts' }),
      /exact probe entrypoint/,
    );
    assert.throws(
      () => prepareCamera('verify', root, { ...environment, LEDOVA_CAMERA_PROBE: mode === 'red' ? 'green' : 'red' }),
      /declared old\/new implementation/,
    );
    fs.appendFileSync(files[0].filename, '\n');
    assert.throws(() => prepareCamera('verify', root, environment), /declared old\/new implementation/);
    assert.throws(() => restoreCameraProbe(files, root), /changed during execution/);
    fs.writeFileSync(files[0].filename, files[0].source);
    restoreCameraProbe(files, root);
    assert.equal(prepareCamera('verify', root, {}).length, 2);
  });
}
