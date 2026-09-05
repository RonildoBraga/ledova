import { useCallback, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCurrentUserPreferences, upsertCurrentUserPreferences, CACHE_TIMING } from '@ledova/shared';
import type { Theme } from '@ledova/shared';
import { useAuth } from './useAuth';
import apiClient from '@services/apiClient';

const STORAGE_KEY = 'ledova-theme';

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  if (theme === 'light') {
    html.classList.add('theme-light');
    html.classList.remove('theme-dark');
  } else {
    html.classList.add('theme-dark');
    html.classList.remove('theme-light');
  }
  localStorage.setItem(STORAGE_KEY, theme);
}

function getStoredTheme(): Theme {
  return (localStorage.getItem(STORAGE_KEY) as Theme) || 'dark';
}

export function useTheme() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const theme: Theme = useMemo(() => {
    const apiTheme = preferencesQuery.data?.data?.theme;
    return apiTheme || getStoredTheme();
  }, [preferencesQuery.data?.data?.theme]);

  // Sync API preference to localStorage on fetch
  useEffect(() => {
    const apiTheme = preferencesQuery.data?.data?.theme;
    if (apiTheme) {
      applyTheme(apiTheme);
    }
  }, [preferencesQuery.data?.data?.theme]);

  // Apply theme on mount (from localStorage, before API responds)
  useEffect(() => {
    applyTheme(getStoredTheme());
  }, []);

  const mutation = useMutation({
    mutationFn: (newTheme: Theme) => upsertCurrentUserPreferences(apiClient, { theme: newTheme }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
    },
  });

  const toggleTheme = useCallback(() => {
    const newTheme: Theme = theme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
    if (isAuthenticated) {
      mutation.mutate(newTheme);
    }
  }, [theme, isAuthenticated, mutation]);

  return { theme, toggleTheme };
}
