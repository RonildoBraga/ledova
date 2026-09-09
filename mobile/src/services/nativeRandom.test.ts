import * as ExpoCrypto from 'expo-crypto';

jest.mock('expo-crypto', () => ({ getRandomValues: jest.fn() }));
jest.mock('react-native', () => ({ NativeModules: {} }));

function withEntry(check: () => void) {
  const names = ['crypto', 'process', 'Buffer', 'expo', 'nativeCallSyncHook', 'RN$Bridgeless'];
  const descriptors = names.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)] as const);
  for (const name of ['crypto', 'expo', 'nativeCallSyncHook', 'RN$Bridgeless']) {
    Object.defineProperty(globalThis, name, { value: undefined, configurable: true, writable: true });
  }
  try {
    jest.isolateModules(() => {
      jest.requireActual('../../crypto-polyfill');
      check();
    });
  } finally {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  }
}

it('fails closed in the entry shim when the native generator is unavailable', () => {
  jest.mocked(ExpoCrypto.getRandomValues).mockImplementation(() => {
    throw new Error('native generator unavailable');
  });
  const random = jest.spyOn(Math, 'random');
  withEntry(() => {
    expect(() => globalThis.crypto.getRandomValues(new Uint8Array(16))).toThrow('native generator unavailable');
    expect(random).not.toHaveBeenCalled();
  });
});

it('uses native bytes through the entry shim without a random fallback', () => {
  jest.mocked(ExpoCrypto.getRandomValues).mockImplementation((bytes) => {
    bytes.fill(23);
    return bytes;
  });
  const random = jest.spyOn(Math, 'random');
  withEntry(() => {
    const bytes = new Uint8Array(16);
    expect(globalThis.crypto.getRandomValues(bytes)).toBe(bytes);
    expect([...bytes]).toEqual(Array(16).fill(23));
    expect(random).not.toHaveBeenCalled();
  });
});
