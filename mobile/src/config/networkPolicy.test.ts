import { allowWebNavigation, getTradingEventsUrl, isPrivateIPv4, validateNetworkUrl } from './networkPolicy';

it.each(['http://api.example.test', 'http://localhost', 'http://127.0.0.1', 'http://10.0.2.2', 'http://192.168.1.2'])(
  'refuses every release HTTP URL including %s',
  (value) => {
    expect(() => validateNetworkUrl(value, false, '192.168.1.2')).toThrow();
  },
);

it.each([
  'http://localhost:8000',
  'http://127.0.0.1:8000',
  'http://[::1]:8000',
  'http://10.0.2.2:8000',
  'http://192.168.1.2:8000',
])('permits the configured local development origin %s', (value) => {
  expect(validateNetworkUrl(value, true, '192.168.1.2').protocol).toBe('http:');
});

it.each([
  'http://192.168.1.3',
  'http://localhost.example.test',
  'http://public.example.test',
  'http://169.254.169.254',
])('refuses other development origins %s', (value) => {
  expect(() => validateNetworkUrl(value, true, '192.168.1.2')).toThrow();
});

it.each([
  'https://name:secret@api.example.test',
  'https://api.example.test/#fragment',
  '//api.example.test',
  'https:\\api.example.test',
  'https://api.example.test\n',
  'file:///private',
  'javascript:alert(1)',
  '',
])('refuses malformed or unsafe URLs %s', (value) => {
  expect(() => validateNetworkUrl(value)).toThrow();
});

it('keeps HTTPS and encoded SSE query controls working', () => {
  expect(validateNetworkUrl('https://api.example.test:443/base', false).origin).toBe('https://api.example.test');
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test/base/';
  const url = new URL(getTradingEventsUrl('/events/', 'synthetic&other=value'));
  expect(url.pathname).toBe('/base/events/');
  expect([...url.searchParams.entries()]).toEqual([['token', 'synthetic&other=value']]);
  process.env.EXPO_PUBLIC_API_URL = 'http://api.example.test';
  expect(() => getTradingEventsUrl('/events/', 'synthetic')).toThrow();
});

it('validates a single literal private host without accepting suffixes or ambiguous octets', () => {
  expect(isPrivateIPv4('172.16.0.1')).toBe(true);
  expect(isPrivateIPv4('10.255.255.254')).toBe(true);
  for (const host of [
    '192.168.1.2,10.1.1.1',
    '192.168.001.2',
    '192.168.1.256',
    '172.32.0.1',
    'localhost',
    '0x7f000001',
  ]) {
    expect(isPrivateIPv4(host)).toBe(false);
  }
});

it('allows embedded blank pages and secure provider navigation while refusing mixed content', () => {
  expect(allowWebNavigation('about:blank')).toBe(true);
  expect(allowWebNavigation('https://provider.example.test/form')).toBe(true);
  expect(allowWebNavigation('http://provider.example.test/form')).toBe(false);
  expect(allowWebNavigation('file:///private')).toBe(false);
});
