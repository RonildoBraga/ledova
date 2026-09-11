import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import { setTimeout, clearTimeout, setInterval, clearInterval } from 'node:timers';

const directory = path.resolve(process.argv[2]);
const host = process.argv[3] === 'ios' ? 'localhost' : '10.0.2.2';
fs.mkdirSync(directory, { recursive: true });
function certificateTool() {
  for (const directory of (process.env.PATH ?? '').split(path.delimiter)) {
    const candidate = path.resolve(directory, 'openssl');
    try {
      if (!fs.statSync(candidate).isFile()) continue;
      fs.accessSync(candidate, fs.constants.X_OK);
      return fs.realpathSync(candidate);
    } catch {
      continue;
    }
  }
  throw new Error('The native probe requires an executable OpenSSL on PATH.');
}
const executable = certificateTool();
const configuration = path.join(directory, 'openssl.cnf');
fs.writeFileSync(configuration, '[req]\ndistinguished_name=probe_name\n[probe_name]\n');

function openssl(stage, args) {
  console.log(stage);
  try {
    return execFileSync(executable, args, {
      cwd: directory,
      env: { ...process.env, OPENSSL_CONF: configuration },
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 30000,
      killSignal: 'SIGKILL',
    });
  } catch (error) {
    throw new Error(`Probe certificate tool failed during ${stage} (${error.code ?? error.status}).`);
  }
}

fs.writeFileSync(
  path.join(directory, 'certificate-tool.json'),
  JSON.stringify(
    {
      executable,
      version: openssl('certificate-tool-version', ['version', '-a']).toString(),
      configuration,
      configurationSha256: createHash('sha256').update(fs.readFileSync(configuration)).digest('hex'),
    },
    null,
    2,
  ),
);
openssl('generate-probe-ca', [
  'req',
  '-x509',
  '-newkey',
  'rsa:2048',
  '-nodes',
  '-sha256',
  '-days',
  '2',
  '-keyout',
  'ca.key',
  '-out',
  'ca.pem',
  '-subj',
  '/CN=Ledova synthetic native probe CA',
  '-addext',
  'basicConstraints=critical,CA:TRUE',
  '-addext',
  'keyUsage=critical,keyCertSign,cRLSign',
  '-addext',
  'subjectKeyIdentifier=hash',
  '-addext',
  'authorityKeyIdentifier=keyid:always',
]);
openssl('generate-server-request', [
  'req',
  '-newkey',
  'rsa:2048',
  '-nodes',
  '-keyout',
  'server.key',
  '-out',
  'server.csr',
  '-subj',
  '/CN=localhost',
]);
fs.writeFileSync(
  path.join(directory, 'server.ext'),
  'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:10.0.2.2\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n',
);
openssl('sign-server-certificate', [
  'x509',
  '-req',
  '-in',
  'server.csr',
  '-CA',
  'ca.pem',
  '-CAkey',
  'ca.key',
  '-CAcreateserial',
  '-days',
  '2',
  '-sha256',
  '-out',
  'server.pem',
  '-extfile',
  'server.ext',
]);
openssl('generate-untrusted-certificate', [
  'req',
  '-x509',
  '-newkey',
  'rsa:2048',
  '-nodes',
  '-sha256',
  '-days',
  '2',
  '-keyout',
  'untrusted.key',
  '-out',
  'untrusted.pem',
  '-subj',
  '/CN=localhost',
  '-addext',
  'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:10.0.2.2',
  '-addext',
  'basicConstraints=critical,CA:FALSE',
  '-addext',
  'extendedKeyUsage=serverAuth',
  '-addext',
  'keyUsage=critical,digitalSignature,keyEncipherment',
]);
for (const key of ['ca.key', 'server.key', 'untrusted.key']) fs.chmodSync(path.join(directory, key), 0o600);
for (const name of ['ca', 'server', 'untrusted']) {
  fs.writeFileSync(
    path.join(directory, `${name}.public.txt`),
    openssl(`inspect-${name}-certificate`, [
      'x509',
      '-in',
      `${name}.pem`,
      '-noout',
      '-text',
      '-fingerprint',
      '-sha256',
    ]),
  );
}

const counts = {
  direct: 0,
  targetControl: 0,
  redirectTarget: 0,
  redirectBody: 0,
  redirectBearer: 0,
  http: 0,
  upload: 0,
  download: 0,
  stream: 0,
  cancelled: 0,
  untrusted: 0,
};
let destination;
const failureCategories = new Set(['assertion', 'native-keychain', 'native-function', 'unknown']);
const failureStages = new Set([
  'check',
  'initial-sign-out',
  'retired-marker-removal',
  'legacy-access-write',
  'legacy-refresh-write',
  'migrated-access-read',
  'migrated-refresh-read',
  'legacy-access-removal',
  'legacy-refresh-removal',
  'ordinary-session-write',
  'authenticated-request',
  'authenticated-response',
  'session-rotation',
  'rotated-refresh-read',
  'sign-out',
  'signed-out-session-read',
  'missing-ref',
  'missing-method',
  'inactive-admitted',
  'window-timeout',
  'window-generation',
  'method-assertion',
  'method-native-keychain',
  'method-native-function',
  'method-unknown',
]);

