import { readFile } from 'node:fs/promises';

const lockfile = JSON.parse(await readFile(new URL('../../package-lock.json', import.meta.url), 'utf8'));
const packages = lockfile.packages ?? {};

function findPackageEntries(name) {
  const suffix = `/node_modules/${name}`;
  return Object.entries(packages).filter(([path]) => path === `node_modules/${name}` || path.endsWith(suffix));
}

const reactEntries = findPackageEntries('react');
const reactDomEntries = findPackageEntries('react-dom');
const errors = [];

for (const [name, entries] of [
  ['react', reactEntries],
  ['react-dom', reactDomEntries],
]) {
  if (entries.length !== 1 || entries[0]?.[0] !== `node_modules/${name}`) {
    const locations = entries.map(([path, metadata]) => `${path}@${metadata.version}`).join(', ') || 'none';
    errors.push(`${name} must have one hoisted lockfile entry; found: ${locations}`);
  }
}

const reactVersion = reactEntries[0]?.[1]?.version;
const reactDomVersion = reactDomEntries[0]?.[1]?.version;
if (reactVersion && reactDomVersion && reactVersion !== reactDomVersion) {
  errors.push(`react and react-dom must match; found ${reactVersion} and ${reactDomVersion}`);
}

if (errors.length > 0) {
  console.error(`React dependency check failed:\n- ${errors.join('\n- ')}`);
  process.exit(1);
}

console.log(`React dependency check passed: react@${reactVersion} and react-dom@${reactDomVersion} are singletons.`);
