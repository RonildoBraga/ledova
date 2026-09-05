import type { AxiosInstance } from 'axios';
import {
  changePassword,
  resendVerificationCode,
  signin,
  signout,
  signup,
  verifyAuth,
  verifyEmail,
} from '../../src/services/auth';

describe('auth services', () => {
  const post = jest.fn();
  const get = jest.fn();
  const apiClient = { get, post } as unknown as AxiosInstance;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('posts signin credentials to the signin endpoint', () => {
    const data = { email: 'founder@example.test', password: 'test-password' };

    signin(apiClient, data);

    expect(post).toHaveBeenCalledWith('/api/signin/', data);
  });

  it('posts signup credentials to the signup endpoint', () => {
    const data = {
      email: 'founder@example.test',
      password: 'test-password',
      passwordConfirm: 'test-password',
    };

    signup(apiClient, data);

    expect(post).toHaveBeenCalledWith('/api/signup/', data);
  });

  it('posts an email verification request to the verification endpoint', () => {
    const data = { email: 'founder@example.test', token: '123456' };

    verifyEmail(apiClient, data);

    expect(post).toHaveBeenCalledWith('/api/email-verification/', data);
  });

  it('posts the signup address to resend-verification because signup issues no session', () => {
    resendVerificationCode(apiClient, { email: 'founder@example.test' });

    expect(post).toHaveBeenCalledWith('/api/resend-verification/', { email: 'founder@example.test' });
  });

  it('gets the current authentication state from the verification endpoint', () => {
    verifyAuth(apiClient);

    expect(get).toHaveBeenCalledWith('/api/auth/verify/');
  });

  it('posts signout to the signout endpoint without a request body', () => {
    signout(apiClient);

    expect(post).toHaveBeenCalledWith('/api/signout/');
  });

  it('posts password changes to the change-password endpoint', () => {
    const data = {
      currentPassword: 'current-test-password',
      newPassword: 'new-test-password',
      newPasswordConfirm: 'new-test-password',
    };

    changePassword(apiClient, data);

    expect(post).toHaveBeenCalledWith('/api/change-password/', data);
  });
});
