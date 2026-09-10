import * as DocumentPicker from 'expo-document-picker';
import * as SecureStore from 'expo-secure-store';
import { pickDocumentCopy } from './documentCopies';
import { subscribeSession } from './sessionScope';
import { clearTokens, getAccessToken, storeTokens } from './tokenStorage';
import { files, nativeBehavior, pickedFile, resetFiles } from '../testSupport/documentFiles';

jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-file-system', () => jest.requireActual('../testSupport/documentFiles').nativeFileSystem);
jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

beforeEach(async () => {
  resetFiles();
  const items = new Map<string, string>();
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => items.get(key) ?? null);
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
    items.set(key, value);
  });
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
    items.delete(key);
  });
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  await clearTokens();
});

it.each([false, true])(
  'retires credentials when document cleanup has a native constructor failure: %s',
  async (fail) => {
    await storeTokens({ accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' });
    jest.mocked(DocumentPicker.getDocumentAsync).mockResolvedValue(pickedFile());
    const copy = (await pickDocumentCopy(() => true))!;
    const unsubscribe = subscribeSession(() => copy.retire());
    try {
      await expect(getAccessToken()).resolves.toBe('synthetic-access');
      expect(files.has(copy.file.uri)).toBe(true);
      nativeBehavior.failManagedConstruction = fail;
      await expect(clearTokens()).resolves.toBeUndefined();
      await expect(getAccessToken()).resolves.toBeNull();
      expect(() => copy.retire()).not.toThrow();
      expect(files.has(copy.file.uri)).toBe(fail);
    } finally {
      unsubscribe();
      nativeBehavior.failManagedConstruction = false;
      copy.retire();
    }
    expect(files.has(copy.file.uri)).toBe(false);
  },
);
