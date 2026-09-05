import type { AssetChainDeployment } from './asset';

export type OperatorDeploymentMode = 'single_issuer' | 'registry';

export interface OperatorSettlementAsset {
  uuid: string;
  symbol: string;
  name: string;
  chainDeployments: AssetChainDeployment[];
}

/** Only the payment rails the operator has filled in are present. */
export interface OperatorPaymentInstructions {
  bankAccountName?: string;
  bankBsb?: string;
  bankAccountNumber?: string;
  paymentReferencePrefix?: string;
  receivingWalletAddress?: string;
  receivingWalletChain?: string;
}

/** GET /api/operator/: the public profile of whoever hosts this deployment. */
export interface Operator {
  name: string;
  legalName: string;
  abn: string;
  contactEmail: string;
  website: string;
  deploymentMode: OperatorDeploymentMode;
  supportedSettlementAssets: OperatorSettlementAsset[];
  issuedStablecoin: OperatorSettlementAsset | null;
  investorKycRequired: boolean;
  issuerKycRequired: boolean;
  paymentInstructions: OperatorPaymentInstructions;
}
