import '../crypto-polyfill';
import { registerRootComponent } from 'expo';
import { useCallback, useEffect, useState } from 'react';
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
import { failureCategory, NativeProbeAssertion } from './diagnostics';
import { DocumentCopy, pickDocumentCopy } from '../src/services/documentCopies';
import { getSessionEpoch } from '../src/services/sessionScope';
import { ScannerBridgeProbe } from './ScannerBridgeProbe';

type Check = { name: string; passed: boolean; failure?: { category: string; stage: string } };
const pair = { accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' };
const target = process.env.EXPO_PUBLIC_NATIVE_PROBE_TARGET || '';
const cleartext = process.env.EXPO_PUBLIC_NATIVE_PROBE_HTTP || '';
const untrusted = process.env.EXPO_PUBLIC_NATIVE_PROBE_UNTRUSTED || '';

function requireTrue(value: unknown): asserts value {
  if (!value) throw new NativeProbeAssertion();
}

function request(url: string, method = 'GET', body?: string): Promise<XMLHttpRequest> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = 10000;
    xhr.setRequestHeader('Authorization', 'Bearer synthetic-access');
    if (body !== undefined) xhr.setRequestHeader('Content-Type', 'text/plain');
    xhr.onload = () => resolve(xhr);
    xhr.onerror = () => reject(new Error('Native request refused.'));
    xhr.ontimeout = () => reject(new Error('Native request timed out.'));
    xhr.send(body);
  });
}

async function run(scannerCheck: Check | null): Promise<Check[]> {
  const checks: Check[] = scannerCheck ? [scannerCheck] : [];
  async function check(name: string, action: (stage: (name: string) => void) => Promise<void> | void) {
    let stage = 'check';
    try {
      await action((name) => {
        stage = name;
      });
      checks.push({ name, passed: true });
    } catch (error) {
      checks.push({ name, passed: false, failure: { category: failureCategory(error), stage } });
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
  await check('legacy session migration and ordinary storage', async (stage) => {
    stage('initial-sign-out');
    await clearTokens();
    stage('retired-marker-removal');
    await SecureStore.deleteItemAsync('session.retired.v1');
    stage('legacy-access-write');
    await SecureStore.setItemAsync('accessToken', pair.accessToken);
    stage('legacy-refresh-write');
    await SecureStore.setItemAsync('refreshToken', pair.refreshToken);
    stage('migrated-access-read');
    requireTrue((await getAccessToken()) === pair.accessToken);
    stage('migrated-refresh-read');
    requireTrue((await getRefreshToken()) === pair.refreshToken);
    stage('legacy-access-removal');
    requireTrue((await SecureStore.getItemAsync('accessToken')) === null);
    stage('legacy-refresh-removal');
    requireTrue((await SecureStore.getItemAsync('refreshToken')) === null);
    stage('ordinary-session-write');
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
  await check('direct authenticated API and refresh', async (stage) => {
    stage('authenticated-request');
    const { data } = await apiClient.post<{ authenticated: boolean; bodyReceived: boolean }>('/direct', {
      secret: 'synthetic-sign-in',
    });
    stage('authenticated-response');
    requireTrue(data.authenticated && data.bodyReceived);
    stage('session-rotation');
    await rotateRefreshToken(pair.refreshToken);
    stage('rotated-refresh-read');
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
        xhr.setRequestHeader('Content-Type', 'text/plain');
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
    const picked = new File(Paths.cache, 'DocumentPicker', '11111111-1111-1111-1111-111111111111.txt');
    let copy: DocumentCopy | null = null;
    let release: (() => void) | undefined;
    try {
      file.create({ overwrite: true });
      file.write('synthetic-fixture');
      picked.create({ intermediates: true, overwrite: true });
      picked.write('synthetic-fixture');
      copy = await pickDocumentCopy(
        () => true,
        async () => ({
          canceled: false,
          assets: [{ uri: picked.uri, name: 'synthetic.txt', mimeType: 'text/plain', size: 17, lastModified: 0 }],
        }),
      );
      requireTrue(copy && !picked.info().exists);
      release = copy.acquire();
      copy.retire();
      requireTrue(new File(copy.file.uri).info().exists);
      const form = new FormData();
      form.append('file', copy.file as unknown as Blob);
      const uploaded = await apiClient.post<{ valid: boolean }>('/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ledovaSessionEpoch: getSessionEpoch(),
      });
      requireTrue(uploaded.data.valid);
      release();
      requireTrue(!new File(copy.file.uri).info().exists);
      requireTrue((await file.text()) === 'synthetic-fixture');
      const downloaded = await apiClient.get<ArrayBuffer>('/download', { responseType: 'arraybuffer' });
      requireTrue(String.fromCharCode(...new Uint8Array(downloaded.data)) === 'synthetic-fixture');
    } finally {
      copy?.retire();
      release?.();
      if (picked.info().exists) picked.delete();
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
      xhr.responseType = 'arraybuffer';
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
  await check('sign-out removes the native session', async (stage) => {
    stage('sign-out');
    await clearTokens();
    stage('signed-out-session-read');
    requireTrue((await getAccessToken()) === null && (await getRefreshToken()) === null);
  });
  await apiClient.post('/report', { checks });
  return checks;
}

function NativeProbe() {
  const [status, setStatus] = useState('Native probe running');
  const [scannerCheck, setScannerCheck] = useState<Check | null>(null);
  const scannerComplete = useCallback((passed: boolean, stage = 'window-generation') => {
    setScannerCheck({
      name: 'Android scanner window bridge',
      passed,
      ...(!passed && { failure: { category: 'assertion', stage } }),
    });
  }, []);
  useEffect(() => {
    if (Platform.OS === 'android' && !scannerCheck) return;
    run(scannerCheck)
      .then((checks) => setStatus(checks.every((check) => check.passed) ? 'NATIVE_PROBE_PASS' : 'NATIVE_PROBE_FAIL'))
      .catch(() => setStatus('NATIVE_PROBE_REPORT_FAILED'));
  }, [scannerCheck]);
  return (
    <View>
      {Platform.OS === 'android' && !scannerCheck && <ScannerBridgeProbe onComplete={scannerComplete} />}
      <Text testID="native-probe-status">{status}</Text>
    </View>
  );
}

registerRootComponent(NativeProbe);
