import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import { setTimeout, clearTimeout, setInterval, clearInterval } from 'node:timers';

const directory = path.resolve(process.argv[2]);
const host = process.argv[3] === 'ios' ? 'localhost' : '10.0.2.2';
fs.mkdirSync(directory, { recursive: true });

function openssl(args) {
  execFileSync('openssl', args, { cwd: directory, stdio: ['ignore', 'ignore', 'pipe'] });
}

openssl([
  'req',
  '-x509',
  '-newkey',
  'rsa:2048',
  '-nodes',
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
]);
openssl([
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
  'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:10.0.2.2\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n',
);
openssl([
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
  '-out',
  'server.pem',
  '-extfile',
  'server.ext',
]);
openssl([
  'req',
  '-x509',
  '-newkey',
  'rsa:2048',
  '-nodes',
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
]);
for (const key of ['ca.key', 'server.key', 'untrusted.key']) fs.chmodSync(path.join(directory, key), 0o600);

const counts = {
  direct: 0,
  targetControl: 0,
  redirectTarget: 0,
  http: 0,
  upload: 0,
  download: 0,
  stream: 0,
  cancelled: 0,
  untrusted: 0,
};
let destination;

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
      response.setHeader('Content-Type', 'application/json');
      if (route === '/redirect307' || route === '/redirect308') {
        response.writeHead(route === '/redirect307' ? 307 : 308, { Location: `${destination}/target` });
        response.end('{}');
        return;
      }
      if (route === '/report') {
        const parsed = JSON.parse(body);
        const checks = parsed.checks.map(({ name, passed }) => ({ name: String(name), passed: passed === true }));
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

process.on('SIGTERM', () => {
  for (const server of servers) {
    server.closeAllConnections();
    server.close();
  }
});
