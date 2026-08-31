import { SunIcon, MoonIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared-constants';
import { useTheme } from '@hooks/useTheme';

const ICON_SIZE = DESIGN_TOKENS.icon.sizes.md;

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="relative flex items-center justify-center w-10 h-10 rounded-full hover:bg-surface-tertiary/50 transition-colors"
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? (
        <SunIcon size={ICON_SIZE} className="text-text-muted" weight="duotone" />
      ) : (
        <MoonIcon size={ICON_SIZE} className="text-text-muted" weight="duotone" />
      )}
    </button>
  );
}
