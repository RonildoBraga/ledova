#!/usr/bin/env node

import { existsSync, readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const packageRoot = join(scriptDirectory, '..');
const scope = '@ledova';

const dependencyGraph = {
  'shared-constants': [],
  'shared-types': ['shared-constants'],
  'shared-utils': ['shared-constants', 'shared-types'],
  'shared-services': ['shared-constants', 'shared-types', 'shared-utils'],
};

function readPackage(packageName) {
  const manifestPath = join(packageRoot, 'packages', packageName, 'package.json');
  if (!existsSync(manifestPath)) {
    throw new Error(`Package manifest is missing: ${packageName}`);
  }
  return JSON.parse(readFileSync(manifestPath, 'utf8'));
}

function validateDependencyGraph() {
  const manifests = Object.fromEntries(
    Object.keys(dependencyGraph).map((packageName) => [packageName, readPackage(packageName)]),
  );
  const errors = [];

  for (const [packageName, expectedDependencies] of Object.entries(dependencyGraph)) {
    const manifest = manifests[packageName];
    const expectedName = `${scope}/${packageName}`;

    if (manifest.name !== expectedName) {
      errors.push(`${packageName}: expected package name ${expectedName}`);
    }
    if (manifest.private !== true) {
      errors.push(`${packageName}: package must remain private`);
    }
    if (manifest.license !== 'Apache-2.0') {
      errors.push(`${packageName}: expected Apache-2.0 license metadata`);
    }

    const declaredDependencies = manifest.dependencies ?? {};
    const expectedNames = new Set(expectedDependencies.map((dependency) => `${scope}/${dependency}`));

    for (const dependency of expectedDependencies) {
      const dependencyName = `${scope}/${dependency}`;
      const expectedVersion = `^${manifests[dependency].version}`;
      if (declaredDependencies[dependencyName] !== expectedVersion) {
        errors.push(
          `${packageName}: expected ${dependencyName} at ${expectedVersion}, found ${
            declaredDependencies[dependencyName] ?? 'missing'
          }`,
        );
      }
    }

    for (const dependencyName of Object.keys(declaredDependencies)) {
      if (dependencyName.startsWith(`${scope}/`) && !expectedNames.has(dependencyName)) {
        errors.push(`${packageName}: unexpected internal dependency ${dependencyName}`);
      }
    }
  }

  if (errors.length > 0) {
    for (const error of errors) {
      console.error(`PACKAGE_DEPENDENCY_ERROR: ${error}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log('PACKAGE_DEPENDENCIES_VALID');
}

try {
  validateDependencyGraph();
} catch (error) {
  console.error(`PACKAGE_DEPENDENCY_ERROR: ${error.message}`);
  process.exitCode = 1;
}
