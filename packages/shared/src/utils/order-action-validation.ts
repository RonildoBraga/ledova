import type {
  OrderActionContext,
  OrderActionCurrentValues,
  OrderActionDomain,
  OrderActionSnapshot,
  OrderActionValues,
} from '../types';
import type { SavedOrderAction } from './order-action-storage';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ADDRESS = /^0x[0-9a-f]{40}$/i;
const STATUSES = [
  'open',
  'partially_filled',
  'matched',
  'pending_signature',
  'executing',
  'completed',
  'cancelled',
  'expired',
  'failed',
];

function integer(value: unknown, max = 9223372036854775807n): value is string {
  return typeof value === 'string' && /^(0|[1-9]\d*)$/.test(value) && value.length <= 78 && BigInt(value) <= max;
}

function price(value: unknown): value is string {
  return typeof value === 'string' && /^(0|[1-9]\d{0,15})\.\d{2}$/.test(value) && BigInt(value.replace('.', '')) > 0n;
}

function values(value: OrderActionValues | null | undefined): boolean {
  return (
    !!value &&
    integer(value.quantity) &&
    value.quantity !== '0' &&
    integer(value.minQuantity) &&
    price(value.pricePerShare)
  );
}

function currentValues(value: OrderActionCurrentValues | null | undefined): boolean {
  return (
    !!value &&
    values(value) &&
    integer(value.filledQuantity) &&
    integer(value.remainingQuantity) &&
    ['buy', 'sell'].includes(value.orderType) &&
    STATUSES.includes(value.status) &&
    Number.isSafeInteger(value.modificationCount) &&
    value.modificationCount >= 0 &&
    typeof value.canCancel === 'boolean' &&
    typeof value.canModify === 'boolean'
  );
}

function domain(value: OrderActionDomain | null | undefined): boolean {
  return (
    !!value &&
    value.name === 'Ledova Trading' &&
    value.version === '1' &&
    Number.isSafeInteger(value.chainId) &&
    value.chainId > 0 &&
    ADDRESS.test(value.verifyingContract) &&
    !/^0x0{40}$/i.test(value.verifyingContract)
  );
}

function sameDomain(left: OrderActionDomain, right: OrderActionDomain): boolean {
  return (
    left.name === right.name &&
    left.version === right.version &&
    left.chainId === right.chainId &&
    left.verifyingContract.toLowerCase() === right.verifyingContract.toLowerCase()
  );
}

function token(value: OrderActionContext['token'] | null | undefined): boolean {
  return (
    !!value &&
    typeof value.name === 'string' &&
    typeof value.symbol === 'string' &&
    typeof value.contractAddress === 'string'
  );
}

function identity(value: OrderActionContext | OrderActionSnapshot): boolean {
  return (
    value.protocolVersion === 1 &&
    [value.orderUuid, value.ownerAccountUuid, value.walletUuid, value.tokenUuid].every(
      (id) => typeof id === 'string' && UUID.test(id),
    ) &&
    typeof value.walletAddress === 'string' &&
    ADDRESS.test(value.walletAddress)
  );
}

function sameIdentity(
  left: OrderActionContext | OrderActionSnapshot,
  right: OrderActionContext | OrderActionSnapshot,
): boolean {
  return (
    left.orderUuid === right.orderUuid &&
    left.ownerAccountUuid === right.ownerAccountUuid &&
    left.walletUuid === right.walletUuid &&
    left.tokenUuid === right.tokenUuid &&
    left.walletAddress.toLowerCase() === right.walletAddress.toLowerCase()
  );
}

function sameValues(left: OrderActionValues | null, right: OrderActionValues | null): boolean {
  return left === null
    ? right === null
    : !!right &&
        left.quantity === right.quantity &&
        left.minQuantity === right.minQuantity &&
        left.pricePerShare === right.pricePerShare;
}

function reviewKey(review: OrderActionSnapshot['review']): string {
  const current = review.currentValues;
  return JSON.stringify([
    review.token.name,
    review.token.symbol,
    review.token.contractAddress,
    current.orderType,
    current.status,
    current.modificationCount,
    current.canCancel,
    current.canModify,
    current.quantity,
    current.minQuantity,
    current.pricePerShare,
    current.filledQuantity,
    current.remainingQuantity,
  ]);
}

