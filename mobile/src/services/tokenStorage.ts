import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';
const BIOMETRIC_LOGIN_KEY = 'settings.biometricLoginEnabled';
const BIOMETRIC_REFRESH_TOKEN_KEY = 'biometric.refreshToken';
const BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY = 'biometric.refreshToken.present';

// The same OS-enforced pattern secureKeyStorage.ts uses for seed phrases: the Keychain / Keystore
// entry is readable only after the device owner authenticates and only on a device with a passcode.
const GATED_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
  requireAuthentication: true,
};

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export interface BiometricLoginState {
  /** The user's preference; it survives sign-out so the next password sign-in stores a gated copy again. */
  enabled: boolean;
  /** A biometric-gated refresh token is on the device. */
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

/**
 * Stores a freshly issued pair (sign-in, email verification, every refresh). The backend blacklists
 * the refresh token it was given, so when biometric sign in is enabled the gated copy follows the
 * rotation and never goes stale.
 */
export async function storeTokens({ accessToken, refreshToken }: TokenPair): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  const { enabled } = await getBiometricLoginState();
  if (enabled) {
    await writeBiometricRefreshToken(refreshToken);
  }
}

/** Every token on the device: the pair and the gated copy. The biometric preference is kept. */
export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  await deleteBiometricRefreshToken();
}

/** Gates a copy of the current session's refresh token; the preference is set only once that worked. */
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

/**
 * Shows the OS prompt. Resolves null when there is no entry or the OS invalidated it after a
 * biometric change; rejects when the user cancels or fails the prompt.
 */
export function readBiometricRefreshToken(authenticationPrompt: string): Promise<string | null> {
  return SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY, { authenticationPrompt });
}

export async function deleteBiometricRefreshToken(): Promise<void> {
  await SecureStore.deleteItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY);
  await SecureStore.deleteItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY);
}

/**
 * iOS prompts only when an existing gated entry is updated, so the old copy is deleted first and the
 * rotated token is added without a prompt. Android asks for biometrics on every gated write and
 * refuses one while the app is in the background; then no copy is kept and the next password
 * sign-in stores one again.
 */
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
