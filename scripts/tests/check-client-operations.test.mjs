import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { checkClientOperations } from '../check-client-operations.mjs';

const require = createRequire(new URL('../../packages/shared/package.json', import.meta.url));
const ts = require('typescript');
const good = { responses: { 200: { content: { 'application/json': { schema: { type: 'object' } } } } } };
const binary = { responses: { 200: { content: { '*/*': { schema: { type: 'string', format: 'binary' } } } } } };
const stream = { responses: { 200: { content: { 'text/event-stream': { schema: { type: 'string' } } } } } };
const client =
  "import axios, { AxiosError, AxiosHeaders, type AxiosInstance } from 'axios'; const client = axios.create();\n";

async function fixture(t, sources, paths) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'ledova-client-operations-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const [name, content] of Object.entries(sources)) {
    const filename = path.join(root, name);
    await mkdir(path.dirname(filename), { recursive: true });
    await writeFile(filename, content);
  }
  return checkClientOperations(root, { paths });
}

test('Axios symbols retain renamed parameters, imports and endpoint functions across modules', async (t) => {
  const result = await fixture(
    t,
    {
      'packages/shared/src/index.ts': "export { ENDPOINTS } from './endpoints';",
      'packages/shared/src/endpoints.ts':
        'export const ENDPOINTS = { DETAIL: (uuid: string) => `/api/items/${uuid}/` } as const;',
      'dashboard/src/service.ts':
        client +
        "import { ENDPOINTS as URLS } from '@ledova/shared'; export function read(renamed: AxiosInstance, id: string) { return renamed.get(URLS.DETAIL(id)); }",
      'mobile/src/service.ts':
        client + "client.post('/api/items/'); client['patch'](`/api/items/${'selected'}/?ignored=yes`);",
    },
    { '/api/items/{uuid}/': { get: good }, '/api/items/': { post: good }, '/api/items/selected/': { patch: good } },
  );
  assert.deepEqual(result.failures, []);
  assert.deepEqual(
    result.operations.map(({ method, path: url }) => [method, url]),
    [
      ['get', '/api/items/{}/'],
      ['post', '/api/items/'],
      ['patch', '/api/items/selected/'],
    ],
  );
});

test('Map, file, headers, comments, tests and strings do not invent requests', async (t) => {
  const result = await fixture(
    t,
    {
      'dashboard/src/service.ts':
        client +
        "client.get('/api/items/'); axios.isAxiosError({}); new Map().get('missing'); new AxiosHeaders().delete('Authorization'); const file = { delete() {} }; file.delete(); const text = `client.get('/missing/')`; // client.post('/missing/');",
      'mobile/src/service.test.ts': client + "client.get('/not-runtime/');",
      'mobile/src/testSupport/helper.ts': client + "client.get('/not-runtime/');",
    },
    { '/api/items/': { get: good } },
  );
  assert.deepEqual(result.failures, []);
  assert.equal(result.operations.length, 1);
});

