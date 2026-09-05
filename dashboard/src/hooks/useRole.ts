import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMING, getCurrentUserPreferences } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useAuth } from './useAuth';

export type AccountRole = 'investor' | 'company' | 'both';

export function useRole() {
  const { isAuthenticated } = useAuth();

  const query = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const preferences = query.data?.data;
  const role: AccountRole = (preferences?.selectedAccount as { role?: AccountRole })?.role ?? 'investor';

  return {
    role,
    isInvestor: role === 'investor' || role === 'both',
    isCompany: role === 'company' || role === 'both',
    isLoading: query.isLoading,
  };
}
