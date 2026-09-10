import React from 'react';
import { act, renderHook } from '@testing-library/react-native';
import * as DocumentPicker from 'expo-document-picker';
import { useDocumentUpload } from './useDocumentUpload';
import { getAccessToken } from '../services/tokenStorage';
import { invalidateSessionScope } from '../services/sessionScope';
import { files, pickedFile, resetFiles } from '../testSupport/documentFiles';

jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-file-system', () => jest.requireActual('../testSupport/documentFiles').nativeFileSystem);
jest.mock('../services/tokenStorage', () => ({ getAccessToken: jest.fn() }));

const pick = jest.mocked(DocumentPicker.getDocumentAsync);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  resetFiles();
  pick.mockReset();
  jest.mocked(getAccessToken).mockResolvedValue('synthetic-access');
});

it('retains a refused claim for retry and removes it only after the successful retry finishes', async () => {
  pick.mockResolvedValue(pickedFile());
  const { result } = await renderHook(() => useDocumentUpload('account-a'));
  await act(async () => {
    expect(await result.current!.pick()).toBe(true);
  });
  const selected = result.current!.file!;
  const refused = jest.fn(async () => {
    throw new Error('claim refused');
  });
  await act(async () => {
    await expect(result.current!.submit(refused)).rejects.toThrow('claim refused');
  });
  expect(result.current!.file).toEqual(selected);
  expect(files.get(selected.uri)?.content).toBe('document-1');
  const accepted = jest.fn(async ({ file }) => {
    expect(file).toEqual(selected);
    expect(files.has(file.uri)).toBe(true);
  });
  await act(async () => {
    expect(await result.current!.submit(accepted)).toBe(true);
  });
  expect(accepted).toHaveBeenCalledWith(expect.objectContaining({ owner: 'account-a', file: selected }));
  expect(result.current!.file).toBeNull();
  expect(files.has(selected.uri)).toBe(false);
});

it('keeps the previous selection after a canceled or failed replacement', async () => {
  pick.mockResolvedValue(pickedFile());
  const { result } = await renderHook(() => useDocumentUpload('account-a'));
  await act(async () => {
    await result.current!.pick();
  });
  const selected = result.current!.file!;
  pick.mockResolvedValue({ canceled: true, assets: null });
  await act(async () => {
    expect(await result.current!.pick()).toBe(false);
  });
  pick.mockRejectedValue(new Error('provider failed'));
  await act(async () => {
    await expect(result.current!.pick()).rejects.toThrow('Could not read');
  });
  expect(result.current!.file).toEqual(selected);
  expect(files.has(selected.uri)).toBe(true);
  await act(async () => {
    result.current!.clear();
  });
  expect(files.has(selected.uri)).toBe(false);
});

it('preserves a newer selection and active bytes when an older upload completes', async () => {
  pick.mockResolvedValue(pickedFile(1));
  const { result } = await renderHook(() => useDocumentUpload('account-a'));
  await act(async () => {
    await result.current!.pick();
  });
  const first = result.current!.file!;
  const response = deferred<void>();
  let uploading!: Promise<boolean>;
  await act(async () => {
    uploading = result.current!.submit(() => response.promise);
  });
  pick.mockResolvedValue(pickedFile(2));
  await act(async () => {
    await result.current!.pick();
  });
  const second = result.current!.file!;
  expect(second.uri).not.toBe(first.uri);
  expect(files.has(first.uri)).toBe(true);
  expect(files.has(second.uri)).toBe(true);
  await act(async () => {
    response.resolve();
    expect(await uploading).toBe(false);
  });
  expect(result.current!.file).toEqual(second);
  expect(files.has(first.uri)).toBe(false);
  await act(async () => {
    expect(await result.current!.submit(async () => {})).toBe(true);
  });
  expect(files.has(second.uri)).toBe(false);
});

