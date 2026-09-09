import { verifyMessage } from 'ethers';
import { getRandomValues } from 'expo-crypto';
import { generateMnemonic, validateMnemonic } from '../../services/secureKeyStorage';
import { deriveAccountsFromMnemonic } from './seedDerivation';
import { signEthereumMessage } from './localSigner';

jest.mock('expo-crypto', () => ({ getRandomValues: jest.fn() }));

const phrase = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
const address = '0x9858EfFD232B4033E47d90003D41EC34EcaEda94';

it('converts the zero-entropy BIP39 vector', () => {
  const entropy = new Uint8Array(16);
  jest.mocked(getRandomValues).mockReturnValue(entropy);
  expect(generateMnemonic()).toBe(phrase);
  expect(validateMnemonic(phrase)).toBe(true);
  expect(validateMnemonic(phrase.replace('about', 'abandon'))).toBe(false);
  expect(getRandomValues).toHaveBeenCalledWith(expect.any(Uint8Array));
  expect([...entropy]).toEqual(Array(16).fill(0));
});

it('wipes temporary native entropy after creating a valid phrase', () => {
  const entropy = new Uint8Array(16).fill(23);
  jest.mocked(getRandomValues).mockReturnValue(entropy);
  expect(entropy.some((byte) => byte !== 0)).toBe(true);
  expect(validateMnemonic(generateMnemonic())).toBe(true);
  expect([...entropy]).toEqual(Array(16).fill(0));
});

it('refuses wallet generation without the native source of entropy', () => {
  jest.mocked(getRandomValues).mockImplementation(() => {
    throw new Error('native entropy unavailable');
  });
  const random = jest.spyOn(Math, 'random');
  expect(() => generateMnemonic()).toThrow('native entropy unavailable');
  expect(random).not.toHaveBeenCalled();
});

it('derives the public BIP44 Ethereum vector and verifies a local signature against it', async () => {
  const accounts = deriveAccountsFromMnemonic(phrase);
  expect(accounts.addresses.find((account) => account.networkType === 'ETH')?.address.toLowerCase()).toBe(
    address.toLowerCase(),
  );
  const message = 'Ledova synthetic native validation';
  const signature = await signEthereumMessage(phrase, "m/44'/60'/0'/0/0", message);
  expect(verifyMessage(message, signature)).toBe(address);
  expect(verifyMessage('different synthetic message', signature)).not.toBe(address);
});
