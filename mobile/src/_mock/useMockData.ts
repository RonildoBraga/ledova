/**
 * Central Mock Data Control
 *
 * This file provides a centralized way to control mock data across the entire application.
 * All hooks should use this utility instead of defining their own USE_MOCK_DATA constants.
 *
 * Usage in hooks:
 * ```typescript
 * import { useMockData } from '../../_mock/useMockData';
 *
 * export function useMyHook() {
 *   const USE_MOCK_DATA = useMockData();
 *   // ... rest of hook logic
 * }
 * ```
 */

/**
 * Returns whether mock data should be used based on environment variable
 * @returns {boolean} true if mock data should be used, false otherwise
 */
export function useMockData(): boolean {
  const envValue = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

  // Default to true if not set (for development convenience)
  if (envValue === undefined || envValue === null) {
    return true;
  }

  // Handle string boolean values
  return envValue.toLowerCase() === 'true';
}
