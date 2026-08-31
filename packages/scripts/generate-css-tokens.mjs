#!/usr/bin/env node

/**
 * Generates Tailwind CSS v4 @theme tokens from DESIGN_TOKENS.
 *
 * Single source of truth: packages/shared-constants/src/ui/design-tokens.ts
 * Outputs:  dashboard/src/styles/tokens.css
 *           marketing/src/tokens.css
 *
 * Usage: node packages/scripts/generate-css-tokens.mjs
 */

import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');

// Import from built shared-constants
const { DESIGN_TOKENS, LIGHT_COLORS } = await import('../packages/shared-constants/dist/ui/design-tokens.js');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Flatten a nested color object into CSS custom properties.
 * Keys named "default" collapse into the parent name:
 *   brand.default  → --color-brand
 *   brand.hover    → --color-brand-hover
 *
 * Skips non-string leaves (objects/arrays are recursed or skipped).
 */
function flattenColors(obj, prefix, lines) {
  for (const [key, value] of Object.entries(obj)) {
    const name = key === 'default' ? prefix : `${prefix}-${key}`;
    if (typeof value === 'string') {
      lines.push(`  --color-${name}: ${value};`);
    } else if (typeof value === 'object' && !Array.isArray(value)) {
      flattenColors(value, name, lines);
    }
    // Arrays (chart palettes) are skipped — consumed via JS only
  }
}

function section(lines, title) {
  lines.push(`\n  /* === ${title} === */`);
}

function add(lines, varName, value) {
  lines.push(`  ${varName}: ${value};`);
}

// ---------------------------------------------------------------------------
// Generate color variables from a color object
// ---------------------------------------------------------------------------

function generateColorVars(colors) {
  const lines = [];

  section(lines, 'SURFACES');
  flattenColors(colors.surface, 'surface', lines);

  section(lines, 'TEXT');
  flattenColors(colors.text, 'text', lines);

  section(lines, 'BRAND');
  flattenColors(colors.brand, 'brand', lines);

  section(lines, 'BORDERS');
  flattenColors(colors.border, 'border', lines);

  section(lines, 'STATUS');
  flattenColors(colors.success, 'success', lines);
  flattenColors(colors.error, 'error', lines);
  flattenColors(colors.warning, 'warning', lines);
  flattenColors(colors.info, 'info', lines);

  section(lines, 'UTILITY');
  for (const [key, value] of Object.entries(colors.utility)) {
    add(lines, `--color-${key}`, value);
  }

  return lines;
}

// ---------------------------------------------------------------------------
// Generate shared (non-color) tokens
// ---------------------------------------------------------------------------

function generateSharedVars() {
  const lines = [];

  // Spacing (token name → Tailwind numeric scale: value / 4)
  section(lines, 'SPACING');
  for (const [, value] of Object.entries(DESIGN_TOKENS.spacing)) {
    add(lines, `--spacing-${value / 4}`, `${value}px`);
  }

  // Border Radius
  section(lines, 'BORDER RADIUS');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.borderRadius)) {
    const unit = value === 0 ? '0' : typeof value === 'number' ? `${value}px` : value;
    add(lines, `--border-radius-${key}`, unit);
  }

  // Font Sizes
  section(lines, 'FONT SIZES');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.fontSize)) {
    add(lines, `--font-size-${key}`, `${value}px`);
  }

  // Font Weights
  section(lines, 'FONT WEIGHTS');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.fontWeight)) {
    add(lines, `--font-weight-${key}`, value);
  }

  // Line Heights
  section(lines, 'LINE HEIGHTS');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.lineHeight)) {
    add(lines, `--line-height-${key}`, value);
  }

  // Shadows
  section(lines, 'SHADOWS');
  for (const [key, shadow] of Object.entries(DESIGN_TOKENS.shadows)) {
    add(lines, `--shadow-${key}`, shadow.web);
  }

  // Z-Index
  section(lines, 'Z-INDEX');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.zIndex)) {
    add(lines, `--z-${key}`, value);
  }

  // Animation Durations
  section(lines, 'ANIMATION');
  for (const [key, value] of Object.entries(DESIGN_TOKENS.animation.duration)) {
    add(lines, `--duration-${key}`, `${value}ms`);
  }

  return lines;
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

const darkColorVars = generateColorVars(DESIGN_TOKENS.colors);
const lightColorVars = generateColorVars(LIGHT_COLORS);
const sharedVars = generateSharedVars();

const css = `/**
 * AUTO-GENERATED — DO NOT EDIT
 *
 * Source of truth: packages/shared-constants/src/ui/design-tokens.ts
 * Regenerate:      node packages/scripts/generate-css-tokens.mjs
 *                  (or: make generate-tokens from repo root)
 */

@theme {${[...darkColorVars, ...sharedVars].join('\n')}
}

/* ── Light theme ───────────────────────────────────────────────────────────
 * Activates via OS preference or .theme-light class on <html>.
 * Only color variables change; spacing, typography, etc. are shared. */

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
