#!/usr/bin/env node

/**
 * Generates design token documentation files:
 *   - design-tokens.json  (machine-readable, for Figma/tools)
 *   - design-tokens.html  (styled visual reference)
 *
 * Usage: node packages/scripts/generate-design-docs.mjs
 */

import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');
const OUT_DOCS = join(ROOT, 'docs/public');
const OUT_MARKETING = join(ROOT, 'marketing/public');

const { DESIGN_TOKENS, LIGHT_COLORS } = await import('../packages/shared-constants/dist/ui/design-tokens.js');

// ── JSON output ──────────────────────────────────────────────────────────

const jsonData = {
  $schema: 'https://example.invalid/ledova/design-tokens.schema.json',
  version: '2.0',
  generated: new Date().toISOString().split('T')[0],
  description: 'Ledova Design Tokens — single source of truth for all platforms',
  themes: {
    dark: DESIGN_TOKENS.colors,
    light: LIGHT_COLORS,
  },
  spacing: DESIGN_TOKENS.spacing,
  borderRadius: DESIGN_TOKENS.borderRadius,
  fontSize: DESIGN_TOKENS.fontSize,
  fontWeight: DESIGN_TOKENS.fontWeight,
  lineHeight: DESIGN_TOKENS.lineHeight,
  shadows: Object.fromEntries(
    Object.entries(DESIGN_TOKENS.shadows).map(([k, v]) => [
      k,
      {
        css: v.web,
        rn: {
          shadowColor: v.shadowColor,
          shadowOffset: v.shadowOffset,
          shadowOpacity: v.shadowOpacity,
          shadowRadius: v.shadowRadius,
          elevation: v.elevation,
        },
      },
    ]),
  ),
  zIndex: DESIGN_TOKENS.zIndex,
  animation: DESIGN_TOKENS.animation,
  icon: { sizes: DESIGN_TOKENS.icon.sizes },
};

for (const dir of [OUT_DOCS, OUT_MARKETING]) {
  writeFileSync(join(dir, 'design-tokens.json'), JSON.stringify(jsonData, null, 2), 'utf-8');
}
console.log('✓ design-tokens.json');

// ── HTML output ──────────────────────────────────────────────────────────

function colorSwatch(color, name) {
  if (typeof color !== 'string') return '';
  const textColor = color.startsWith('#') && parseInt(color.slice(1, 3), 16) > 128 ? '#000' : '#fff';
  return `<div class="swatch" style="background:${color}"><span style="color:${textColor}">${name}</span><code>${color}</code></div>`;
}

function renderColorGroup(obj, prefix, depth = 0) {
  let html = '';
  for (const [key, value] of Object.entries(obj)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      html += colorSwatch(value, name);
    } else if (Array.isArray(value)) {
      html += `<div class="color-group"><h4>${name}[]</h4><div class="swatches">`;
      value.forEach((c, i) => {
        html += colorSwatch(c, `${name}[${i}]`);
      });
      html += '</div></div>';
    } else if (typeof value === 'object') {
      if (depth < 2) {
        html += `<div class="color-group"><h4>${name}</h4><div class="swatches">${renderColorGroup(value, name, depth + 1)}</div></div>`;
      }
    }
  }
  return html;
}

