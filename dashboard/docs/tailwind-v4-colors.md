# Color System

This document outlines our color system implementation using Tailwind CSS v4.

## Overview

Our color system uses Tailwind v4's `@theme` directive to define custom colors as CSS variables. All colors are defined in `src/styles/index.css` and automatically generate corresponding Tailwind utility classes.

## Color Palette

### Surface Colors

Used for backgrounds and layered surfaces with progressive contrast:

```css
--color-surface-primary: #0c1426; /* Main app background - navy blue */
--color-surface-secondary: #1a2332; /* Cards, panels - lighter navy */
--color-surface-tertiary: #2a3441; /* Interactive elements - blue-gray */
--color-surface-quaternary: #4a5568; /* Disabled states */
--color-surface-elevated: #243247; /* Modals, dropdowns - elevated navy */
```

**Usage:**

```html
<div class="bg-surface-primary">Main background</div>
<div class="bg-surface-secondary">Card background</div>
<div class="bg-surface-elevated">Modal background</div>
```

### Content Colors

Used for text hierarchy with improved readability:

```css
--color-content-primary: #fafbfc; /* Primary headings */
--color-content-secondary: #e4e7ea; /* Secondary text */
--color-content-body: #cbd2d8; /* Body text */
--color-content-muted: #8b95a1; /* Muted text */
--color-content-subtle: #64748b; /* Subtle helpers */
```

**Usage:**

```html
<h1 class="text-content-primary">Primary heading</h1>
<p class="text-content-body">Body text</p>
<span class="text-content-muted">Muted text</span>
```

### Primary Colors

Brand colors for interactive elements (indigo palette):

```css
--color-primary-400: #818cf8; /* Links, accents */
--color-primary-500: #6366f1; /* Focus rings, brand primary */
--color-primary-600: #4f46e5; /* Primary buttons */
--color-primary-700: #4338ca; /* Button hover */
```

**Usage:**

```html
<button class="bg-primary-600 hover:bg-primary-700">Primary button</button>
<a href="#" class="text-primary-400">Link</a>
```

### Status Colors

Semantic colors for feedback and states:

```css
/* Success */
--color-success-400: #4ade80;
--color-success-600: #16a34a;
--color-success-700: #15803d;

/* Error */
--color-error-400: #f87171;
--color-error-600: #dc2626;
--color-error-700: #b91c1c;

/* Warning */
--color-warning-600: #d97706;
```

**Usage:**

```html
<span class="text-success-600">Success message</span>
<span class="text-error-600">Error message</span>
<span class="text-warning-600">Warning message</span>
```

### Border Colors

Structural borders and focus states:

```css
--color-border-default: #334155; /* Standard borders - navy-gray */
--color-border-subtle: #1e293b; /* Subtle dividers - dark navy */
--color-border-strong: #475569; /* Emphasis borders */
--color-border-focus-primary: #6366f1; /* Primary focus */
```

**Usage:**

```html
<input class="border border-border-default focus:border-border-focus-primary" />
<div class="border-t border-border-subtle">Subtle divider</div>
```

### Accent Colors

Expressive colors for specific UI elements:

```css
--color-accent-secondary: #ec4899; /* Pink accent for icons */
--color-accent-warm: #f97316; /* Orange accent for icons */
--color-accent-teal: #14b8a6; /* Teal for financial highlights */
--color-accent-violet: #8b5cf6; /* Violet for premium features */
```

**Usage:**

```html
<GiftIcon class="text-accent-secondary" /> <span class="text-accent-teal">+12.5% growth</span>
```

### Financial Colors

Specific colors for financial data:

```css
--color-positive: #10b981; /* For positive values */
--color-negative: #ef4444; /* For negative values */
```

**Usage:**

```html
<span class="text-positive">+$1,234.56</span> <span class="text-negative">-$567.89</span>
```

### Transaction Colors

Colors for specific transaction types:

```css
--color-transaction-distribution: #8b5cf6; /* Distribution/gift icons */
```

## Badge System

For consistent status indicators, use the badge system from `@utils/badgeSystem` instead of direct color classes:

```typescript
import { getTradeStatusBadge } from '@utils/badgeSystem';

const badge = getTradeStatusBadge('SETTLED');
// Returns: { className: 'bg-success-900/80 text-success-300', displayText: 'Settled' }
```

## Chart Colors

For data visualizations, use the programmatic chart colors from `@constants/ui`:

```typescript
import { CHART_COLORS, getChartColor } from '@constants/ui';

// Static assignment
const colors = CHART_COLORS; // ['#3B82F6', '#EF4444', '#10B981', ...]

// Dynamic assignment
const color = getChartColor(index); // Cycles through colors
```

## Architecture

### CSS Variables (Tailwind Classes)

- Defined in `src/styles/index.css` using `@theme`
- Generate utility classes like `bg-surface-primary`, `text-content-body`
- Used for styling HTML elements

### JavaScript Constants

- Defined in `src/constants/ui/colors.ts`
- Used for programmatic color assignment
- Primarily for charts and data visualization

### Badge System

- Centralized in `src/utils/badgeSystem.ts`
- Provides semantic status styling
- Ensures consistency across components

## Best Practices

1. **Use semantic names**: `surface-primary` instead of `gray-900`
2. **Maintain hierarchy**: primary → secondary → tertiary progression
3. **Prefer badge system**: For status indicators, use badges over direct colors
4. **Chart colors**: Use JavaScript constants for data visualization
5. **Consistent patterns**: Follow established color usage patterns

## Quick Reference

```html
<!-- Backgrounds -->
<div class="bg-surface-primary">
  <!-- Main background -->
  <div class="bg-surface-secondary">
    <!-- Cards -->
    <div class="bg-surface-elevated">
      <!-- Modals -->

      <!-- Text -->
      <h1 class="text-content-primary">
        <!-- Headings -->
        <p class="text-content-body">
          <!-- Body text -->
          <span class="text-content-muted">
            <!-- Secondary text -->

            <!-- Interactive -->
            <button class="bg-primary-600 hover:bg-primary-700">
              <!-- Buttons -->
              <input class="focus:border-border-focus-primary" />
              <!-- Focus states -->

              <!-- Status -->
              <span class="text-success-600">
                <!-- Success -->
                <span class="text-error-600">
                  <!-- Errors -->
                  <span class="text-warning-600"> <!-- Warnings --></span></span
                ></span
              >
            </button></span
          >
        </p>
      </h1>
    </div>
  </div>
</div>
```