it.each(['clear', 'unmount', 'account', 'session'])(
  'retires a late picker result after %s without replacing a later draft',
  async (action) => {
    const response = deferred<DocumentPicker.DocumentPickerResult>();
    pick.mockReturnValue(response.promise);
    const view = await renderHook(({ owner }: { owner: string }) => useDocumentUpload(owner), {
      initialProps: { owner: 'account-a' },
    });
    let choosing!: Promise<boolean>;
    await act(async () => {
      choosing = view.result.current!.pick();
    });
    expect(pick).toHaveBeenCalledTimes(1);
    if (action === 'clear')
      await act(async () => {
        view.result.current!.clear();
      });
    if (action === 'unmount') await view.unmount();
    if (action === 'account') await view.rerender({ owner: 'account-b' });
    if (action === 'session')
      await act(async () => {
        invalidateSessionScope();
      });
    const returned = pickedFile(1);
    await act(async () => {
      response.resolve(returned);
      expect(await choosing).toBe(false);
    });
    expect(files.has(returned.assets[0].uri)).toBe(false);
    expect([...files.keys()].some((uri) => uri.includes('ledova-upload-copies-v1'))).toBe(false);
    if (action !== 'unmount') {
      pick.mockResolvedValue(pickedFile(2));
      await act(async () => {
        expect(await view.result.current!.pick()).toBe(true);
      });
      expect(files.get(view.result.current!.file!.uri)?.content).toBe('document-2');
    }
  },
);

it.each(['clear', 'unmount', 'session'])(
  'keeps an admitted upload alive after %s until its refusal settles',
  async (action) => {
    pick.mockResolvedValue(pickedFile());
    const view = await renderHook(() => useDocumentUpload('account-a'));
    await act(async () => {
      await view.result.current!.pick();
    });
    const uri = view.result.current!.file!.uri;
    const response = deferred<void>();
    let uploading!: Promise<boolean>;
    await act(async () => {
      uploading = view.result.current!.submit(() => response.promise);
    });
    if (action === 'clear')
      await act(async () => {
        view.result.current!.clear();
      });
    if (action === 'unmount') await view.unmount();
    if (action === 'session')
      await act(async () => {
        invalidateSessionScope();
      });
    expect(files.has(uri)).toBe(true);
    await act(async () => {
      response.reject(new Error('refused'));
      expect(await uploading).toBe(false);
    });
    expect(files.has(uri)).toBe(false);
  },
);

it('refuses a second picker and allows the other screen to choose after the first one settles', async () => {
  const response = deferred<DocumentPicker.DocumentPickerResult>();
  pick.mockReturnValue(response.promise);
  const first = await renderHook(() => useDocumentUpload('account-a'));
  const second = await renderHook(() => useDocumentUpload('company-a'));
  let choosing!: Promise<boolean>;
  await act(async () => {
    choosing = first.result.current!.pick();
  });
  await act(async () => {
    expect(await first.result.current!.pick()).toBe(false);
    await expect(second.result.current!.pick()).rejects.toThrow('already open');
  });
  expect(pick).toHaveBeenCalledTimes(1);
  await act(async () => {
    response.resolve({ canceled: true, assets: null });
    await choosing;
  });
  pick.mockResolvedValue(pickedFile());
  await act(async () => {
    expect(await second.result.current!.pick()).toBe(true);
  });
  expect(pick).toHaveBeenCalledTimes(2);
});

it('checks scope again after reading credentials and works under StrictMode', async () => {
  const token = deferred<string | null>();
  jest.mocked(getAccessToken).mockReturnValue(token.promise);
  const view = await renderHook(() => useDocumentUpload('account-a'), {
    wrapper: ({ children }) => <React.StrictMode>{children}</React.StrictMode>,
  });
  let choosing!: Promise<boolean>;
  await act(async () => {
    choosing = view.result.current!.pick();
  });
  await act(async () => {
    view.result.current!.clear();
    token.resolve('synthetic-access');
    await choosing;
  });
  expect(pick).not.toHaveBeenCalled();
  jest.mocked(getAccessToken).mockResolvedValue('synthetic-access');
  pick.mockResolvedValue(pickedFile());
  await act(async () => {
    expect(await view.result.current!.pick()).toBe(true);
  });
  expect(files.has(view.result.current!.file!.uri)).toBe(true);
});
