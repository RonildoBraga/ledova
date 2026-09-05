import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';
const BIOMETRIC_LOGIN_KEY = 'settings.biometricLoginEnabled';
const BIOMETRIC_REFRESH_TOKEN_KEY = 'biometric.refreshToken';
const BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY = 'biometric.refreshToken.present';

const GATED_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
  requireAuthentication: true,
};

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export interface BiometricLoginState {
  enabled: boolean;

  ready: boolean;
}

export function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function getBiometricLoginState(): Promise<BiometricLoginState> {
  const enabled = (await SecureStore.getItemAsync(BIOMETRIC_LOGIN_KEY)) === 'true';
  const present = (await SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY)) === 'true';
  return { enabled, ready: enabled && present };
}

export async function storeTokens({ accessToken, refreshToken }: TokenPair): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  const { enabled } = await getBiometricLoginState();
  if (enabled) {
    await writeBiometricRefreshToken(refreshToken);
  }
}

export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  await deleteBiometricRefreshToken();
}

export async function enableBiometricLogin(): Promise<boolean> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    return false;
  }
  const stored = await writeBiometricRefreshToken(refreshToken);
  if (stored) {
    await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'true');
  }
  return stored;
}

export async function disableBiometricLogin(): Promise<void> {
  await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'false');
  await deleteBiometricRefreshToken();
}

export function readBiometricRefreshToken(authenticationPrompt: string): Promise<string | null> {
  return SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY, { authenticationPrompt });
}

export async function deleteBiometricRefreshToken(): Promise<void> {
  await SecureStore.deleteItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY);
  await SecureStore.deleteItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY);
}

async function writeBiometricRefreshToken(refreshToken: string): Promise<boolean> {
  try {
    await deleteBiometricRefreshToken();
    await SecureStore.setItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY, refreshToken, {
      ...GATED_OPTIONS,
      authenticationPrompt: 'Authenticate to keep biometric sign in',
    });
    await SecureStore.setItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY, 'true');
    return true;
  } catch {
    return false;
  }
}
