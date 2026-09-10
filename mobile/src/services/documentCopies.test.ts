import * as DocumentPicker from 'expo-document-picker';
import { pickDocumentCopy } from './documentCopies';
import {
  cache,
  files,
  nativeBehavior,
  nativeFileSystem,
  operations,
  pickedFile,
  resetFiles,
  sticky,
  unreadable,
} from '../testSupport/documentFiles';

jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-file-system', () => jest.requireActual('../testSupport/documentFiles').nativeFileSystem);

const pick = jest.mocked(DocumentPicker.getDocumentAsync);

beforeEach(() => {
  resetFiles();
  pick.mockReset();
  jest.spyOn(console, 'warn').mockImplementation(() => {});
});

it('adopts a private copy, preserves the provider original, and waits for every admitted consumer', async () => {
  const result = pickedFile();
  const original = 'content://provider/original.pdf';
  files.set(original, { size: 5, content: 'provider-original' });
  pick.mockResolvedValue(result);
  const copy = (await pickDocumentCopy(() => true))!;
  expect(files.has(result.assets[0].uri)).toBe(false);
  expect(files.get(copy.file.uri)?.content).toBe('document-1');
  const releaseFirst = copy.acquire();
  const releaseSecond = copy.acquire();
  copy.retire();
  releaseFirst();
  releaseFirst();
  expect(files.has(copy.file.uri)).toBe(true);
  releaseSecond();
  expect(files.has(copy.file.uri)).toBe(false);
  expect(files.get(original)?.content).toBe('provider-original');
  expect(() => copy.acquire()).toThrow();
});

it('verifies source retirement when an older native move only copies the bytes', async () => {
  nativeBehavior.copyOnMove = true;
  const result = pickedFile();
  pick.mockResolvedValue(result);
  const copy = (await pickDocumentCopy(() => true))!;
  expect(files.has(result.assets[0].uri)).toBe(false);
  expect(files.has(copy.file.uri)).toBe(true);
  copy.retire();

  const stuck = pickedFile(2);
  sticky.add(stuck.assets[0].uri);
  pick.mockResolvedValue(stuck);
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('retire');
  expect(files.has(stuck.assets[0].uri)).toBe(true);
  expect([...files.keys()].some((uri) => uri.includes('ledova-upload-copies-v1'))).toBe(false);
});

it.each([
  'content://provider/private.pdf',
  `${cache}elsewhere.pdf`,
  `${cache}DocumentPicker/../original.pdf`,
  `${cache}DocumentPicker/not-a-generated-file.pdf`,
])('refuses an unowned result without touching it: %s', async (uri) => {
  files.set(uri, { size: 5, content: 'untouched' });
  pick.mockResolvedValue({ canceled: false, assets: [{ uri, name: 'private.pdf', size: 5, lastModified: 0 }] });
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('private copy');
  expect(files.get(uri)?.content).toBe('untouched');
  expect(operations.some((operation) => operation.uri === uri)).toBe(false);
});

it('retires every returned private copy when the native picker unexpectedly supplies multiple files', async () => {
  const first = pickedFile(1);
  const second = pickedFile(2);
  const external = 'content://provider/untouched';
  files.set(external, { size: 5, content: 'provider-original' });
  pick.mockResolvedValue({
    canceled: false,
    assets: [...first.assets, ...second.assets, { uri: external, name: 'original', lastModified: 0 }],
  });
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('one document');
  expect(files.has(first.assets[0].uri)).toBe(false);
  expect(files.has(second.assets[0].uri)).toBe(false);
  expect(files.has(external)).toBe(true);
});

it.each([0, 10 * 1024 * 1024 + 1])('retires a returned copy with refused actual size %s', async (size) => {
  const result = pickedFile(1, size);
  pick.mockResolvedValue(result);
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('10 MB');
  expect(files.has(result.assets[0].uri)).toBe(false);
});

it('refuses a partial copy and permits a complete copy at the limit', async () => {
  const partial = pickedFile();
  partial.assets[0].size++;
  pick.mockResolvedValue(partial);
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('incomplete');
  expect(files.has(partial.assets[0].uri)).toBe(false);
  pick.mockResolvedValue(pickedFile(2, 10 * 1024 * 1024));
  const copy = (await pickDocumentCopy(() => true))!;
  expect(files.get(copy.file.uri)?.size).toBe(10 * 1024 * 1024);
  copy.retire();
});

it('cleans only the fixed managed slots after a fresh module load and refuses unreadable or sticky slots', async () => {
  const retired = `${cache}ledova-upload-copies-v1/slot-0`;
  const denied = `${cache}ledova-upload-copies-v1/slot-1`;
  const stuck = `${cache}ledova-upload-copies-v1/slot-2`;
  const unrelated = `${cache}ledova-upload-copies-v1/unrelated`;
  for (const uri of [retired, denied, stuck, unrelated]) files.set(uri, { size: 5, content: 'leftover' });
  unreadable.add(denied);
  sticky.add(stuck);
  pick.mockResolvedValue({ canceled: true, assets: null });
  await jest.isolateModulesAsync(async () => {
    jest.doMock('expo-file-system', () => nativeFileSystem);
    jest.doMock('expo-document-picker', () => DocumentPicker);
    const fresh = jest.requireActual<typeof import('./documentCopies')>('./documentCopies');
    await fresh.pickDocumentCopy(() => true);
  });
  expect(files.has(retired)).toBe(false);
  expect(files.has(denied)).toBe(true);
  expect(files.has(stuck)).toBe(true);
  expect(files.has(unrelated)).toBe(true);
  expect(new Set(operations.map(({ uri }) => uri)).size).toBe(16);
  expect(operations.some(({ kind, uri }) => kind === 'delete' && uri === denied)).toBe(false);
  expect(pick).toHaveBeenCalledTimes(1);
});

it('does not reuse a leased slot while another picker opens, and retries cleanup after deletion becomes available', async () => {
  pick.mockResolvedValue(pickedFile(1));
  const first = (await pickDocumentCopy(() => true))!;
  const release = first.acquire();
  first.retire();
  pick.mockResolvedValue(pickedFile(2));
  const second = (await pickDocumentCopy(() => true))!;
  expect(second.file.uri).not.toBe(first.file.uri);
  expect(files.get(first.file.uri)?.content).toBe('document-1');
  sticky.add(first.file.uri);
  release();
  expect(files.has(first.file.uri)).toBe(true);
  sticky.delete(first.file.uri);
  pick.mockResolvedValue({ canceled: true, assets: null });
  await pickDocumentCopy(() => true);
  expect(files.has(first.file.uri)).toBe(false);
  expect(files.has(second.file.uri)).toBe(true);
  second.retire();
});

it('handles a provider rejection without exposing its message and releases the picker for a later selection', async () => {
  pick.mockRejectedValue(new Error('provider/private/secret.pdf'));
  await expect(pickDocumentCopy(() => true)).rejects.toThrow('Could not read the document');
  pick.mockResolvedValue(pickedFile());
  const copy = (await pickDocumentCopy(() => true))!;
  expect(files.has(copy.file.uri)).toBe(true);
  copy.retire();
});
