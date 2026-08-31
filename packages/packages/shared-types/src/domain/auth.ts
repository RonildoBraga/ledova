export interface AuthState {
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
  readonly user: {
    readonly hasProfile: boolean;
    readonly profileCompleted: boolean;
  } | null;
}

export interface SigninRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  passwordConfirm: string;
}

export interface EmailVerificationRequest {
  token: string;
  email?: string;
}

export interface TokenRefreshResponse {
  status?: number;
  data?: {
    access?: string;
    refresh?: string;
  };
}

export interface TokenRefreshRequest {
  refresh: string;
}

/**
 * Token refresh result containing the new access and refresh tokens.
 * Note: This is the actual response data, distinct from TokenRefreshResponse
 * which wraps it with HTTP response metadata.
 */
export interface TokenRefreshResult {
  access: string;
  refresh: string;
}

export interface AuthVerificationResponse {
  valid: boolean;
  expiresAt?: string;
  reason?: 'no_token' | 'invalid_token';
}

export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
  newPasswordConfirm: string;
}

export interface ChangePasswordResponse {
  message: string;
}
