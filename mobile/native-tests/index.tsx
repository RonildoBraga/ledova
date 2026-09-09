import '../crypto-polyfill';
import { registerRootComponent } from 'expo';
import { useEffect, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { getRandomValues } from 'expo-crypto';
import { File, Paths } from 'expo-file-system';
import EventSource from 'react-native-sse';
import { apiClient, rotateRefreshToken } from '../src/services/apiClient';
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from '../src/services/tokenStorage';
import { generateMnemonic, getSeedPhrase, storeSeedPhrase, validateMnemonic } from '../src/services/secureKeyStorage';
import { getApiBaseUrl, getTradingEventsUrl } from '../src/config/networkPolicy';
import { verifyMessage } from 'ethers';
import { deriveAccountsFromMnemonic } from '../src/utils/softwareWallet/seedDerivation';
import { signEthereumMessage } from '../src/utils/softwareWallet/localSigner';

type Check = { name: string; passed: boolean };
const pair = { accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' };
const target = process.env.EXPO_PUBLIC_NATIVE_PROBE_TARGET || '';
const cleartext = process.env.EXPO_PUBLIC_NATIVE_PROBE_HTTP || '';
const untrusted = process.env.EXPO_PUBLIC_NATIVE_PROBE_UNTRUSTED || '';

function requireTrue(value: unknown): asserts value {
  if (!value) throw new Error('Native probe assertion failed.');
}

function request(url: string, method = 'GET', body?: string): Promise<XMLHttpRequest> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = 10000;
    xhr.setRequestHeader('Authorization', 'Bearer synthetic-access');
    xhr.onload = () => resolve(xhr);
    xhr.onerror = () => reject(new Error('Native request refused.'));
    xhr.ontimeout = () => reject(new Error('Native request timed out.'));
    xhr.send(body);
  });
}

