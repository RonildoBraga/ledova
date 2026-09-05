import { DESIGN_TOKENS, LIGHT_COLORS } from '@ledova/shared';
import { useTheme } from './useTheme';

export function useColors() {
  const { theme } = useTheme();
  return theme === 'light' ? LIGHT_COLORS : DESIGN_TOKENS.colors;
}
