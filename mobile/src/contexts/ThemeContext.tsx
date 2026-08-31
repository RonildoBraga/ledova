import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DESIGN_TOKENS, LIGHT_COLORS } from '@ledova/shared-constants';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { upsertCurrentUserPreferences } from '@ledova/shared-services';
import type { Theme } from '@ledova/shared-types';
import { apiClient } from '../services/apiClient';
import { useAuth } from '../hooks/useAuth';
import { useUserPreferences } from '../hooks/useUserPreferences';

const STORAGE_KEY = 'ledova-theme';

const DARK_THEME = {
  colors: DESIGN_TOKENS.colors,
  spacing: DESIGN_TOKENS.spacing,
  borderRadius: DESIGN_TOKENS.borderRadius,
  fontSize: DESIGN_TOKENS.fontSize,
  fontWeight: DESIGN_TOKENS.fontWeight,
  lineHeight: DESIGN_TOKENS.lineHeight,
  layout: DESIGN_TOKENS.layout,
  shadows: DESIGN_TOKENS.shadows,
  animation: DESIGN_TOKENS.animation,
  zIndex: DESIGN_TOKENS.zIndex,
  icon: DESIGN_TOKENS.icon,
} as const;

const LIGHT_THEME = {
  ...DARK_THEME,
  colors: LIGHT_COLORS,
  icon: {
    ...DESIGN_TOKENS.icon,
    colors: {
      primary: LIGHT_COLORS.text.primary,
      muted: LIGHT_COLORS.text.subtle,
    },
  },
} as const;

type ThemeObject = typeof DARK_THEME;

interface ThemeContextValue {
  theme: ThemeObject;
  themeMode: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DARK_THEME,
  themeMode: 'dark',
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeMode, setThemeMode] = useState<Theme>('dark');
  const { isAuthenticated } = useAuth();
  const { preferences } = useUserPreferences();
  const queryClient = useQueryClient();

  // Load from AsyncStorage on mount
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((stored) => {
      if (stored === 'light' || stored === 'dark') {
        setThemeMode(stored);
      }
    });
  }, []);

  // Sync from API when preferences load
  useEffect(() => {
    if (preferences?.theme === 'light' || preferences?.theme === 'dark') {
      setThemeMode(preferences.theme);
      AsyncStorage.setItem(STORAGE_KEY, preferences.theme);
    }
  }, [preferences?.theme]);

  const mutation = useMutation({
    mutationFn: (newTheme: Theme) => upsertCurrentUserPreferences(apiClient, { theme: newTheme }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
    },
  });

  const toggleTheme = useCallback(() => {
    const newTheme: Theme = themeMode === 'dark' ? 'light' : 'dark';
    setThemeMode(newTheme);
    AsyncStorage.setItem(STORAGE_KEY, newTheme);
    if (isAuthenticated) {
      mutation.mutate(newTheme);
    }
  }, [themeMode, isAuthenticated, mutation]);

  const theme = useMemo(() => (themeMode === 'light' ? LIGHT_THEME : DARK_THEME), [themeMode]);

  const value = useMemo(() => ({ theme, themeMode, toggleTheme }), [theme, themeMode, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/**
 * Returns the theme object for the current theme mode.
 */
export function useAppTheme() {
  return useContext(ThemeContext).theme;
}

/**
 * Returns theme mode and toggle function (for settings/toggle UI).
 */
export function useThemeMode() {
  const { themeMode, toggleTheme } = useContext(ThemeContext);
  return { themeMode, toggleTheme };
}

/**
 * Creates theme-aware styles. Styles are memoized and only recompute when the theme changes.
 */
export function useThemedStyles<T extends StyleSheet.NamedStyles<T>>(stylesFn: (theme: ThemeObject) => T): T {
  const theme = useContext(ThemeContext).theme;

  return useMemo(() => StyleSheet.create(stylesFn(theme)), [stylesFn, theme]);
}

export const overlayColors = {
  modal: 'rgba(0, 0, 0, 0.5)',
} as const;

export const createStyles = StyleSheet.create;