function outcomeKey(snapshot: OrderActionSnapshot): string {
  const result = snapshot.result;
  const refusal = snapshot.refusal;
  return JSON.stringify([
    result?.kind === 'cancel'
      ? [result.kind, result.fromStatus, result.toStatus]
      : result?.kind === 'modify'
        ? [
            result.kind,
            result.modificationCount,
            result.changes.map((change) => [change.field, change.old, change.new]),
          ]
        : result,
    refusal ? [refusal.code, refusal.detail, refusal.httpStatus] : refusal,
  ]);
}

export function canonicalOrderActionValues(value: OrderActionValues): OrderActionValues {
  const quantity = value.quantity.trim();
  const minimum = value.minQuantity.trim();
  const amount = value.pricePerShare.trim();
  if (!/^\d{1,19}$/.test(quantity) || !/^\d{1,19}$/.test(minimum) || !/^\d{1,16}(\.\d{0,2})?$/.test(amount))
    throw new Error('Enter whole share quantities and a positive price with at most two decimal places.');
  const [whole, fraction = ''] = amount.split('.');
  const canonical = {
    quantity: BigInt(quantity).toString(),
    minQuantity: BigInt(minimum).toString(),
    pricePerShare: `${BigInt(whole!).toString()}.${fraction.padEnd(2, '0')}`,
  };
  if (!values(canonical)) throw new Error('The share quantities or price are outside the supported range.');
  return canonical;
}

export function validateOrderActionContext(context: OrderActionContext, account: string, order: string): void {
  if (
    !context ||
    !identity(context) ||
    context.ownerAccountUuid !== account ||
    context.orderUuid !== order ||
    !domain(context.domain) ||
    !token(context.token) ||
    !currentValues(context.currentValues)
  )
    throw new Error('The order details did not match this account and order.');
}

export function validateOrderActionSnapshot(
  snapshot: OrderActionSnapshot,
  record: SavedOrderAction,
  known?: OrderActionSnapshot | null,
): void {
  if (
    !snapshot ||
    !identity(snapshot) ||
    snapshot.actionId !== record.actionId ||
    snapshot.ownerAccountUuid !== record.ownerAccountUuid ||
    snapshot.orderUuid !== record.orderUuid ||
    snapshot.purpose !== record.purpose ||
    !snapshot.intent ||
    !domain(snapshot.intent.domain) ||
    (record.purpose === 'cancel' ? snapshot.intent.modifications !== null : !values(snapshot.intent.modifications)) ||
    !snapshot.review ||
    !token(snapshot.review.token) ||
    !currentValues(snapshot.review.currentValues) ||
    !snapshot.order ||
    snapshot.order.uuid !== record.orderUuid ||
    snapshot.order.token !== snapshot.tokenUuid ||
    typeof snapshot.order.walletAddress !== 'string' ||
    snapshot.order.walletAddress.toLowerCase() !== snapshot.walletAddress.toLowerCase() ||
    !STATUSES.includes(snapshot.order.status) ||
    !['buy', 'sell'].includes(snapshot.order.orderType) ||
    typeof snapshot.order.tokenName !== 'string' ||
    typeof snapshot.order.tokenSymbol !== 'string' ||
    !Number.isInteger(snapshot.order.quantity) ||
    snapshot.order.quantity < 1 ||
    typeof snapshot.order.pricePerShare !== 'string' ||
    typeof snapshot.order.totalValue !== 'string' ||
    typeof snapshot.order.createdAt !== 'string'
  )
    throw new Error('The saved action response did not match this cancellation or change.');
  if (
    known &&
    (!sameIdentity(snapshot, known) ||
      !sameDomain(snapshot.intent.domain, known.intent.domain) ||
      !sameValues(snapshot.intent.modifications, known.intent.modifications) ||
      reviewKey(snapshot.review) !== reviewKey(known.review))
  )
    throw new Error('The saved action response changed its original intent or review.');
  if (
    known &&
    known.status !== 'pending' &&
    (snapshot.status !== known.status || outcomeKey(snapshot) !== outcomeKey(known))
  )
    throw new Error('The saved action response changed its recorded outcome.');
  if (snapshot.status === 'pending') {
    if (snapshot.result !== null || snapshot.refusal !== null || snapshot.challenge === undefined)
      throw new Error('The pending action response is incomplete.');
    if (snapshot.challenge !== null) validateChallenge(snapshot);
  } else if (snapshot.status === 'applied') {
    const result = snapshot.result;
    if (
      !result ||
      result.kind !== record.purpose ||
      snapshot.refusal !== null ||
      snapshot.challenge !== null ||
      (result.kind === 'cancel' && (!STATUSES.includes(result.fromStatus) || result.toStatus !== 'cancelled')) ||
      (result.kind === 'modify' &&
        (!Number.isSafeInteger(result.modificationCount) ||
          result.modificationCount < 1 ||
          !Array.isArray(result.changes) ||
          result.changes.some(
            (change) =>
              !change ||
              !['quantity', 'min_quantity', 'price_per_share'].includes(change.field) ||
              typeof change.old !== 'string' ||
              typeof change.new !== 'string',
          )))
    )
      throw new Error('The applied action response is incomplete.');
  } else if (snapshot.status === 'refused') {
    const refusal = snapshot.refusal;
    const allowed =
      record.purpose === 'cancel'
        ? { order_cancellation_failed: 400 }
        : { order_modification_failed: 400, order_modification_conflict: 409 };
    if (
      !refusal ||
      !(refusal.code in allowed) ||
      allowed[refusal.code as keyof typeof allowed] !== refusal.httpStatus ||
      typeof refusal.detail !== 'string' ||
      !refusal.detail.trim() ||
      refusal.detail.length > 2000 ||
      snapshot.result !== null ||
      snapshot.challenge !== null
    )
      throw new Error('The refusal response does not establish a recorded outcome.');
  } else throw new Error('The action response has an unknown status.');
}