test('missing paths and wrong verbs identify the actual untyped caller', async (t) => {
  const result = await fixture(
    t,
    { 'mobile/src/service.ts': client + "client.delete('/api/items/'); client.get('/missing/');" },
    { '/api/items/': { get: good } },
  );
  assert.equal(result.failures.length, 2);
  assert.match(result.failures.join('\n'), /mobile\/src\/service.ts:2: DELETE \/api\/items\//);
  assert.match(result.failures.join('\n'), /GET \/missing\//);
});

test('new unresolved Axios paths/configs, reassigned URLs, indirect methods and fetch fail visibly', async (t) => {
  const result = await fixture(
    t,
    {
      'mobile/src/service.ts':
        client +
        [
          "client.get('/api/items/');",
          'export function dynamic(destination: string) { client.get(destination); client.request({url: destination}); }',
          "let destination = '/api/items/'; destination = globalThis.location.href; client.get(destination);",
          'const indirect = client.get; indirect(globalThis.location.href);',
          "fetch('/api/items/');",
        ].join('\n'),
    },
    { '/api/items/': { get: good } },
  );
  assert.match(result.failures.join('\n'), /:3: Unresolved client destination/);
  assert.match(result.failures.join('\n'), /:3: Unresolved Axios request configuration/);
  assert.match(result.failures.join('\n'), /:4: Unresolved client destination/);
  assert.match(result.failures.join('\n'), /:5: Indirect Axios transport reference/);
  assert.match(result.failures.join('\n'), /:6: Unclassified fetch transport/);
});

test('valid empty, binary, text, scalar and object responses stay covered', async (t) => {
  const paths = {
    '/empty/': { delete: { responses: { 204: { description: 'Deleted' } } } },
    '/binary/': { get: binary },
    '/text/': { get: { responses: { 200: { content: { 'text/csv': { schema: { type: 'string' } } } } } } },
    '/scalar/': { get: { responses: { 200: { content: { 'application/json': { schema: { type: 'integer' } } } } } } },
    '/object/': { get: good },
  };
  const result = await fixture(
    t,
    {
      'mobile/src/service.ts':
        client +
        "client.delete('/empty/'); client.get('/binary/'); client.get('/text/'); client.get('/scalar/'); client.get('/object/');",
    },
    paths,
  );
  assert.deepEqual(result.failures, []);
  assert.equal(result.operations.length, 5);
});

test('error-only and undocumented successful responses cannot satisfy a client request', async (t) => {
  const result = await fixture(
    t,
    { 'mobile/src/service.ts': client + "client.get('/empty/'); client.post('/error-only/');" },
    {
      '/empty/': { get: { responses: { 200: { description: 'No body' } } } },
      '/error-only/': { post: { responses: { 400: good.responses[200] } } },
    },
  );
  assert.equal(result.failures.length, 2);
  assert.ok(result.failures.every((message) => message.includes('no declared successful response kind')));
});

test('both real retry forms account for the original request without inventing an endpoint', async (t) => {
  const result = await fixture(
    t,
    {
      'dashboard/src/service.ts':
        client +
        [
          "client.get('/api/items/');",
          'client.interceptors.response.use(r => r, (error: AxiosError) => { const config = error.config; if (config) return client.request(config); });',
          'client.interceptors.response.use(r => r, (error: AxiosError) => { const config = error.config; if (config) return client(config); });',
        ].join('\n'),
    },
    { '/api/items/': { get: good } },
  );
  assert.deepEqual(result.failures, []);
  assert.equal(result.operations.length, 1);
  assert.equal(result.replays.length, 2);
});

test('a rewritten or escaped retry config is unresolved, including method and origin changes', async (t) => {
  for (const mutation of [
    "config.url = '/unrecorded/';",
    "config['method'] = 'DELETE';",
    "config.baseURL = 'https://other.invalid';",
    'Object.assign(config, {});',
    "const alias = config; alias.url = '/unrecorded/';",
    'const clone = {...config};',
  ]) {
    const result = await fixture(
      t,
      {
        'dashboard/src/service.ts':
          client +
          `client.get('/api/items/'); client.interceptors.response.use(r => r, (error: AxiosError) => { const config = error.config; if (config) { ${mutation} return client.request(config); } });`,
      },
      { '/api/items/': { get: good } },
    );
    assert.equal(result.replays.length, 0, mutation);
    assert.match(result.failures.join('\n'), /Unresolved Axios request configuration/, mutation);
  }
});

test('a retry config escaping through an object shorthand cannot bypass destination coverage', async (t) => {
  const result = await fixture(
    t,
    {
      'dashboard/src/service.ts':
        client +
        "client.get('/api/items/'); client.interceptors.response.use(r => r, (error: AxiosError) => { const config = error.config; if (config) { const escaped = { config }; escaped.config.url = '/unrecorded/'; return client.request(config); } });",
    },
    { '/api/items/': { get: good } },
  );
  assert.equal(result.replays.length, 0);
  assert.deepEqual(result.failures, [
    'dashboard/src/service.ts:2: Unresolved Axios request configuration; declare its method/path or preserve an unchanged AxiosError.config replay.',
  ]);
});

test('the response-linked company file requires its internal binary route', async (t) => {
  const sources = {
    'mobile/src/screens/listing/index.tsx':
      client +
      'interface DocumentRowProps { uploaded?: { fileUrl?: string } } function DocumentRow({uploaded}: DocumentRowProps) { if (uploaded?.fileUrl) client.get(uploaded.fileUrl); }',
  };
  const url = '/api/v1/companies/{company_uuid}/documents/{uuid}/file/';
  const admitted = await fixture(t, sources, { [url]: { get: binary } });
  assert.deepEqual(admitted.failures, []);
  assert.equal(admitted.operations[0].mechanism, 'CompanyDocument.fileUrl');
  const wrong = await fixture(t, sources, { [url]: { get: good } });
  assert.match(wrong.failures.join('\n'), /must declare binary/);
  const missing = await fixture(t, sources, {});
  assert.match(missing.failures.join('\n'), /is absent from the schema/);
  const unknown = await fixture(
    t,
    {
      'mobile/src/another.ts': client + 'function open(document: {fileUrl: string}) { client.get(document.fileUrl); }',
    },
    { [url]: { get: binary } },
  );
  assert.match(unknown.failures.join('\n'), /Unresolved client destination/);
});

test('browser and mobile SSE builders check the actual event-stream path and content kind', async (t) => {
  const helper = await readFile(new URL('../../mobile/src/config/networkPolicy.ts', import.meta.url), 'utf8');
  const sources = {
    'mobile/src/config/networkPolicy.ts': helper,
    'mobile/src/service.ts':
      "import EventSource from 'react-native-sse'; import { getTradingEventsUrl } from './config/networkPolicy'; let url: string; try { url = getTradingEventsUrl('/events/', 'synthetic'); } catch {} new EventSource(url);",
    'dashboard/src/service.ts':
      "export {}; const baseUrl = (import.meta.env.VITE_API_URL as string).replace(/\\/$/, ''); const url = `${baseUrl}/events/?token=${'synthetic'}`; new EventSource(url);",
  };
  const admitted = await fixture(t, sources, { '/events/': { get: stream } });
  assert.deepEqual(admitted.failures, []);
  assert.equal(admitted.operations.length, 2, JSON.stringify(admitted));
  const wrong = await fixture(t, sources, { '/events/': { get: good } });
  assert.equal(wrong.failures.length, 2);
  assert.ok(wrong.failures.every((message) => message.includes('must declare text/event-stream')));
  const changed = await fixture(
    t,
    {
      ...sources,
      'mobile/src/config/networkPolicy.ts': helper.replace(
        '`${getApiBaseUrl()}${path}`',
        '`${getApiBaseUrl()}/changed/`',
      ),
    },
    { '/events/': { get: stream } },
  );
  assert.match(changed.failures.join('\n'), /mobile\/src\/service.ts:1: Unresolved client destination/);
  const context = vm.createContext({
    URL,
    process: { env: { EXPO_PUBLIC_API_URL: 'https://api.example.test' } },
    __DEV__: false,
    exports: {},
  });
  vm.runInContext(
    ts.transpileModule(helper, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    context,
  );
  assert.equal(
    context.exports.getTradingEventsUrl('/events/', 'synthetic'),
    'https://api.example.test/events/?token=synthetic',
  );
});

test('an unclassified new SSE destination is not silently omitted', async (t) => {
  const result = await fixture(
    t,
    {
      'dashboard/src/service.ts':
        client + "client.get('/api/items/'); function connect(url: string) { new EventSource(url); }",
    },
    { '/api/items/': { get: good } },
  );
  assert.match(result.failures.join('\n'), /Unresolved client destination/);
});

test('casting an Axios receiver does not erase its HTTP operation from the census', async (t) => {
  const result = await fixture(
    t,
    {
      'mobile/src/service.ts':
        client + "(client as any).get('/missing/'); const erased: any = client; erased.delete('/missing/');",
    },
    {},
  );
  assert.equal(result.operations.length, 2);
  assert.match(result.failures.join('\n'), /GET \/missing\//);
  assert.match(result.failures.join('\n'), /DELETE \/missing\//);
});

test('aliased browser streams are covered and new browser transports fail visibly', async (t) => {
  const result = await fixture(
    t,
    {
      'dashboard/src/service.ts':
        'export {}; const Stream = EventSource; new Stream("/events/"); new window.EventSource("/events/"); new WebSocket("wss://other.invalid"); new XMLHttpRequest();',
    },
    { '/events/': { get: stream } },
  );
  assert.equal(result.operations.length, 2);
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /Unclassified client transport/);
});

test('syntax errors cannot hide the remainder of an actual client file', async (t) => {
  const result = await fixture(
    t,
    { 'mobile/src/service.ts': client + "client.get('/api/items/'); const hidden = (" },
    { '/api/items/': { get: good } },
  );
  assert.match(result.failures.join('\n'), /Cannot inspect malformed client source/);
});

test('a dynamic Axios verb cannot inherit one arbitrary resolved signature', async (t) => {
  const result = await fixture(
    t,
    {
      'mobile/src/service.ts':
        client + "client.get('/api/items/'); function read(method: 'get' | 'post') { client[method]('/api/items/'); }",
    },
    { '/api/items/': { get: good, post: good } },
  );
  assert.match(result.failures.join('\n'), /Unsupported client HTTP method dynamic/);
  assert.equal(result.operations.length, 1);
});
