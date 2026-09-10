import type { OrderStatus, OrderType } from '../../constants';
import type { SigningChallengeTypedData, TransferOrder } from './trading';

export type OrderActionPurpose = 'cancel' | 'modify';
export type OrderActionDomain = SigningChallengeTypedData['domain'];

export interface OrderActionValues {
  quantity: string;
  minQuantity: string;
  pricePerShare: string;
}

export interface OrderActionCurrentValues extends OrderActionValues {
  orderType: OrderType;
  status: OrderStatus;
  modificationCount: number;
  filledQuantity: string;
  remainingQuantity: string;
  canCancel: boolean;
  canModify: boolean;
}

export interface OrderActionToken {
  name: string;
  symbol: string;
  contractAddress: string;
}

export interface OrderActionContext {
  protocolVersion: 1;
  ownerAccountUuid: string;
  orderUuid: string;
  walletUuid: string;
  tokenUuid: string;
  walletAddress: string;
  domain: OrderActionDomain;
  token: OrderActionToken;
  currentValues: OrderActionCurrentValues;
}

export interface OrderActionChallenge extends SigningChallengeTypedData {
  purpose: 'order_cancel' | 'order_modify';
  digest: string;
  expiresAt: string;
}

export interface OrderActionChange {
  field: 'quantity' | 'min_quantity' | 'price_per_share';
  old: string;
  new: string;
}

export type OrderActionResult =
  | { kind: 'cancel'; fromStatus: OrderStatus; toStatus: 'cancelled' }
  | { kind: 'modify'; modificationCount: number; changes: OrderActionChange[] };

export interface OrderActionSnapshot {
  protocolVersion: 1;
  actionId: string;
  ownerAccountUuid: string;
  orderUuid: string;
  walletUuid: string;
  tokenUuid: string;
  walletAddress: string;
  purpose: OrderActionPurpose;
  status: 'pending' | 'applied' | 'refused';
  intent: { domain: OrderActionDomain; modifications: OrderActionValues | null };
  review: { token: OrderActionToken; currentValues: OrderActionCurrentValues };
  order: TransferOrder;
  result: OrderActionResult | null;
  refusal: { code: string; detail: string; httpStatus: 400 | 409 } | null;
  challenge: OrderActionChallenge | null;
}

export interface OrderActionRequest {
  actionId: string;
  ownerAccountUuid: string;
}

export interface OrderActionModificationRequest extends OrderActionRequest {
  newQuantity: string;
  newMinQuantity: string;
  newPricePerShare: string;
}

export interface OrderActionExecuteRequest extends OrderActionRequest {
  digest?: string;
  signature?: string;
}