export function validateOrderActionIssuance(
  snapshot: OrderActionSnapshot,
  context: OrderActionContext,
  replacements: OrderActionValues | null,
): void {
  if (
    !sameIdentity(snapshot, context) ||
    !sameDomain(snapshot.intent.domain, context.domain) ||
    !sameValues(snapshot.intent.modifications, replacements)
  )
    throw new Error(
      'The signing context changed. Check this saved action and review its recorded details before signing.',
    );
}

function validateChallenge(snapshot: OrderActionSnapshot): void {
  const challenge = snapshot.challenge!;
  const primary = snapshot.purpose === 'cancel' ? 'OrderCancelV1' : 'OrderModifyV1';
  const expected: Record<string, string> = {
    actionId: 'string',
    protocolVersion: 'uint256',
    ownerAccountUuid: 'string',
    walletUuid: 'string',
    tokenUuid: 'string',
    orderUuid: 'string',
    wallet: 'address',
    nonce: 'uint256',
    deadline: 'uint256',
    ...(snapshot.purpose === 'modify'
      ? { newQuantity: 'uint256', newMinQuantity: 'uint256', newPricePerShare: 'string' }
      : {}),
  };
  const fields = challenge.types?.[primary];
  const message = challenge.message;
  const expiry = Date.parse(challenge.expiresAt);
  if (
    challenge.purpose !== `order_${snapshot.purpose}` ||
    !domain(challenge.domain) ||
    !sameDomain(challenge.domain, snapshot.intent.domain) ||
    !/^0x[0-9a-f]{64}$/i.test(challenge.digest) ||
    !Number.isFinite(expiry) ||
    !Array.isArray(fields) ||
    Object.keys(challenge.types).length !== 1 ||
    fields.length !== Object.keys(expected).length ||
    new Set(fields.map((field) => field.name)).size !== fields.length ||
    fields.some((field) => !field || expected[field.name] !== field.type) ||
    !message ||
    Object.keys(message).length !== Object.keys(expected).length ||
    message.actionId !== snapshot.actionId ||
    message.protocolVersion !== '1' ||
    message.ownerAccountUuid !== snapshot.ownerAccountUuid ||
    message.walletUuid !== snapshot.walletUuid ||
    message.tokenUuid !== snapshot.tokenUuid ||
    message.orderUuid !== snapshot.orderUuid ||
    typeof message.wallet !== 'string' ||
    message.wallet.toLowerCase() !== snapshot.walletAddress.toLowerCase() ||
    !integer(message.nonce, (1n << 256n) - 1n) ||
    !integer(message.deadline) ||
    message.deadline !== Math.floor(expiry / 1000).toString() ||
    (snapshot.purpose === 'modify' &&
      (message.newQuantity !== snapshot.intent.modifications!.quantity ||
        message.newMinQuantity !== snapshot.intent.modifications!.minQuantity ||
        message.newPricePerShare !== snapshot.intent.modifications!.pricePerShare))
  )
    throw new Error('The signing request did not bind the reviewed action and exact values.');
}
