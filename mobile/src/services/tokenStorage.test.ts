import * as SecureStore from 'expo-secure-store';
import {
  clearTokens,
  disableBiometricLogin,
  enableBiometricLogin,
  getAccessToken,
  getBiometricLoginState,
  getRefreshToken,
  readBiometricRefreshToken,
  storeTokens,
} from './tokenStorage';

jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED: 0,
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 6,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const pair = { accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' };
const items = new Map<string, { value: string; accessible: number; authenticated: boolean }>();

beforeEach(async () => {
  items.clear();
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => items.get(key)?.value ?? null);
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
    items.delete(key);
  });
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value, options) => {
    const existing = items.get(key);
    items.set(key, {
      value,
      accessible: existing?.accessible ?? options?.keychainAccessible ?? SecureStore.WHEN_UNLOCKED,
      authenticated: existing?.authenticated ?? options?.requireAuthentication ?? false,
    });
  });
  await clearTokens();
  items.clear();
  jest.clearAllMocks();
});

it('stores the ordinary pair in device-only storage without requiring biometrics', async () => {
  await storeTokens(pair);
  await expect(getAccessToken()).resolves.toBe(pair.accessToken);
  await expect(getRefreshToken()).resolves.toBe(pair.refreshToken);
  const secrets = [...items.values()].filter(({ value }) => value.includes('synthetic-'));
  expect(secrets.length).toBeGreaterThan(0);
  for (const item of secrets) {
    expect(item.accessible).toBe(SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY);
    expect(item.authenticated).toBe(false);
  }
});

it('migrates an existing pair into a fresh item and retires both default-policy originals', async () => {
  await SecureStore.setItemAsync('accessToken', pair.accessToken);
  await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
  await expect(Promise.all([getAccessToken(), getRefreshToken()])).resolves.toEqual([
    pair.accessToken,
    pair.refreshToken,
  ]);
  expect(items.has('accessToken')).toBe(false);
  expect(items.has('refreshToken')).toBe(false);
  const migrated = [...items.values()].find(({ value }) => value.includes(pair.refreshToken));
  expect(migrated?.accessible).toBe(SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY);
});

it('does not expose legacy credentials if a migration write fails', async () => {
  await SecureStore.setItemAsync('accessToken', pair.accessToken);
  await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
  jest.mocked(SecureStore.setItemAsync).mockRejectedValue(new Error('write unavailable'));
  await expect(getAccessToken()).resolves.toBeNull();
  expect(items.get('refreshToken')?.value).toBe(pair.refreshToken);
});

it('does not expose credentials while legacy deletion is incomplete', async () => {
  await SecureStore.setItemAsync('accessToken', pair.accessToken);
  await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
  jest.mocked(SecureStore.deleteItemAsync).mockResolvedValue(undefined);
  await expect(getRefreshToken()).resolves.toBeNull();
  expect(items.has('refreshToken')).toBe(true);
});

it('refuses an incomplete old session', async () => {
  await SecureStore.setItemAsync('accessToken', pair.accessToken);
  await expect(getAccessToken()).resolves.toBeNull();
});

it('serializes a migration and sign-out so the session cannot be resurrected', async () => {
  await SecureStore.setItemAsync('accessToken', pair.accessToken);
  await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
  await Promise.all([getAccessToken(), clearTokens()]);
  await expect(getAccessToken()).resolves.toBeNull();
  await expect(getRefreshToken()).resolves.toBeNull();
  expect([...items.values()].some(({ value }) => value.includes('synthetic-'))).toBe(false);
});

it('preserves the optional biometric copy and rotates it with the ordinary pair', async () => {
  await storeTokens(pair);
  await expect(getBiometricLoginState()).resolves.toEqual({ enabled: false, ready: false });
  await expect(enableBiometricLogin()).resolves.toBe(true);
  const gated = items.get('biometric.refreshToken');
  expect(gated).toMatchObject({
    value: pair.refreshToken,
    accessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
    authenticated: true,
  });
  await storeTokens({ accessToken: 'rotated-access', refreshToken: 'rotated-refresh' });
  await expect(readBiometricRefreshToken('Authenticate')).resolves.toBe('rotated-refresh');
  await disableBiometricLogin();
  await expect(getBiometricLoginState()).resolves.toEqual({ enabled: false, ready: false });
  await expect(getAccessToken()).resolves.toBe('rotated-access');
});

it('finishes sign-out after an already-started biometric enable without restoring secrets', async () => {
  await storeTokens(pair);
  let signalWrite!: () => void;
  let finishWrite!: () => void;
  const entered = new Promise<void>((resolve) => {
    signalWrite = resolve;
  });
  const released = new Promise<void>((resolve) => {
    finishWrite = resolve;
  });
  const write = jest.mocked(SecureStore.setItemAsync).getMockImplementation()!;
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value, options) => {
    if (key === 'biometric.refreshToken') {
      signalWrite();
      await released;
    }
    return write(key, value, options);
  });
  const enabling = enableBiometricLogin();
  await entered;
  const clearing = clearTokens();
  await new Promise<void>((resolve) => setImmediate(resolve));
  finishWrite();
  await Promise.all([enabling, clearing]);
  await expect(getAccessToken()).resolves.toBeNull();
  await expect(getBiometricLoginState()).resolves.toMatchObject({ ready: false });
  expect(items.has('biometric.refreshToken')).toBe(false);
});

it('refuses a sticky session after sign-out, including a fresh storage-module load', async () => {
  await storeTokens(pair);
  const sessionKey = [...items].find(([, item]) => item.value.includes(pair.accessToken))![0];
  async function freshAccessToken() {
    let value: string | null = null;
    await jest.isolateModulesAsync(async () => {
      jest.doMock('expo-secure-store', () => SecureStore);
      const fresh = jest.requireActual<typeof import('./tokenStorage')>('./tokenStorage');
      value = await fresh.getAccessToken();
    });
    return value;
  }
  await expect(freshAccessToken()).resolves.toBe(pair.accessToken);
  const remove = jest.mocked(SecureStore.deleteItemAsync).getMockImplementation()!;
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key, options) => {
    if (key !== sessionKey) await remove(key, options);
  });
  await expect(clearTokens()).rejects.toThrow();
  expect(items.get(sessionKey)?.value).toContain(pair.accessToken);
  await expect(getAccessToken()).resolves.toBeNull();
  await expect(freshAccessToken()).resolves.toBeNull();
  await storeTokens({ accessToken: 'fresh-access', refreshToken: 'fresh-refresh' });
  await expect(freshAccessToken()).resolves.toBe('fresh-access');
});
