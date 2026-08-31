import { DESIGN_TOKENS, LIGHT_COLORS } from '@ledova/shared-constants';
import { useTheme } from './useTheme';

/**
 * Returns the correct color tokens for the current theme.
 * Use this instead of DESIGN_TOKENS.colors in components that pass
 * colors to JavaScript APIs (Chart.js, inline styles, etc.).
 * For CSS-only styling, Tailwind classes automatically respond to theme.
 */
export function useColors() {
  const { theme } = useTheme();
  return theme === 'light' ? LIGHT_COLORS : DESIGN_TOKENS.colors;
}
