import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(new URL('../packages/shared/package.json', import.meta.url));
const ts = require('typescript');
const ROOT = fileURLToPath(new URL('..', import.meta.url));
const AXIOS_TYPES = path.join(path.dirname(require.resolve('axios/package.json')), 'index.d.ts');
const METHODS = new Set(['get', 'post', 'put', 'patch', 'delete']);
const ORIGIN = 'https://configured-api.invalid';
const SOURCE_ROOTS = ['packages/shared/src', 'dashboard/src', 'mobile/src'];

function sourceFiles(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (/^(node_modules|__tests__|__mocks__|testSupport)$/.test(entry.name)) return [];
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(filename);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec|d)\.tsx?$/.test(entry.name) ? [filename] : [];
  });
}

function unwrap(node) {
  while (
    node &&
    (ts.isAsExpression(node) ||
      ts.isTypeAssertionExpression(node) ||
      ts.isParenthesizedExpression(node) ||
      ts.isNonNullExpression(node) ||
      ts.isSatisfiesExpression(node))
  )
    node = node.expression;
  return node;
}

function visit(node, callback) {
  callback(node);
  ts.forEachChild(node, (child) => visit(child, callback));
}

function shape(value) {
  return (
    value
      .split(/[?#]/, 1)[0]
      .replace(/\{[^}]*\}/g, '{}')
      .replace(/\/$/, '') + '/'
  );
}

export function checkClientOperations(root, document) {
  const files = SOURCE_ROOTS.flatMap((directory) => sourceFiles(path.join(root, directory))).sort();
  const program = ts.createProgram(files, {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    jsx: ts.JsxEmit.ReactJSX,
    allowSyntheticDefaultImports: true,
    strict: true,
    skipLibCheck: true,
    baseUrl: root,
    paths: { axios: [AXIOS_TYPES], '@ledova/shared': ['packages/shared/src/index.ts'] },
  });
  const checker = program.getTypeChecker();
  const failures = [];
  const operations = [];
  const replays = [];
  const declarations = new Map();
  for (const [url, methods] of Object.entries(document.paths ?? {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (METHODS.has(method)) declarations.set(`${method} ${shape(url)}`, operation);
    }
  }

  function location(node) {
    const source = node.getSourceFile();
    return `${path.relative(root, source.fileName)}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
  }

  function fail(node, message) {
    failures.push(`${location(node)}: ${message}`);
  }

  function symbol(node) {
    const original = checker.getSymbolAtLocation(node);
    return original?.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(original) : original;
  }

  function declaration(node) {
    return symbol(node)?.valueDeclaration ?? symbol(node)?.declarations?.[0];
  }

  function axiosOwner(node) {
    if (!node || !/[/\\]node_modules[/\\]axios[/\\]index\.d\.ts$/.test(node.getSourceFile().fileName)) return undefined;
    return node.parent.name?.text;
  }

  function transport(call) {
    const expression = unwrap(call.expression);
    if (
      ts.isElementAccessExpression(expression) &&
      value(expression.argumentExpression) === undefined &&
      axiosReceiver(expression.expression, 'get')
    )
      return 'dynamic';
    let signature = checker.getResolvedSignature(call)?.declaration;
    if (!axiosOwner(signature)) signature = axiosMethod(call.expression);
    if (!axiosOwner(signature))
      signature = checker.getTypeAtLocation(unwrap(call.expression)).getCallSignatures()[0]?.declaration;
    if (!['Axios', 'AxiosInstance', 'AxiosStatic'].includes(axiosOwner(signature))) return undefined;
    const name = (signature.name?.text ?? 'request').replace(/Form$/, '');
    return METHODS.has(name) || ['request', 'head', 'options', 'query'].includes(name) ? name : undefined;
  }

  function axiosMethod(node) {
    node = unwrap(node);
    if (!node || (!ts.isPropertyAccessExpression(node) && !ts.isElementAccessExpression(node))) return undefined;
    const name = ts.isPropertyAccessExpression(node) ? node.name.text : value(node.argumentExpression);
    if (!name) return undefined;
    return axiosReceiver(node.expression, name);
  }

  function axiosReceiver(node, name) {
    let receiver = unwrap(node);
    const seen = new Set();
    while (receiver && !seen.has(receiver)) {
      seen.add(receiver);
      const property = checker.getTypeAtLocation(receiver).getProperty(name)?.valueDeclaration;
      if (axiosOwner(property)) return property;
      receiver = unwrap(initializer(receiver));
    }
    return undefined;
  }

  function initializer(node) {
    const declared = declaration(node);
    if (!declared || ts.isParameter(declared)) return undefined;
    if (!ts.isVariableDeclaration(declared)) return declared.initializer;
    const writes = [];
    visit(declared.getSourceFile(), (candidate) => {
      if (
        ts.isBinaryExpression(candidate) &&
        candidate.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        candidate.operatorToken.kind <= ts.SyntaxKind.LastAssignment &&
        symbol(candidate.left) === symbol(node)
      )
        writes.push(candidate.operatorToken.kind === ts.SyntaxKind.EqualsToken ? candidate.right : undefined);
    });
    if (declared.initializer) writes.push(declared.initializer);
    return writes.length === 1 ? writes[0] : undefined;
  }

  function simpleUrlBuilder(node) {
    const declared = declaration(node.expression);
    if (
      !declared ||
      !ts.isFunctionDeclaration(declared) ||
      path.relative(root, declared.getSourceFile().fileName) !== 'mobile/src/config/networkPolicy.ts' ||
      declared.name?.text !== 'getTradingEventsUrl'
    )
      return false;
    const statements = declared.body?.statements;
    if (statements?.length !== 3 || !ts.isVariableStatement(statements[0])) return false;
    const url = statements[0].declarationList.declarations[0];
    const build = url?.initializer;
    const query = statements[1];
    const result = statements[2];
    return (
      build &&
      ts.isNewExpression(build) &&
      build.expression.getText() === 'URL' &&
      build.arguments?.length === 1 &&
      build.arguments[0].getText() === '`${getApiBaseUrl()}${' + declared.parameters[0].name.getText() + '}`' &&
      ts.isExpressionStatement(query) &&
      ts.isCallExpression(query.expression) &&
      query.expression.expression.getText() === `${url.name.getText()}.searchParams.set` &&
      query.expression.arguments.length === 2 &&
      query.expression.arguments[0].text === 'token' &&
      query.expression.arguments[1].getText() === declared.parameters[1].name.getText() &&
      ts.isReturnStatement(result) &&
      result.expression?.getText() === `validateApiDestination(${url.name.getText()}.href)`
    );
  }

  function value(node, bindings = new Map(), seen = new Set()) {
    node = unwrap(node);
    if (!node || seen.has(node)) return undefined;
    const next = new Set([...seen, node]);
    if (ts.isStringLiteralLike(node)) return node.text;
    if (bindings.has(symbol(node))) return bindings.get(symbol(node));
    if (node.getText() === 'import.meta.env.VITE_API_URL') return ORIGIN;
    if (ts.isTemplateExpression(node)) {
      return (
        node.head.text +
        node.templateSpans.map((span) => (value(span.expression, bindings, next) ?? '{}') + span.literal.text).join('')
      );
    }
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const left = value(node.left, bindings, next);
      const right = value(node.right, bindings, next);
      return left === undefined || right === undefined ? undefined : left + right;
    }
    if (ts.isCallExpression(node)) {
      if (
        ts.isPropertyAccessExpression(node.expression) &&
        node.expression.name.text === 'replace' &&
        node.arguments[0]?.getText() === '/\\/$/' &&
        node.arguments[1]?.text === ''
      )
        return value(node.expression.expression, bindings, next)?.replace(/\/$/, '');
      if (simpleUrlBuilder(node)) return value(node.arguments[0], bindings, next);
      let declared = declaration(node.expression);
      if (declared?.initializer) declared = unwrap(declared.initializer);
      if (
        declared &&
        (ts.isArrowFunction(declared) || ts.isFunctionExpression(declared)) &&
        !ts.isBlock(declared.body)
      ) {
        const parameters = new Map(bindings);
        declared.parameters.forEach((parameter, index) =>
          parameters.set(symbol(parameter.name), value(node.arguments[index], bindings, next) ?? '{}'),
        );
        return value(declared.body, parameters, next);
      }
    }
    if (ts.isIdentifier(node) || ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))
      return value(initializer(node), bindings, next);
    return undefined;
  }

  function replay(call) {
    const config = unwrap(call.arguments[0]);
    if (!config || !ts.isIdentifier(config)) return false;
    const declared = declaration(config);
    const original = unwrap(declared?.initializer);
    if (
      !original ||
      !ts.isPropertyAccessExpression(original) ||
      original.name.text !== 'config' ||
      axiosOwner(declaration(original)) !== 'AxiosError'
    )
      return false;
    let scope = declared;
    while (scope && !ts.isFunctionLike(scope)) scope = scope.parent;
    if (!scope) return false;
    let unchanged = true;
    visit(scope, (node) => {
      if (ts.isShorthandPropertyAssignment(node) && checker.getShorthandAssignmentValueSymbol(node) === symbol(config))
        unchanged = false;
      if (!ts.isIdentifier(node) || symbol(node) !== symbol(config) || node === declared.name) return;
      let parent = node.parent;
      if (
        (ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) &&
        parent.expression === node
      ) {
        const key = ts.isPropertyAccessExpression(parent) ? parent.name.text : parent.argumentExpression.text;
        const use = parent.parent;
        if (
          (ts.isBinaryExpression(use) &&
            use.left === parent &&
            use.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
            use.operatorToken.kind <= ts.SyntaxKind.LastAssignment) ||
          ts.isDeleteExpression(use) ||
          ts.isPrefixUnaryExpression(use) ||
          ts.isPostfixUnaryExpression(use)
        ) {
          if (!['_retry', 'csrfRetried'].includes(key)) unchanged = false;
        }
      } else if (
        ts.isBinaryExpression(parent) &&
        parent.left === node &&
        parent.operatorToken.kind === ts.SyntaxKind.EqualsToken
      )
        unchanged = false;
      else if (
        ts.isCallExpression(parent) &&
        parent.arguments.includes(node) &&
        (transport(parent) !== 'request' || parent.arguments[0] !== node)
      )
        unchanged = false;
      else if (
        ts.isSpreadAssignment(parent) ||
        ts.isVariableDeclaration(parent) ||
        ts.isReturnStatement(parent) ||
        ts.isArrayLiteralExpression(parent) ||
        ts.isPropertyAssignment(parent)
      )
        unchanged = false;
    });
    return unchanged;
  }

  function linkedFile(node) {
    const declared = declaration(unwrap(node));
    if (!declared || !ts.isPropertySignature(declared) || declared.name.getText() !== 'fileUrl') return false;
    if (
      declared.parent.name?.text === 'CompanyDocument' &&
      path.relative(root, declared.getSourceFile().fileName) === 'packages/shared/src/types/domain/company.ts'
    )
      return true;
    let parent = declared.parent;
    let property;
    while (parent && !ts.isInterfaceDeclaration(parent)) {
      if (ts.isPropertySignature(parent)) property = parent.name.getText();
      parent = parent.parent;
    }
    return (
      property === 'uploaded' &&
      parent?.name.text === 'DocumentRowProps' &&
      path.relative(root, declared.getSourceFile().fileName) === 'mobile/src/screens/listing/index.tsx'
    );
  }

  function record(call, method, url, mechanism, expectedMedia) {
    if (!METHODS.has(method))
      return fail(call, `Unsupported client HTTP method ${method}; add explicit operation coverage.`);
    if (url?.startsWith(ORIGIN)) url = url.slice(ORIGIN.length);
    if (!url?.startsWith('/') || url.startsWith('//'))
      return fail(
        call,
        'Unresolved client destination; use a resolvable API path or add a tested response-linked/replay/stream mechanism.',
      );
    const operation = { location: location(call), method, path: shape(url), mechanism };
    operations.push(operation);
    const declared = declarations.get(`${method} ${operation.path}`);
    if (!declared) return fail(call, `${method.toUpperCase()} ${operation.path} is absent from the schema.`);
    const successes = Object.entries(declared.responses ?? {}).filter(([status]) => /^2\d\d$/.test(status));
    const media = successes.flatMap(([, response]) => Object.entries(response.content ?? {}));
    const known =
      successes.some(([status, response]) => status === '204' && !response.content) ||
      media.some(([, response]) =>
        ['type', '$ref', 'oneOf', 'anyOf', 'allOf'].some((key) => key in (response.schema ?? {})),
      );
    if (!known) fail(call, `${method.toUpperCase()} ${operation.path} has no declared successful response kind.`);
    if (
      expectedMedia &&
      !media.some(([kind, response]) =>
        expectedMedia === 'binary'
          ? response.schema?.type === 'string' && response.schema.format === 'binary'
          : kind === expectedMedia,
      )
    )
      fail(call, `${method.toUpperCase()} ${operation.path} must declare ${expectedMedia}.`);
  }

  function networkConstructor(node) {
    const original = checker.getSymbolAtLocation(node.expression);
    for (let imported of original?.declarations ?? []) {
      while (imported && !ts.isSourceFile(imported) && !ts.isImportDeclaration(imported)) imported = imported.parent;
      if (imported && ts.isImportDeclaration(imported) && imported.moduleSpecifier.text === 'react-native-sse')
        return 'EventSource';
    }
    let declared = checker.getResolvedSignature(node)?.declaration;
    if (!declared?.getSourceFile().fileName.endsWith('/lib.dom.d.ts')) return undefined;
    while (declared && !ts.isSourceFile(declared)) {
      if (['EventSource', 'XMLHttpRequest', 'WebSocket'].includes(declared.name?.text)) return declared.name.text;
      declared = declared.parent;
    }
    return undefined;
  }

  for (const filename of files) {
    const source = program.getSourceFile(filename);
    for (const diagnostic of source.parseDiagnostics) {
      const line = source.getLineAndCharacterOfPosition(diagnostic.start ?? 0).line + 1;
      failures.push(
        `${path.relative(root, filename)}:${line}: Cannot inspect malformed client source: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ')}`,
      );
    }
    visit(source, (node) => {
      if (ts.isCallExpression(node)) {
        const method = transport(node);
        if (method) {
          if (method === 'request') {
            if (replay(node)) replays.push({ location: location(node), mechanism: 'original AxiosError.config' });
            else
              fail(
                node,
                'Unresolved Axios request configuration; declare its method/path or preserve an unchanged AxiosError.config replay.',
              );
          } else if (linkedFile(node.arguments[0]))
            record(node, method, '/api/v1/companies/{}/documents/{}/file/', 'CompanyDocument.fileUrl', 'binary');
          else record(node, method, value(node.arguments[0]), 'axios');
        } else {
          const signature = checker.getResolvedSignature(node)?.declaration;
          if (signature?.name?.text === 'fetch' && signature.getSourceFile().fileName.endsWith('/lib.dom.d.ts'))
            fail(node, 'Unclassified fetch transport; add explicit method/path coverage before using it.');
        }
      }
      if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
        const name = axiosMethod(node)?.name?.text;
        if (
          name &&
          (METHODS.has(name.replace(/Form$/, '')) || ['request', 'head', 'options', 'query'].includes(name)) &&
          !(ts.isCallExpression(node.parent) && node.parent.expression === node)
        )
          fail(node, 'Indirect Axios transport reference; call it directly or add tested endpoint resolution.');
      }
      if (ts.isNewExpression(node)) {
        const kind = networkConstructor(node);
        if (kind === 'EventSource')
          record(node, 'get', value(node.arguments?.[0]), 'event-source', 'text/event-stream');
        else if (kind) fail(node, 'Unclassified client transport; add explicit operation coverage before using it.');
      }
    });
  }
  if (!files.length) failures.push('No client source files were discovered.');
  if (!operations.length)
    failures.push('No client HTTP operations were discovered; check TypeScript/Axios resolution.');
  return { scanned: files.length, operations, replays, failures: [...new Set(failures)].sort() };
}

export function main(arguments_ = process.argv.slice(2)) {
  let schema = path.join(ROOT, 'backend/schema/openapi.json');
  let report;
  for (let index = 0; index < arguments_.length; index += 2) {
    if (arguments_[index] === '--schema') schema = arguments_[index + 1];
    else if (arguments_[index] === '--report') report = arguments_[index + 1];
    else throw new Error(`Unknown option: ${arguments_[index]}`);
  }
  const result = checkClientOperations(ROOT, JSON.parse(readFileSync(schema, 'utf8')));
  if (report) writeFileSync(report, JSON.stringify(result, null, 2) + '\n');
  if (result.failures.length) {
    console.error(result.failures.join('\n'));
    return 1;
  }
  const pairs = new Set(result.operations.map(({ method, path: url }) => `${method} ${url}`));
  console.log(
    `${result.operations.length} client HTTP sites (${pairs.size} distinct operations) and ${result.replays.length} original-request replays are accounted for across ${result.scanned} source files.`,
  );
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exitCode = main();
