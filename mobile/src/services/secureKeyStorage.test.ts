import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { getSeedPhrase, storeSeedPhrase } from './secureKeyStorage';

jest.mock('expo-secure-store', () => ({
  WHEN_PASSCODE_SET_THIS_DEVICE_ONLY: 6,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));
jest.mock('expo-local-authentication', () => ({ authenticateAsync: jest.fn() }));

const phrase = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
const items = new Map<string, { value: string; accessible?: number }>();
let legacyRemovalBlocked = false;

function alias(key: string, options?: SecureStore.SecureStoreOptions, authenticated = false) {
  return `${options?.keychainService ?? 'default'}:${key}:${authenticated ? 'auth' : 'plain'}`;
}

beforeEach(() => {
  items.clear();
  legacyRemovalBlocked = false;
  items.set(alias('wallet.seed.synthetic'), { value: phrase });
  jest.mocked(LocalAuthentication.authenticateAsync).mockResolvedValue({ success: true });
  jest
    .mocked(SecureStore.getItemAsync)
    .mockImplementation(
      async (key, options) =>
        items.get(alias(key, options))?.value ?? items.get(alias(key, options, true))?.value ?? null,
    );
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value, options) => {
    const target = alias(key, options, options?.requireAuthentication);
    items.set(target, { value, accessible: items.get(target)?.accessible ?? options?.keychainAccessible });
    if (options?.requireAuthentication && !legacyRemovalBlocked) items.delete(alias(key, options));
  });
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key, options) => {
    if (key === 'wallet.seed.synthetic' && legacyRemovalBlocked) return;
    items.delete(alias(key, options));
    items.delete(alias(key, options, true));
  });
});

it('refuses the legacy phrase when its authenticated replacement fails without losing the original', async () => {
  jest.mocked(SecureStore.setItemAsync).mockRejectedValue(new Error('storage unavailable'));
  await expect(getSeedPhrase('synthetic')).resolves.toBeNull();
  expect(items.get(alias('wallet.seed.synthetic'))?.value).toBe(phrase);
});

it('does not accept an authenticated alias while its preferred ungated original survives', async () => {
  legacyRemovalBlocked = true;
  await expect(getSeedPhrase('synthetic')).resolves.toBeNull();
  expect(items.get(alias('wallet.seed.synthetic'))?.value).toBe(phrase);
  expect([...items].some(([key, item]) => key.endsWith(':auth') && item.value === phrase)).toBe(true);
  legacyRemovalBlocked = false;
  await expect(getSeedPhrase('synthetic')).resolves.toBe(phrase);
  expect(items.has(alias('wallet.seed.synthetic'))).toBe(false);
});

it('uses a fresh gated namespace even when the old secured marker exists', async () => {
  items.set(alias('wallet.seed.secured.synthetic'), { value: 'true' });
  await expect(getSeedPhrase('synthetic')).resolves.toBe(phrase);
  expect(items.has(alias('wallet.seed.synthetic'))).toBe(false);
  const replacements = [...items].filter(([, item]) => item.value === phrase);
  expect(replacements).toHaveLength(1);
  expect(replacements[0][0]).not.toContain(':wallet.seed.synthetic:');
  expect(replacements[0][0]).toMatch(/:auth$/);
  expect(replacements[0][1].accessible).toBe(SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY);
});

it('keeps the legacy phrase recoverable until the replacement can be read back', async () => {
  const read = jest.mocked(SecureStore.getItemAsync).getMockImplementation()!;
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key, options) => {
    if (options?.requireAuthentication && items.has(alias(key, options, true)))
      throw new Error('authentication cancelled');
    return read(key, options);
  });
  await expect(getSeedPhrase('synthetic')).resolves.toBeNull();
  expect(SecureStore.setItemAsync).toHaveBeenCalled();
  expect(items.get(alias('wallet.seed.synthetic'))?.value).toBe(phrase);
});

it('does not read the legacy phrase after cancelled authentication', async () => {
  jest.mocked(LocalAuthentication.authenticateAsync).mockResolvedValue({ success: false, error: 'user_cancel' });
  await expect(getSeedPhrase('synthetic')).resolves.toBeNull();
  expect(jest.mocked(SecureStore.getItemAsync).mock.calls.some(([key]) => key === 'wallet.seed.synthetic')).toBe(false);
  expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
});

it('refuses a failed legacy read and a missing phrase', async () => {
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => {
    if (key === 'wallet.seed.synthetic') throw new Error('read unavailable');
    return null;
  });
  await expect(getSeedPhrase('synthetic')).resolves.toBeNull();
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  await expect(getSeedPhrase('missing')).resolves.toBeNull();
});

it('keeps new phrases gated and refuses an inaccessible secured phrase', async () => {
  await storeSeedPhrase('new', phrase);
  await expect(getSeedPhrase('new')).resolves.toBe(phrase);
  const write = jest.mocked(SecureStore.setItemAsync).mock.calls.find(([, value]) => value === phrase)!;
  expect(write[2]).toMatchObject({
    keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
    requireAuthentication: true,
  });
  const read = jest.mocked(SecureStore.getItemAsync).getMockImplementation()!;
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key, options) => {
    if (key === write[0]) throw new Error('authentication cancelled');
    return read(key, options);
  });
  await expect(getSeedPhrase('new')).resolves.toBeNull();
});