function handler(kind) {
  return (request, response) => {
    const route = new URL(request.url, 'https://localhost').pathname;
    if (route === '/reset') {
      for (const key of Object.keys(counts)) counts[key] = 0;
      fs.rmSync(path.join(directory, 'result.json'), { force: true });
      response.end('{}');
      return;
    }
    if (kind === 'http') counts.http++;
    if (kind === 'untrusted') counts.untrusted++;
    if (route === '/target') counts.redirectTarget++;
    if (route === '/target-control') counts.targetControl++;
    if (route === '/stream') {
      counts.stream++;
      response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
      response.write('event: connected\ndata: {"sequence":1}\n\n');
      const timer = setTimeout(() => response.write('event: connected\ndata: {"sequence":2}\n\n'), 100);
      response.on('close', () => clearTimeout(timer));
      return;
    }
    if (route === '/slow') {
      response.writeHead(200, { 'Content-Type': 'application/octet-stream' });
      response.write('synthetic-');
      const timer = setInterval(() => response.write('progress-'), 50);
      response.on('close', () => {
        clearInterval(timer);
        counts.cancelled++;
      });
      return;
    }
    if (route === '/download') {
      counts.download++;
      response.writeHead(200, { 'Content-Type': 'application/octet-stream' });
      response.end('synthetic-fixture');
      return;
    }
    const chunks = [];
    let size = 0;
    request.on('data', (chunk) => {
      size += chunk.length;
      if (size > 65536) request.destroy();
      else chunks.push(chunk);
    });
    request.on('end', () => {
      const body = Buffer.concat(chunks).toString();
      if (route === '/target') {
        if (body.includes('synthetic-refresh-and-sign-in')) counts.redirectBody++;
        if (request.headers.authorization === 'Bearer synthetic-access') counts.redirectBearer++;
      }
      response.setHeader('Content-Type', 'application/json');
      if (route === '/redirect307' || route === '/redirect308') {
        response.writeHead(route === '/redirect307' ? 307 : 308, { Location: `${destination}/target` });
        response.end('{}');
        return;
      }
      if (route === '/report') {
        const parsed = JSON.parse(body);
        const checks = parsed.checks.map(({ name, passed, failure }) => ({
          name: String(name),
          passed: passed === true,
          ...(passed === false &&
            failureCategories.has(failure?.category) &&
            failureStages.has(failure?.stage) && {
              failure: { category: failure.category, stage: failure.stage },
            }),
        }));
        fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify({ checks, counts }, null, 2));
        response.end('{}');
        return;
      }
      if (route === '/upload') {
        counts.upload++;
        response.end(
          JSON.stringify({
            valid:
              body.includes('synthetic-fixture') && request.headers['content-type']?.includes('multipart/form-data'),
          }),
        );
        return;
      }
      if (route === '/direct') counts.direct++;
      response.end(
        JSON.stringify({
          authenticated: request.headers.authorization === 'Bearer synthetic-access',
          bodyReceived: body.includes('synthetic-'),
          access: 'synthetic-access',
          refresh: 'synthetic-refresh',
        }),
      );
    });
  };
}

const credentials = {
  key: fs.readFileSync(path.join(directory, 'server.key')),
  cert: fs.readFileSync(path.join(directory, 'server.pem')),
};
const servers = [
  https.createServer(credentials, handler('primary')),
  https.createServer(credentials, handler('target')),
  http.createServer(handler('http')),
  https.createServer(
    {
      key: fs.readFileSync(path.join(directory, 'untrusted.key')),
      cert: fs.readFileSync(path.join(directory, 'untrusted.pem')),
    },
    handler('untrusted'),
  ),
];
console.log('listen-probe-services');
await Promise.all(servers.map((server) => new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))));
const ports = servers.map((server) => server.address().port);
destination = `https://${host}:${ports[1]}`;
fs.writeFileSync(
  path.join(directory, 'config.json'),
  JSON.stringify(
    {
      apiUrl: `https://${host}:${ports[0]}`,
      targetUrl: destination,
      httpUrl: `http://${host === 'localhost' ? '127.0.0.1' : host}:${ports[2]}`,
      untrustedUrl: `https://${host}:${ports[3]}`,
    },
    null,
    2,
  ),
);
console.log('probe-services-ready');

process.on('SIGTERM', () => {
  for (const server of servers) {
    server.closeAllConnections();
    server.close();
  }
});
