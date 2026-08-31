export interface RequestVerificationChallengeResponse {
  challenge: string;
  message: string;
  walletAddress: string;
}

export interface VerifyWalletRequest {
  signature: string;
}

export interface VerifyWalletResponse {
  success: boolean;
  message: string;
  verificationStatus: 'PENDING' | 'VERIFIED';
  verifiedAt?: string;
}
