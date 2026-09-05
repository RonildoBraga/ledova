import { useQuery } from '@tanstack/react-query';
import { getExchangeRate, CACHE_TIMING, formatCurrency } from '@ledova/shared';
import type { DisplayCurrency } from '@ledova/shared';
import { apiClient } from '../services/apiClient';
import { useUserPreferences } from './useUserPreferences';

/**
 * Hook that provides currency-aware formatting.
 *
 * Reads the user's display currency preference and fetches the
 * exchange rate to convert USD-denominated values for display.
 */
export function useCurrency() {
  const { preferences } = useUserPreferences();
  const displayCurrency: DisplayCurrency = preferences?.displayCurrency ?? 'AUD';

  const exchangeRateQuery = useQuery({
    queryKey: ['exchangeRate', displayCurrency],
    queryFn: () => getExchangeRate(apiClient, displayCurrency),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    enabled: displayCurrency !== 'USD',
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
