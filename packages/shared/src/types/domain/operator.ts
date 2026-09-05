import type { AssetChainDeployment } from './asset';

export type OperatorDeploymentMode = 'single_issuer' | 'registry';

export interface OperatorSettlementAsset {
  uuid: string;
  symbol: string;
  name: string;
  chainDeployments: AssetChainDeployment[];
}

export interface OperatorPaymentInstructions {
  bankAccountName?: string;
  bankBsb?: string;
  bankAccountNumber?: string;
  paymentReferencePrefix?: string;
  receivingWalletAddress?: string;
  receivingWalletChain?: string;
}

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
