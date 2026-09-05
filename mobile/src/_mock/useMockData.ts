export function useMockData(): boolean {
  const envValue = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

  if (envValue === undefined || envValue === null) {
    return true;
  }

  return envValue.toLowerCase() === 'true';
}
