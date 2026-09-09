import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { test } from 'node:test';

const mobile = path.resolve(import.meta.dirname, '../..');

function processTable() {
  return execFileSync('ps', ['-axo', 'pid=,pgid=,stat='], {
    encoding: 'utf8',
    timeout: 15000,
    killSignal: 'SIGKILL',
  })
    .trim()
    .split('\n')
    .map((row) => {
      const [pid, group, state] = row.trim().split(/\s+/);
      return { pid: Number(pid), group: Number(group), state };
    });
}

function fixture(context, behavior, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ledova-command-timeout-')));
  const output = path.join(root, 'results');
  const groups = [];
  context.after(() => {
    for (const group of groups) {
      try {
        process.kill(-group, 'SIGKILL');
      } catch (error) {
        if (error.code !== 'ESRCH') throw error;
      }
    }
    fs.rmSync(root, { recursive: true, force: true });
  });
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.mkdirSync(path.join(root, 'bin'));
  fs.copyFileSync(path.join(mobile, 'app.json'), path.join(root, 'app.json'));
  let runner = fs.readFileSync(path.join(mobile, 'scripts/native-smoke.mjs'), 'utf8');
  assert.equal(runner.match(/\* 60 \* 1000/g)?.length, 1);
  runner = runner.replace('* 60 * 1000', '* 100');
  const build = "await build('ordinary-release-build', { ENTRY_FILE: 'index.ts' });";
  assert.ok(runner.includes(build));
  runner = runner.replace(
    build,
    `${build}\nfs.writeFileSync(path.join(directory, 'build-resolved'), 'yes');\nthrow new Error('Synthetic post-build boundary.');`,
  );
  fs.writeFileSync(path.join(root, 'scripts/native-smoke.mjs'), runner);
  let server = fs.readFileSync(path.join(mobile, 'scripts/native-probe-server.mjs'), 'utf8');
  const create = 'fs.mkdirSync(directory, { recursive: true });';
  assert.ok(server.includes(create));
  server = server.replace(create, `${create}\nfs.writeFileSync(path.join(directory, 'pid'), String(process.pid));`);
  fs.writeFileSync(path.join(root, 'scripts/native-probe-server.mjs'), server);
  const script = `#!/usr/bin/env node
const fs = require('node:fs');
const { spawn } = require('node:child_process');
fs.writeFileSync('command.json', JSON.stringify({ pid: process.pid, started: Date.now() }));
${behavior}
`;
  fs.writeFileSync(path.join(root, 'bin/xcodebuild'), script, { mode: 0o700 });
  const result = spawnSync(process.execPath, [path.join(root, 'scripts/native-smoke.mjs'), 'ios', output], {
    cwd: root,
    env: {
      ...process.env,
      PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH}`,
      IOS_SIMULATOR_UDID: 'synthetic-command-control',
    },
    encoding: 'utf8',
    timeout: 150000,
    killSignal: 'SIGTERM',
  });
  const commandFile = path.join(root, 'command.json');
  const serverFile = path.join(output, 'server/pid');
  const command = fs.existsSync(commandFile) ? JSON.parse(fs.readFileSync(commandFile, 'utf8')) : null;
  const serverPid = fs.existsSync(serverFile) ? Number(fs.readFileSync(serverFile, 'utf8')) : null;
  if (command) groups.push(command.pid);
  if (serverPid) groups.push(serverPid);
  assert.equal(result.error, undefined);
  assert.equal(result.status, 1);
  assert.ok(command && serverPid, result.stderr);
  const rows = processTable();
  assert.ok(!rows.some(({ group, state }) => groups.includes(group) && !state.startsWith('Z')));
  for (const pid of groups) assert.ok(!rows.some((row) => row.pid === pid), 'Direct children must be reaped.');
  check({ root, output, result, command });
}

test('a hung Xcode command times out explicitly and stops its server, command and descendant', (context) => {
  fixture(
    context,
    `process.on('SIGTERM', () => fs.writeFileSync('command-term', String(Date.now())));
spawn(process.execPath, ['-e', "require('node:fs').writeFileSync('descendant-started', 'yes'); process.on('SIGTERM', () => {}); setInterval(() => {}, 1000);"], { stdio: 'ignore' });
setInterval(() => {}, 1000);`,
    ({ root, output, result, command }) => {
      assert.ok(fs.existsSync(path.join(root, 'descendant-started')));
      assert.ok(!fs.existsSync(path.join(output, 'build-resolved')));
      assert.match(result.stderr, /ordinary-release-build timed out after 4\.5 seconds/);
      assert.doesNotMatch(result.stderr, /failed \(null\)/);
      const terminated = Number(fs.readFileSync(path.join(root, 'command-term'), 'utf8'));
      assert.ok(terminated - command.started >= 4000);
      assert.ok(terminated - command.started < 15000);
    },
  );
});

test('an Xcode command can succeed past the former deadline', (context) => {
  fixture(context, 'setTimeout(() => process.exit(0), 3500);', ({ output, result }) => {
    assert.ok(fs.existsSync(path.join(output, 'build-resolved')), result.stderr);
    assert.match(result.stderr, /Synthetic post-build boundary/);
    assert.doesNotMatch(result.stderr, /timed out/);
  });
});

test('a nonzero command exit remains distinct from a timeout', (context) => {
  fixture(context, 'process.exit(23);', ({ output, result }) => {
    assert.ok(!fs.existsSync(path.join(output, 'build-resolved')));
    assert.match(result.stderr, /ordinary-release-build failed \(23\)/);
    assert.doesNotMatch(result.stderr, /timed out/);
  });
});

test('a command signal is reported by name without being labelled a timeout', (context) => {
  fixture(context, "process.kill(process.pid, 'SIGTERM');", ({ output, result }) => {
    assert.ok(!fs.existsSync(path.join(output, 'build-resolved')));
    assert.match(result.stderr, /ordinary-release-build failed \(SIGTERM\)/);
    assert.doesNotMatch(result.stderr, /timed out|failed \(null\)/);
  });
});
