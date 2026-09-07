import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describeFailure } from '../../src/utils/errors';

const PASSWORD = 'correct-horse-battery-staple';
const EMAIL = 'investor@example.test';

const requestConfig = (url: string, body: unknown): InternalAxiosRequestConfig =>
  ({
    url,
    method: 'post',
    data: JSON.stringify(body),
    headers: { Authorization: 'Bearer secret-access-token' },
  }) as unknown as InternalAxiosRequestConfig;

const rejectedSignin = (status: number) => {
  const config = requestConfig('/api/auth/signin/', { email: EMAIL, password: PASSWORD });
  const response: AxiosResponse = { status, statusText: 'Unauthorized', data: {}, headers: {}, config };
  return new AxiosError('Request failed with status code 401', AxiosError.ERR_BAD_REQUEST, config, {}, response);
};

describe('describeFailure', () => {
  it('describes a rejected sign-in by status, code and route', () => {
    expect(describeFailure(rejectedSignin(401))).toBe('status=401 code=ERR_BAD_REQUEST request=POST /api/auth/signin/');
  });

  it('carries neither the request body nor the credentials in it', () => {
    const description = describeFailure(rejectedSignin(401));

    expect(description).not.toContain(PASSWORD);
    expect(description).not.toContain(EMAIL);
    expect(description).not.toContain('secret-access-token');
  });

  it('drops the query string, which is where an email reaches a URL', () => {
    const config = requestConfig(`/api/users/?email=${encodeURIComponent(EMAIL)}#fragment`, {});
    const error = new AxiosError('Request failed', AxiosError.ERR_BAD_REQUEST, config, {}, undefined);

    expect(describeFailure(error)).toBe('code=ERR_BAD_REQUEST request=POST /api/users/');
  });

  it('still names a network failure that never reached a response', () => {
    const config = requestConfig('/api/auth/signin/', { email: EMAIL, password: PASSWORD });
    const error = new AxiosError('Network Error', AxiosError.ERR_NETWORK, config, {}, undefined);

    expect(describeFailure(error)).toBe('code=ERR_NETWORK request=POST /api/auth/signin/');
  });

  it('falls back to the name and message of a local error', () => {
    expect(describeFailure(new TypeError('cbor is not a function'))).toBe('TypeError: cbor is not a function');
  });

  it('passes a string through and names anything it cannot read', () => {
    expect(describeFailure('No cameras found')).toBe('No cameras found');
    expect(describeFailure(null)).toBe('unknown failure');
    expect(describeFailure(undefined)).toBe('unknown failure');
    expect(describeFailure({})).toBe('unknown failure');
  });
});
