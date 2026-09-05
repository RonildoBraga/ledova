import { useQuery } from '@tanstack/react-query';
import { getCurrentUserPreferences, CACHE_TIMING } from '@ledova/shared';
import apiClient from '../services/apiClient';
import { useAuth } from './useAuth';

/**
 * Custom hook that fetches user preferences with full nested objects.
 *
 * The API returns full objects for selectedAccount and selectedPortfolio,
 * so no additional queries are needed to get portfolio/account details.
 *
 * Note: User preferences are guaranteed to exist as they are created
 * during signup in the backend.
 *
 * @returns preferences - User preferences with nested selectedAccount and selectedPortfolio
 * @returns selectedPortfolio - Convenience accessor for the selected portfolio object
 * @returns selectedAccount - Convenience accessor for the selected account object
 * @returns isLoading - Loading state
 * @returns isError - Error state
 */
export function useSelectedPortfolio() {
  const { isAuthenticated } = useAuth();

  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const preferences = preferencesQuery.data?.data;

  return {
    portfolio: preferences?.selectedPortfolio ?? null,
    selectedPortfolio: preferences?.selectedPortfolio ?? null,
    selectedAccount: preferences?.selectedAccount ?? null,
    isLoading: preferencesQuery.isLoading,
  };
}
