export function sourceImports(ts, text, filename) {
  const kind = /\.[jt]sx$/.test(filename) ? ts.ScriptKind.TSX : undefined;
  const source = ts.createSourceFile(filename, text, ts.ScriptTarget.Latest, true, kind);
  const imports = [];

  function add(node) {
    if (!node || !ts.isStringLiteralLike(node)) return;
    const { line } = source.getLineAndCharacterOfPosition(node.getStart(source));
    imports.push({ specifier: node.text, line: line + 1 });
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) add(node.moduleSpecifier);
    else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      add(node.moduleReference.expression);
    } else if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) {
      add(node.argument.literal);
    } else if (
      ts.isCallExpression(node) &&
      (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(node.expression) && node.expression.text === 'require'))
    ) {
      add(node.arguments[0]);
    }
    ts.forEachChild(node, visit);
  }

  visit(source);
  return imports;
}
