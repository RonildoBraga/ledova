export function useMockData(): boolean {
  const envValue = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

  return envValue?.toLowerCase() === 'true';
}
