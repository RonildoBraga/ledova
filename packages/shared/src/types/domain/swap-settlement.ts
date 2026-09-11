import type { SwapUserRole } from '../../constants';
import type { ApprovalTransaction, EIP712Types, SwapOrder } from './trading';

export interface SwapSettlementLookup {
  orderUuid: string;
  swapUuid: string;
  ownerAccountUuid: string;
  walletUuid: string;
  settlementDigest?: string;
}

export interface SwapSettlementIdentity extends SwapSettlementLookup {
  settlementDigest: string;
}

export interface SwapSettlementSelection extends SwapSettlementLookup {
  walletAddress?: string;
}

export interface SwapSettlementParty {
  orderUuid: string;
  ownerAccountUuid: string;
  walletUuid: string;
  paymentAssetUuid: string | null;
  address: string;
}

export interface SwapSettlementTypedData {
  types: EIP712Types;
  primaryType: 'SwapOrder';
  domain: {
    name: 'LedovaAtomicSwap';
    version: '1';
    chainId: string;
    verifyingContract: string;
  };
  message: {
    seller: string;
    buyer: string;
    shareToken: string;
    paymentToken: string;
    shareAmount: string;
    paymentAmount: string;
    nonce: string;
    deadline: string;
  };
}

export interface SwapSettlementContext {
  protocolVersion: 1;
  swapUuid: string;
  seller: SwapSettlementParty;
  buyer: SwapSettlementParty;
  shareToken: { uuid: string; address: string; chain: string; name: string; symbol: string; decimals: number };
  paymentAsset: {
    uuid: string;
    name: string;
    symbol: string;
    pricingDecimals: number;
    deploymentUuid: string;
    deploymentChain: string;
    deploymentAddress: string;
    deploymentDecimals: number;
  };
  pricePerShare: string;
  typedData: SwapSettlementTypedData;
  digest: string;
  orderHash: string;
}

export interface SettlementSwapOrder extends Omit<SwapOrder, 'completedAt'> {
  settlementProtocolVersion: 1;
  settlementContext: SwapSettlementContext;
  settlementDigest: string;
  completedAt: string | null;
}

export interface SwapSettlementResponse extends SwapSettlementIdentity {
  swapOrder: SettlementSwapOrder;
  typedData: SwapSettlementTypedData;
  userRole: SwapUserRole;
  hasSigned: boolean;
  canSign: boolean;
  admissionRefusal: string | null;
}

export interface SwapSettlementApprovalIdentity extends SwapSettlementIdentity {
  userRole: SwapUserRole;
}

export interface SwapSettlementApprovalStatus extends SwapSettlementApprovalIdentity {
  tokenAddress: string;
  tokenSymbol: string;
  requiredAmount: string;
  currentAllowance: string;
  needsApproval: boolean;
  spender: string;
}

export type SwapSettlementApprovalData = SwapSettlementApprovalIdentity &
  (
    | { needsApproval: false; message: string; requiredAmount: string; currentAllowance: string }
    | {
        needsApproval: true;
        transaction: ApprovalTransaction;
        description: string;
        tokenAddress: string;
        tokenSymbol: string;
        spender: string;
        amount: string;
        unlimited: true;
      }
  );

export interface SwapSettlementApprovalConfirmed extends SwapSettlementApprovalIdentity {
  txHash: string;
  blockNumber: number | null;
  gasUsed: number | null;
}

export interface SwapSettlementApprovalUnconfirmed extends SwapSettlementApprovalIdentity {
  txHash: string;
  code: 'swap_approval_unconfirmed';
  detail: string;
}

export interface SwapSettlementSignature {
  signature: string;
  signerAddress: string;
}

export interface SwapSettlementSignedApproval {
  txHash: string;
  transaction: ApprovalTransaction;
}

export interface SwapSettlementCrypto {
  digestTypedData: (typedData: SwapSettlementTypedData) => string | Promise<string>;
  recoverSigner: (typedData: SwapSettlementTypedData, signature: string) => string | Promise<string>;
  inspectSignedApproval: (raw: string) => SwapSettlementSignedApproval | Promise<SwapSettlementSignedApproval>;
}