function renderTokenTable(obj, unit = '') {
  let html = '<table><thead><tr><th>Token</th><th>Value</th></tr></thead><tbody>';
  for (const [key, value] of Object.entries(obj)) {
    html += `<tr><td><code>${key}</code></td><td>${value}${unit}</td></tr>`;
  }
  html += '</tbody></table>';
  return html;
}

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ledova Design Tokens</title>
<style>
  :root { --bg: #f5f5f7; --card: #fff; --text: #1a1a2e; --muted: #6b7280; --border: #d4d4d8; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.6; }
  h1 { font-size: 2rem; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); margin-bottom: 2rem; font-size: 0.9rem; }
  h2 { font-size: 1.4rem; margin: 2rem 0 1rem; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; }
  h3 { font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: var(--muted); }
  h4 { font-size: 0.85rem; color: var(--muted); margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .section { background: var(--card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid var(--border); }
  .swatches { display: flex; flex-wrap: wrap; gap: 8px; }
  .swatch { width: 140px; height: 72px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 0.7rem; border: 1px solid rgba(0,0,0,0.1); }
  .swatch span { font-weight: 600; font-size: 0.65rem; }
  .swatch code { font-size: 0.6rem; opacity: 0.8; margin-top: 2px; }
  .color-group { margin-bottom: 1rem; }
  .theme-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.5rem 1rem; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
  code { font-family: "SF Mono", Monaco, monospace; background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 4px; font-size: 0.8em; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.5rem; }
  .shadow-demo { padding: 1.5rem; border-radius: 8px; background: white; margin-bottom: 0.75rem; }
  .meta { display: flex; gap: 2rem; margin-bottom: 2rem; font-size: 0.8rem; color: var(--muted); }
  .meta strong { color: var(--text); }
  @media print { body { padding: 1rem; } .section { break-inside: avoid; } }
</style>
</head>
<body>

<h1>Ledova Design Tokens</h1>
<p class="subtitle">Visual reference for the unified design system across dashboard, mobile, and marketing.</p>
<div class="meta">
  <div><strong>Version:</strong> 2.0</div>
  <div><strong>Generated:</strong> ${new Date().toISOString().split('T')[0]}</div>
  <div><strong>Source:</strong> packages/shared-constants/src/ui/design-tokens.ts</div>
</div>

<h2>Colors — Dark Theme (Default)</h2>
<div class="section">
${renderColorGroup(
  {
    surface: DESIGN_TOKENS.colors.surface,
    text: DESIGN_TOKENS.colors.text,
    brand: DESIGN_TOKENS.colors.brand,
    border: DESIGN_TOKENS.colors.border,
    success: DESIGN_TOKENS.colors.success,
    error: DESIGN_TOKENS.colors.error,
    warning: DESIGN_TOKENS.colors.warning,
    info: DESIGN_TOKENS.colors.info,
    utility: DESIGN_TOKENS.colors.utility,
    chain: DESIGN_TOKENS.colors.chain,
    chart: DESIGN_TOKENS.colors.chart,
  },
  '',
)}
</div>

<h2>Colors — Light Theme</h2>
<div class="section">
${renderColorGroup(
  {
    surface: LIGHT_COLORS.surface,
    text: LIGHT_COLORS.text,
    brand: LIGHT_COLORS.brand,
    border: LIGHT_COLORS.border,
    success: LIGHT_COLORS.success,
    error: LIGHT_COLORS.error,
    warning: LIGHT_COLORS.warning,
    info: LIGHT_COLORS.info,
    utility: LIGHT_COLORS.utility,
  },
  '',
)}
</div>

<h2>Spacing</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.spacing, 'px')}
</div>

<div class="grid-2">
<div>
<h2>Border Radius</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.borderRadius, 'px')}
</div>
</div>
<div>
<h2>Font Sizes</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.fontSize, 'px')}
</div>
</div>
</div>

<div class="grid-3">
<div>
<h2>Font Weights</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.fontWeight)}
</div>
</div>
<div>
<h2>Line Heights</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.lineHeight)}
</div>
</div>
<div>
<h2>Z-Index</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.zIndex)}
</div>
</div>
</div>

<h2>Shadows</h2>
<div class="section">
${Object.entries(DESIGN_TOKENS.shadows)
  .map(
    ([key, s]) =>
      `<div class="shadow-demo" style="box-shadow: ${s.web}"><strong>${key}</strong> — <code>${s.web}</code></div>`,
  )
  .join('\n')}
</div>

<h2>Icon Sizes</h2>
<div class="section">
${renderTokenTable(DESIGN_TOKENS.icon.sizes, 'px')}
</div>

<h2>Animation</h2>
<div class="section">
<h3>Duration</h3>
${renderTokenTable(DESIGN_TOKENS.animation.duration, 'ms')}
<h3>Easing</h3>
${renderTokenTable(DESIGN_TOKENS.animation.easing)}
</div>

</body>
</html>`;

for (const dir of [OUT_DOCS, OUT_MARKETING]) {
  writeFileSync(join(dir, 'design-tokens.html'), html, 'utf-8');
}
console.log('✓ design-tokens.html');
