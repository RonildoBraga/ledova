import { useQuery } from '@tanstack/react-query';
import { getCurrentUserPreferences, getExchangeRate, CACHE_TIMING, formatCurrency } from '@ledova/shared';
import type { DisplayCurrency } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useAuth } from './useAuth';

export function useCurrency() {
  const { isAuthenticated } = useAuth();

  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const displayCurrency: DisplayCurrency = preferencesQuery.data?.data?.displayCurrency ?? 'AUD';

  const exchangeRateQuery = useQuery({
    queryKey: ['exchangeRate', displayCurrency],
    queryFn: () => getExchangeRate(apiClient, displayCurrency),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    enabled: isAuthenticated && displayCurrency !== 'USD',
  });

  const rate = displayCurrency === 'USD' ? 1 : parseFloat(exchangeRateQuery.data?.data?.rate ?? '0') || 0;

  const formatDisplayCurrency = (usdValue?: number, decimals: number = 2): string => {
    if (usdValue === undefined || usdValue === null || isNaN(usdValue)) return '—';
    if (displayCurrency === 'USD') {
      return formatCurrency(usdValue, { currency: 'USD', locale: 'en-US', decimals });
    }
    if (!rate) return '—';
    return formatCurrency(usdValue * rate, { currency: displayCurrency, locale: 'en-AU', decimals });
  };

  return {
    displayCurrency,
    exchangeRate: rate,
    formatDisplayCurrency,
    isLoading: exchangeRateQuery.isLoading,
  };
}
