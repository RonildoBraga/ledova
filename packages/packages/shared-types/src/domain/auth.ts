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

export interface TokenRefreshRequest {
  refresh: string;
}

export interface TokenRefreshResult {
  access: string;
  refresh: string;
}

export interface AuthVerificationResponse {
  valid: boolean;
  expiresAt?: string;
}

export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
  newPasswordConfirm: string;
}

export interface ChangePasswordResponse {
  message: string;
}