async function run(): Promise<Check[]> {
  const checks: Check[] = [];
  async function check(name: string, action: () => Promise<void> | void) {
    try {
      await action();
      checks.push({ name, passed: true });
    } catch {
      checks.push({ name, passed: false });
    }
  }

  await check('compiled API destination matches isolated server', () => {
    requireTrue(apiClient.defaults.baseURL === process.env.EXPO_PUBLIC_API_URL);
    requireTrue(getApiBaseUrl() === process.env.EXPO_PUBLIC_API_URL);
  });
  await check('native entropy and mnemonic', () => {
    const first = getRandomValues(new Uint8Array(32));
    const second = getRandomValues(new Uint8Array(32));
    requireTrue(first.some((byte) => byte !== 0) && first.some((byte, index) => byte !== second[index]));
    requireTrue(validateMnemonic(generateMnemonic()));
  });
  await check('native wallet derivation and signing vector', async () => {
    const phrase = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
    const address = '0x9858EfFD232B4033E47d90003D41EC34EcaEda94';
    requireTrue(
      deriveAccountsFromMnemonic(phrase)
        .addresses.find((account) => account.networkType === 'ETH')
        ?.address.toLowerCase() === address.toLowerCase(),
    );
    const message = 'Ledova synthetic native validation';
    const signature = await signEthereumMessage(phrase, "m/44'/60'/0'/0/0", message);
    requireTrue(verifyMessage(message, signature) === address);
    requireTrue(verifyMessage('different synthetic message', signature) !== address);
  });
  await check('legacy session migration and ordinary storage', async () => {
    await clearTokens();
    await SecureStore.deleteItemAsync('session.retired.v1');
    await SecureStore.setItemAsync('accessToken', pair.accessToken);
    await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
    requireTrue((await getAccessToken()) === pair.accessToken);
    requireTrue((await getRefreshToken()) === pair.refreshToken);
    requireTrue((await SecureStore.getItemAsync('accessToken')) === null);
    requireTrue((await SecureStore.getItemAsync('refreshToken')) === null);
    await storeTokens(pair);
  });
  if (Platform.OS === 'android') {
    await check('unenrolled native wallet storage refuses without losing legacy recovery', async () => {
      requireTrue(!SecureStore.canUseBiometricAuthentication());
      const phrase = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
      await SecureStore.setItemAsync('wallet.seed.synthetic-probe', phrase);
      requireTrue((await getSeedPhrase('synthetic-probe')) === null);
      requireTrue((await SecureStore.getItemAsync('wallet.seed.synthetic-probe')) === phrase);
      let refused = false;
      try {
        await storeSeedPhrase('new-synthetic-probe', phrase);
      } catch {
        refused = true;
      }
      requireTrue(refused);
      await SecureStore.deleteItemAsync('wallet.seed.synthetic-probe');
    });
  }
  await check('direct authenticated API and refresh', async () => {
    const { data } = await apiClient.post<{ authenticated: boolean; bodyReceived: boolean }>('/direct', {
      secret: 'synthetic-sign-in',
    });
    requireTrue(data.authenticated && data.bodyReceived);
    await rotateRefreshToken(pair.refreshToken);
    requireTrue((await getRefreshToken()) === pair.refreshToken);
  });
  await check('redirect target reachability', async () => {
    const response = await request(`${target}/target-control`, 'POST', 'synthetic-control');
    const data = JSON.parse(response.responseText);
    requireTrue(response.status === 200 && data.bodyReceived && data.authenticated);
  });
  for (const status of [307, 308]) {
    await check(`native ${status} refusal`, async () => {
      const response = await request(
        `${process.env.EXPO_PUBLIC_API_URL}/redirect${status}`,
        'POST',
        'synthetic-refresh-and-sign-in',
      );
      requireTrue(response.status === status);
    });
  }
  await check('native cleartext refusal', async () => {
    let refused = false;
    try {
      await request(`${cleartext}/direct`, 'POST', 'synthetic-body');
    } catch (error) {
      refused = error instanceof Error && error.message === 'Native request refused.';
    }
    requireTrue(refused);
  });
  await check('repeated native refusal and cancellation completes', async () => {
    for (let index = 0; index < 8; index++) {
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const timeout = setTimeout(() => reject(new Error('Refusal cancellation timed out.')), 10000);
        const complete = () => {
          clearTimeout(timeout);
          resolve();
        };
        xhr.open('POST', `${cleartext}/direct`);
        xhr.setRequestHeader('Authorization', 'Bearer synthetic-access');
        xhr.onerror = complete;
        xhr.onabort = complete;
        xhr.onload = () => {
          clearTimeout(timeout);
          reject(new Error('Cleartext request escaped.'));
        };
        xhr.send('synthetic-body');
        setTimeout(() => xhr.abort(), 0);
      });
    }
  });
  await check('native TLS trust refusal', async () => {
    let refused = false;
    try {
      await request(`${untrusted}/direct`);
    } catch (error) {
      refused = error instanceof Error && error.message === 'Native request refused.';
    }
    requireTrue(refused);
  });
  await check('multipart upload and binary download', async () => {
    const file = new File(Paths.cache, 'ledova-native-probe.txt');
    try {
      file.create({ overwrite: true });
      file.write('synthetic-fixture');
      const form = new FormData();
      form.append('file', { uri: file.uri, name: 'synthetic.txt', type: 'text/plain' } as unknown as Blob);
      const uploaded = await apiClient.post<{ valid: boolean }>('/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      requireTrue(uploaded.data.valid);
      const downloaded = await apiClient.get<ArrayBuffer>('/download', { responseType: 'arraybuffer' });
      requireTrue(String.fromCharCode(...new Uint8Array(downloaded.data)) === 'synthetic-fixture');
    } finally {
      if (file.exists) file.delete();
    }
  });
  await check('incremental SSE and close', async () => {
    await new Promise<void>((resolve, reject) => {
      let messages = 0;
      const stream = new EventSource<'connected'>(getTradingEventsUrl('/stream', 'synthetic'), {
        headers: { Authorization: 'Bearer synthetic-access' },
        pollingInterval: 0,
      });
      const timeout = setTimeout(() => {
        stream.close();
        reject(new Error('Stream timed out.'));
      }, 10000);
      stream.addEventListener('connected', () => {
        messages++;
        if (messages === 2) {
          clearTimeout(timeout);
          stream.close();
          resolve();
        }
      });
      stream.addEventListener('error', () => {
        clearTimeout(timeout);
        stream.close();
        reject(new Error('Stream failed.'));
      });
    });
  });
  await check('progress and native cancellation', async () => {
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', `${process.env.EXPO_PUBLIC_API_URL}/slow`);
      xhr.timeout = 10000;
      xhr.onprogress = (event) => {
        if (event.loaded > 0) xhr.abort();
      };
      xhr.onabort = () => resolve();
      xhr.onerror = () => reject(new Error('Progress failed.'));
      xhr.ontimeout = () => reject(new Error('Progress timed out.'));
      xhr.send();
    });
  });
  await check('sign-out removes the native session', async () => {
    await clearTokens();
    requireTrue((await getAccessToken()) === null && (await getRefreshToken()) === null);
  });
  await apiClient.post('/report', { checks });
  return checks;
}

function NativeProbe() {
  const [status, setStatus] = useState('Native probe running');
  useEffect(() => {
    run()
      .then((checks) => setStatus(checks.every((check) => check.passed) ? 'NATIVE_PROBE_PASS' : 'NATIVE_PROBE_FAIL'))
      .catch(() => setStatus('NATIVE_PROBE_REPORT_FAILED'));
  }, []);
  return (
    <View>
      <Text testID="native-probe-status">{status}</Text>
    </View>
  );
}

registerRootComponent(NativeProbe);
