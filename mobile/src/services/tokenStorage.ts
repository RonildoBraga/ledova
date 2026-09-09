import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';
const SESSION_KEY = 'session.tokens.v2';
const SESSION_RETIRED_KEY = 'session.retired.v1';
const BIOMETRIC_LOGIN_KEY = 'settings.biometricLoginEnabled';
const BIOMETRIC_REFRESH_TOKEN_KEY = 'biometric.refreshToken';
const BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY = 'biometric.refreshToken.present';

const SESSION_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

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

let operations: Promise<unknown> = Promise.resolve();
let sessionGeneration = 0;
let retirementUnavailable = false;

function serially<T>(operation: () => Promise<T>): Promise<T> {
  const result = operations.then(operation);
  operations = result.catch(() => undefined);
  return result;
}

async function removeLegacyTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  if ((await SecureStore.getItemAsync(ACCESS_TOKEN_KEY)) || (await SecureStore.getItemAsync(REFRESH_TOKEN_KEY))) {
    throw new Error('Legacy session removal did not complete.');
  }
}

async function persistPair(pair: TokenPair): Promise<void> {
  const value = JSON.stringify(pair);
  await SecureStore.setItemAsync(SESSION_KEY, value, SESSION_OPTIONS);
  if ((await SecureStore.getItemAsync(SESSION_KEY)) !== value) throw new Error('Session storage did not complete.');
  await removeLegacyTokens();
  await SecureStore.setItemAsync(SESSION_RETIRED_KEY, 'false');
  if ((await SecureStore.getItemAsync(SESSION_RETIRED_KEY)) !== 'false') {
    throw new Error('Session activation did not complete.');
  }
  retirementUnavailable = false;
}

async function readPair(): Promise<TokenPair | null> {
  try {
    if (retirementUnavailable || (await SecureStore.getItemAsync(SESSION_RETIRED_KEY)) === 'true') return null;
    const stored = await SecureStore.getItemAsync(SESSION_KEY);
    if (stored) {
      const pair: TokenPair = JSON.parse(stored);
      if (
        typeof pair.accessToken !== 'string' ||
        !pair.accessToken ||
        typeof pair.refreshToken !== 'string' ||
        !pair.refreshToken
      ) {
        return null;
      }
      await removeLegacyTokens();
      return pair;
    }
    const accessToken = await SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
    const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
    if (!accessToken || !refreshToken) {
      await removeLegacyTokens();
      return null;
    }
    const pair = { accessToken, refreshToken };
    await persistPair(pair);
    return pair;
  } catch {
    return null;
  }
}

export function getAccessToken(): Promise<string | null> {
  return serially(async () => (await readPair())?.accessToken ?? null);
}

export function getRefreshToken(): Promise<string | null> {
  return serially(async () => (await readPair())?.refreshToken ?? null);
}

async function readBiometricLoginState(): Promise<BiometricLoginState> {
  const enabled = (await SecureStore.getItemAsync(BIOMETRIC_LOGIN_KEY)) === 'true';
  const present = (await SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY)) === 'true';
  return { enabled, ready: enabled && present };
}

export function getBiometricLoginState(): Promise<BiometricLoginState> {
  return serially(readBiometricLoginState);
}

export function captureRefreshSession(refreshToken: string): Promise<number> {
  const generation = sessionGeneration;
  return serially(async () => {
    const pair = await readPair();
    if (generation !== sessionGeneration || (pair && pair.refreshToken !== refreshToken)) {
      throw new Error('The saved session changed.');
    }
    return generation;
  });
}

export async function storeTokens(
  { accessToken, refreshToken }: TokenPair,
  expectedGeneration?: number,
): Promise<void> {
  if (expectedGeneration === undefined) sessionGeneration++;
  await serially(async () => {
    if (expectedGeneration !== undefined) {
      if (expectedGeneration !== sessionGeneration) throw new Error('The saved session changed.');
      sessionGeneration++;
    }
    const generation = sessionGeneration;
    if (!accessToken || !refreshToken) throw new Error('A complete session is required.');
    await persistPair({ accessToken, refreshToken });
    const { enabled } = await readBiometricLoginState();
    if (enabled) await writeBiometricRefreshToken(refreshToken);
    if (expectedGeneration !== undefined && generation !== sessionGeneration) {
      throw new Error('The saved session changed.');
    }
  });
}

export async function clearTokens(expectedGeneration?: number): Promise<void> {
  if (expectedGeneration === undefined) sessionGeneration++;
  await serially(async () => {
    if (expectedGeneration !== undefined) {
      if (expectedGeneration !== sessionGeneration) return;
      sessionGeneration++;
    }
    retirementUnavailable = true;
    await SecureStore.setItemAsync(SESSION_RETIRED_KEY, 'true');
    if ((await SecureStore.getItemAsync(SESSION_RETIRED_KEY)) !== 'true') {
      throw new Error('Session retirement did not complete.');
    }
    const results = await Promise.allSettled([
      SecureStore.deleteItemAsync(SESSION_KEY),
      removeLegacyTokens(),
      removeBiometricRefreshToken(),
    ]);
    const failure = results.find((result) => result.status === 'rejected');
    if (failure?.status === 'rejected') throw failure.reason;
    if (await SecureStore.getItemAsync(SESSION_KEY)) throw new Error('Session removal did not complete.');
    retirementUnavailable = false;
  });
}

export function enableBiometricLogin(): Promise<boolean> {
  return serially(async () => {
    const refreshToken = (await readPair())?.refreshToken;
    if (!refreshToken) return false;
    const stored = await writeBiometricRefreshToken(refreshToken);
    if (stored) await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'true');
    return stored;
  });
}

export function disableBiometricLogin(): Promise<void> {
  return serially(async () => {
    await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'false');
    await removeBiometricRefreshToken();
  });
}

export function readBiometricRefreshToken(authenticationPrompt: string): Promise<string | null> {
  const generation = sessionGeneration;
  return serially(async () => {
    if (!(await readBiometricLoginState()).ready) return null;
    const value = await SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY, { authenticationPrompt });
    return generation === sessionGeneration ? value : null;
  });
}

export function deleteBiometricRefreshToken(): Promise<void> {
  return serially(removeBiometricRefreshToken);
}

async function removeBiometricRefreshToken(): Promise<void> {
  await SecureStore.setItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY, 'false');
  if ((await SecureStore.getItemAsync(BIOMETRIC_REFRESH_TOKEN_PRESENT_KEY)) !== 'false') {
    throw new Error('Biometric session retirement did not complete.');
  }
  await SecureStore.deleteItemAsync(BIOMETRIC_REFRESH_TOKEN_KEY);
}

async function writeBiometricRefreshToken(refreshToken: string): Promise<boolean> {
  try {
    await removeBiometricRefreshToken();
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
