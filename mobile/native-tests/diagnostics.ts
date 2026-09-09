export class NativeProbeAssertion extends Error {}

export function failureCategory(error: unknown): 'assertion' | 'native-keychain' | 'native-function' | 'unknown' {
  if (error instanceof NativeProbeAssertion) return 'assertion';
  if (typeof error === 'object' && error !== null && 'code' in error) {
    if (error.code === 'ERR_KEY_CHAIN') return 'native-keychain';
    if (error.code === 'ERR_FUNCTION_CALL') return 'native-function';
  }
  return 'unknown';
}
