#!/usr/bin/env node

import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');

const { DESIGN_TOKENS, LIGHT_COLORS } = await import('../shared/src/constants/ui/design-tokens.ts');

function flattenColors(obj, prefix, lines) {
  for (const [key, value] of Object.entries(obj)) {
    const name = key === 'default' ? prefix : `${prefix}-${key}`;
    if (typeof value === 'string') {
      lines.push(`  --color-${name}: ${value};`);
    } else if (typeof value === 'object' && !Array.isArray(value)) {
      flattenColors(value, name, lines);
    }
  }
}

function section(lines) {
  lines.push('');
}

function add(lines, varName, value) {
  lines.push(`  ${varName}: ${value};`);
}

function generateColorVars(colors) {
  const lines = [];

  section(lines);
  flattenColors(colors.surface, 'surface', lines);

  section(lines);
  flattenColors(colors.text, 'text', lines);

  section(lines);
  flattenColors(colors.brand, 'brand', lines);

  section(lines);
  flattenColors(colors.border, 'border', lines);

  section(lines);
  flattenColors(colors.success, 'success', lines);
  flattenColors(colors.error, 'error', lines);
  flattenColors(colors.warning, 'warning', lines);
  flattenColors(colors.info, 'info', lines);

  section(lines);
  for (const [key, value] of Object.entries(colors.utility)) {
    add(lines, `--color-${key}`, value);
  }

  return lines;
}

function generateSharedVars() {
  const lines = [];

  section(lines);
  for (const [, value] of Object.entries(DESIGN_TOKENS.spacing)) {
    add(lines, `--spacing-${value / 4}`, `${value}px`);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.borderRadius)) {
    const unit = value === 0 ? '0' : typeof value === 'number' ? `${value}px` : value;
    add(lines, `--border-radius-${key}`, unit);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.fontSize)) {
    add(lines, `--font-size-${key}`, `${value}px`);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.fontWeight)) {
    add(lines, `--font-weight-${key}`, value);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.lineHeight)) {
    add(lines, `--line-height-${key}`, value);
  }

  section(lines);
  for (const [key, shadow] of Object.entries(DESIGN_TOKENS.shadows)) {
    add(lines, `--shadow-${key}`, shadow.web);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.zIndex)) {
    add(lines, `--z-${key}`, value);
  }

  section(lines);
  for (const [key, value] of Object.entries(DESIGN_TOKENS.animation.duration)) {
    add(lines, `--duration-${key}`, `${value}ms`);
  }

  return lines;
}

const darkColorVars = generateColorVars(DESIGN_TOKENS.colors);
const lightColorVars = generateColorVars(LIGHT_COLORS);
const sharedVars = generateSharedVars();

const css = `@theme {${[...darkColorVars, ...sharedVars].join('\n')}
}

@media (prefers-color-scheme: light) {
  :root:not(.theme-dark) {
${lightColorVars.map((l) => '  ' + l).join('\n')}
  }
}

.theme-light {
${lightColorVars.map((l) => '  ' + l).join('\n')}
}
`;

const targets = [join(ROOT, 'dashboard/src/styles/tokens.css'), join(ROOT, 'marketing/src/tokens.css')];

for (const target of targets) {
  writeFileSync(target, css, 'utf-8');
  console.log(`✓ ${target.replace(ROOT + '/', '')}`);
}
