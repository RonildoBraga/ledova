const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '10.0.2.2']);

export function isPrivateIPv4(value: string): boolean {
  const octets = value.split('.');
  if (octets.length !== 4 || octets.some((part) => !/^(0|[1-9]\d{0,2})$/.test(part) || Number(part) > 255)) {
    return false;
  }
  const [first, second] = octets.map(Number);
  return first === 10 || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168);
}

export function validateNetworkUrl(
  value: string,
  development = __DEV__,
  privateHost = process.env.EXPO_PUBLIC_DEV_API_HOST || '',
): URL {
  if (!/^https?:\/\//i.test(value) || /[\s\\]/.test(value)) throw new Error('A valid HTTPS URL is required.');
  const url = new URL(value);
  if (url.username || url.password || url.hash) throw new Error('URL credentials and fragments are not allowed.');
  if (url.protocol === 'https:') return url;
  const local = LOOPBACK_HOSTS.has(url.hostname) || (isPrivateIPv4(privateHost) && url.hostname === privateHost);
  if (development && local) return url;
  throw new Error('HTTP is allowed only for explicitly configured local development.');
}

export function getApiBaseUrl(): string {
  const url = validateNetworkUrl(process.env.EXPO_PUBLIC_API_URL || '');
  if (url.search) throw new Error('The API base URL cannot contain a query.');
  return url.href.replace(/\/$/, '');
}

export function validateApiDestination(value: string): string {
  const destination = validateNetworkUrl(value);
  if (destination.origin !== new URL(getApiBaseUrl()).origin) {
    throw new Error('Credentials can only be sent to the configured API origin.');
  }
  return destination.href;
}

export function getTradingEventsUrl(path: string, tokenUuid: string): string {
  const url = new URL(`${getApiBaseUrl()}${path}`);
  url.searchParams.set('token', tokenUuid);
  return validateApiDestination(url.href);
}

export function allowWebNavigation(value: string): boolean {
  if (value === 'about:blank') return true;
  try {
    validateNetworkUrl(value);
    return true;
  } catch {
    return false;
  }
}
