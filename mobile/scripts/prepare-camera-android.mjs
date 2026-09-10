import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {
  instrumentCamera,
  removeCameraInstrumentation,
  probeEntry,
  probeSupportPath,
  probeSupport,
} from './camera-probe-source.mjs';

export const mobileRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const hash = (value) => createHash('sha256').update(value).digest('hex');

export function cameraSources(root = mobileRoot) {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'patches/expo-camera-17.0.10.json'), 'utf8'));
  const camera = fs.realpathSync(path.join(root, 'node_modules/expo-camera'));
  const ownedModules = fs.realpathSync(path.join(root, 'node_modules'));
  assert.equal(
    ownedModules,
    path.join(fs.realpathSync(root), 'node_modules'),
    'Camera preparation refuses a shared dependency directory.',
  );
  assert.ok(
    camera.startsWith(`${ownedModules}${path.sep}`),
    'Camera preparation requires an owned local installation.',
  );
  const pkg = JSON.parse(fs.readFileSync(path.join(camera, 'package.json'), 'utf8'));
  const module = JSON.parse(fs.readFileSync(path.join(camera, 'expo-module.config.json'), 'utf8'));
  assert.deepEqual(module.android, manifest.android, 'Camera Gradle project/publication identity changed.');
  assert.equal(
    hash(fs.readFileSync(path.join(camera, 'android/build.gradle'))),
    manifest.gradleSha256,
    'Camera Gradle inputs changed.',
  );
  assert.equal(pkg.version, manifest.version, 'Review the camera patch before changing its version.');
  const autolinking = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).expo?.autolinking;
  assert.ok(autolinking?.android?.buildFromSource?.includes('expo-camera'), 'Camera must build from reviewed source.');
  return { camera, manifest };
}

export function patchedSource(source, file) {
  if (hash(source) === file.afterSha256) return source;
  assert.equal(hash(source), file.beforeSha256, 'Camera source differs from the reviewed upstream file.');
  for (const replacement of file.replacements) {
    assert.equal(source.split(replacement.before).length - 1, 1, 'Camera patch anchor must occur exactly once.');
    source = source.replace(replacement.before, replacement.after);
  }
  assert.equal(hash(source), file.afterSha256, 'Camera patch output differs from its reviewed identity.');
  return source;
}

export function prepareCamera(command, root = mobileRoot, environment = process.env) {
  assert.ok(['apply', 'verify'].includes(command), 'Use apply or verify.');
  const { camera, manifest } = cameraSources(root);
  const mode = environment.LEDOVA_CAMERA_PROBE;
  const support = path.join(camera, probeSupportPath);
  if (mode !== undefined) {
    assert.ok(mode === 'red' || mode === 'green', 'Unknown camera probe mode.');
    assert.equal(command, 'verify', 'Probe preparation must not replace the ordinary patch operation.');
    assert.equal(environment.ENTRY_FILE, probeEntry, 'Camera test hooks require the exact probe entrypoint.');
    assert.equal(
      fs.readFileSync(support, 'utf8'),
      probeSupport(root),
      'Camera probe support differs from reviewed source.',
    );
    return manifest.files.map((file) => {
      const source = fs.readFileSync(path.join(camera, file.path), 'utf8');
      const body = removeCameraInstrumentation(file.path, source);
      assert.equal(
        hash(body),
        mode === 'red' ? file.beforeSha256 : file.afterSha256,
        'Camera probe body differs from the declared old/new implementation.',
      );
      assert.equal(source, instrumentCamera(file.path, body), 'Camera probe transform differs from reviewed source.');
      return { path: file.path, sha256: hash(source) };
    });
  }
  assert.ok(!fs.existsSync(support), 'Camera probe support must be absent from ordinary builds.');
  const checks = manifest.files.map((file) => {
    const filename = path.join(camera, file.path);
    const source = fs.readFileSync(filename, 'utf8');
    const result = patchedSource(source, file);
    if (command === 'verify')
      assert.equal(hash(source), file.afterSha256, 'Run Android prebuild before compiling camera source.');
    return { filename, source: result, sha256: file.afterSha256 };
  });
  if (command === 'apply') {
    for (const file of checks) fs.writeFileSync(file.filename, file.source);
  }
  return checks.map(({ filename, sha256 }) => ({ path: path.relative(camera, filename), sha256 }));
}

export function installCameraProbe(mode, root = mobileRoot) {
  assert.ok(mode === 'red' || mode === 'green');
  prepareCamera('verify', root, {});
  const { camera, manifest } = cameraSources(root);
  const files = manifest.files.map((file) => {
    const filename = path.join(camera, file.path);
    const original = fs.readFileSync(filename, 'utf8');
    let body = original;
    if (mode === 'red') {
      for (const change of [...file.replacements].reverse()) body = body.replace(change.after, change.before);
      assert.equal(hash(body), file.beforeSha256);
    }
    return { filename, original, source: instrumentCamera(file.path, body) };
  });
  files.push({ filename: path.join(camera, probeSupportPath), original: null, source: probeSupport(root) });
  for (const file of files) fs.writeFileSync(file.filename, file.source);
  prepareCamera('verify', root, { LEDOVA_CAMERA_PROBE: mode, ENTRY_FILE: probeEntry });
  return files;
}

export function restoreCameraProbe(files, root = mobileRoot) {
  for (const file of files) {
    assert.equal(fs.readFileSync(file.filename, 'utf8'), file.source, 'Camera probe source changed during execution.');
  }
  for (const file of files) {
    if (file.original === null) fs.rmSync(file.filename);
    else fs.writeFileSync(file.filename, file.original);
  }
  prepareCamera('verify', root, {});
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(JSON.stringify({ files: prepareCamera(process.argv[2]) }));
}
