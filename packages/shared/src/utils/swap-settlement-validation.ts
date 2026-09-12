import { SwapSettlementError } from './swap-settlement-error';
import type {
  ApprovalTransaction,
  SettlementSwapOrder,
  SwapOrder,
  SwapSettlementApprovalConfirmed,
  SwapSettlementApprovalData,
  SwapSettlementApprovalStatus,
  SwapSettlementApprovalUnconfirmed,
  SwapSettlementContext,
  SwapSettlementCrypto,
  SwapSettlementIdentity,
  SwapSettlementLookup,
  SwapSettlementParty,
  SwapSettlementResponse,
  SwapSettlementSelection,
  SwapSettlementSignedApproval,
  SwapSettlementTypedData,
  Wallet,
} from '../types';
import type { OrderSubmissionOwner } from './order-submission-storage';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH = /^0x[0-9a-f]{64}$/i;
const MAX_UINT = (1n << 256n) - 1n;
const STATUSES = ['created', 'seller_signed', 'buyer_signed', 'ready', 'executing', 'completed', 'failed', 'expired'];
const DOMAIN_FIELDS = ['name:string', 'version:string', 'chainId:uint256', 'verifyingContract:address'];
const MESSAGE_FIELDS = [
  'seller:address',
  'buyer:address',
  'shareToken:address',
  'paymentToken:address',
  'shareAmount:uint256',
  'paymentAmount:uint256',
  'nonce:uint256',
  'deadline:uint256',
];

function requireValue(
  condition: unknown,
  message = 'The settlement response did not match the reviewed swap.',
): asserts condition {
  if (!condition) throw new SwapSettlementError(message);
}

function uint(value: unknown): value is string {
  return typeof value === 'string' && /^(0|[1-9]\d*)$/.test(value) && value.length <= 78 && BigInt(value) <= MAX_UINT;
}

function address(value: unknown): value is string {
  return typeof value === 'string' && /^0x[0-9a-f]{40}$/i.test(value) && !/^0x0{40}$/i.test(value);
}

function sameAddress(left: unknown, right: unknown): boolean {
  return address(left) && address(right) && left.toLowerCase() === right.toLowerCase();
}

function scale(value: unknown): boolean {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= 255;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(',')}}`;
  return JSON.stringify(value);
}

function party(value: SwapSettlementParty | undefined): boolean {
  return (
    !!value &&
    [value.orderUuid, value.ownerAccountUuid, value.walletUuid].every(
      (id) => typeof id === 'string' && UUID.test(id),
    ) &&
    (value.paymentAssetUuid === null ||
      (typeof value.paymentAssetUuid === 'string' && UUID.test(value.paymentAssetUuid))) &&
    address(value.address)
  );
}

export function validateSwapSettlementLookup(value: SwapSettlementLookup): void {
  requireValue(
    value &&
      [value.orderUuid, value.swapUuid, value.ownerAccountUuid, value.walletUuid].every(
        (id) => typeof id === 'string' && UUID.test(id),
      ) &&
      (value.settlementDigest === undefined || HASH.test(value.settlementDigest)),
  );
}

export function swapSettlementIdentity(value: SwapSettlementIdentity): SwapSettlementIdentity {
  validateSwapSettlementLookup(value);
  requireValue(HASH.test(value.settlementDigest));
  return {
    orderUuid: value.orderUuid,
    swapUuid: value.swapUuid,
    ownerAccountUuid: value.ownerAccountUuid,
    walletUuid: value.walletUuid,
    settlementDigest: value.settlementDigest,
  };
}

function echo(value: SwapSettlementIdentity, expected: SwapSettlementLookup): void {
  validateSwapSettlementLookup(value);
  requireValue(
    HASH.test(value.settlementDigest) &&
      value.orderUuid === expected.orderUuid &&
      value.swapUuid === expected.swapUuid &&
      value.ownerAccountUuid === expected.ownerAccountUuid &&
      value.walletUuid === expected.walletUuid &&
      (expected.settlementDigest === undefined ||
        value.settlementDigest.toLowerCase() === expected.settlementDigest.toLowerCase()),
  );
}

function typedData(typed: SwapSettlementTypedData): void {
  requireValue(typed && typed.primaryType === 'SwapOrder' && typed.domain && typed.message && typed.types);
  requireValue(Object.keys(typed.types).sort().join(',') === 'EIP712Domain,SwapOrder');
  for (const [name, expected] of [
    ['EIP712Domain', DOMAIN_FIELDS],
    ['SwapOrder', MESSAGE_FIELDS],
  ] as const) {
    const fields = typed.types[name];
    requireValue(
      Array.isArray(fields) &&
        fields.length === expected.length &&
        fields.every(
          (field, index) =>
            field &&
            Object.keys(field).sort().join(',') === 'name,type' &&
            `${field.name}:${field.type}` === expected[index],
        ),
    );
  }
  requireValue(
    Object.keys(typed.domain).sort().join(',') === 'chainId,name,verifyingContract,version' &&
      typed.domain.name === 'LedovaAtomicSwap' &&
      typed.domain.version === '1' &&
      uint(typed.domain.chainId) &&
      typed.domain.chainId !== '0' &&
      address(typed.domain.verifyingContract),
  );
  requireValue(
    Object.keys(typed.message).sort().join(',') ===
      MESSAGE_FIELDS.map((field) => field.split(':')[0])
        .sort()
        .join(','),
  );
  for (const [key, value] of Object.entries(typed.message)) {
    requireValue(['seller', 'buyer', 'shareToken', 'paymentToken'].includes(key) ? address(value) : uint(value));
  }
  requireValue(
    typed.message.shareAmount !== '0' && typed.message.paymentAmount !== '0' && typed.message.deadline !== '0',
  );
}

async function context(value: SwapSettlementContext, crypto: SwapSettlementCrypto): Promise<void> {
  requireValue(
    value && value.protocolVersion === 1 && UUID.test(value.swapUuid) && party(value.seller) && party(value.buyer),
  );
  const share = value.shareToken;
  const payment = value.paymentAsset;
  requireValue(
    share &&
      payment &&
      UUID.test(share.uuid) &&
      UUID.test(payment.uuid) &&
      UUID.test(payment.deploymentUuid) &&
      [share.chain, share.name, share.symbol, payment.name, payment.symbol, payment.deploymentChain].every(
        (item) => typeof item === 'string',
      ) &&
      [share.decimals, payment.pricingDecimals, payment.deploymentDecimals].every(scale) &&
      typeof value.pricePerShare === 'string' &&
      /^(0|[1-9]\d*)(\.\d+)?$/.test(value.pricePerShare) &&
      HASH.test(value.digest) &&
      /^[0-9a-f]{64}$/i.test(value.orderHash),
  );
  requireValue((value.buyer.paymentAssetUuid ?? value.seller.paymentAssetUuid) === payment.uuid);
  typedData(value.typedData);
  const message = value.typedData.message;
  requireValue(
    sameAddress(value.seller.address, message.seller) &&
      sameAddress(value.buyer.address, message.buyer) &&
      sameAddress(share.address, message.shareToken) &&
      sameAddress(payment.deploymentAddress, message.paymentToken),
  );
  const computed = await crypto.digestTypedData(value.typedData);
  requireValue(
    typeof computed === 'string' && HASH.test(computed) && computed.toLowerCase() === value.digest.toLowerCase(),
    'The signing digest did not match the original settlement.',
  );
}

export async function validateSettlementSwapOrder(
  order: SettlementSwapOrder,
  selection: SwapSettlementSelection,
  crypto: SwapSettlementCrypto,
  known?: SettlementSwapOrder | null,
): Promise<void> {
  requireValue(
    order &&
      order.settlementProtocolVersion === 1 &&
      order.uuid === selection.swapUuid &&
      STATUSES.includes(order.status) &&
      typeof order.sellerHasSigned === 'boolean' &&
      typeof order.buyerHasSigned === 'boolean',
  );
  await context(order.settlementContext, crypto);
  const captured = order.settlementContext;
  requireValue(
    captured.swapUuid === order.uuid &&
      order.settlementDigest === captured.digest &&
      (selection.settlementDigest === undefined ||
        selection.settlementDigest.toLowerCase() === captured.digest.toLowerCase()) &&
      order.orderHash === captured.orderHash &&
      order.sellOrderUuid === captured.seller.orderUuid &&
      order.buyOrderUuid === captured.buyer.orderUuid &&
      sameAddress(order.sellerAddress, captured.seller.address) &&
      sameAddress(order.buyerAddress, captured.buyer.address) &&
      sameAddress(order.shareTokenAddress, captured.shareToken.address) &&
      sameAddress(order.paymentTokenAddress, captured.paymentAsset.deploymentAddress) &&
      order.shareTokenName === captured.shareToken.name &&
      order.shareTokenSymbol === captured.shareToken.symbol &&
      order.paymentTokenSymbol === captured.paymentAsset.symbol &&
      Number.isFinite(Date.parse(order.expiresAt)) &&
      Math.floor(Date.parse(order.expiresAt) / 1000).toString() === captured.typedData.message.deadline,
  );
  requireValue(
    [captured.seller, captured.buyer].some(
      (side) =>
        side.orderUuid === selection.orderUuid &&
        side.ownerAccountUuid === selection.ownerAccountUuid &&
        side.walletUuid === selection.walletUuid &&
        (selection.walletAddress === undefined || sameAddress(selection.walletAddress, side.address)),
    ),
  );
  if (known)
    requireValue(
      canonical(captured) === canonical(known.settlementContext) &&
        (!known.sellerHasSigned || order.sellerHasSigned) &&
        (!known.buyerHasSigned || order.buyerHasSigned),
      'The settlement response changed its original review or stored signature.',
    );
}

export async function validateSwapSettlementResponse(
  value: SwapSettlementResponse,
  selection: SwapSettlementSelection,
  crypto: SwapSettlementCrypto,
  known?: SettlementSwapOrder | null,
): Promise<void> {
  echo(value, selection);
  requireValue(
    ['seller', 'buyer'].includes(value.userRole) &&
      typeof value.hasSigned === 'boolean' &&
      typeof value.canSign === 'boolean' &&
      (value.admissionRefusal === null || typeof value.admissionRefusal === 'string'),
  );
  await validateSettlementSwapOrder(
    value.swapOrder,
    { ...selection, settlementDigest: value.settlementDigest },
    crypto,
    known,
  );
  const side = value.swapOrder.settlementContext[value.userRole];
  requireValue(
    side.orderUuid === value.orderUuid &&
      side.ownerAccountUuid === value.ownerAccountUuid &&
      side.walletUuid === value.walletUuid &&
      value.hasSigned ===
        (value.userRole === 'seller' ? value.swapOrder.sellerHasSigned : value.swapOrder.buyerHasSigned) &&
      value.canSign === (value.admissionRefusal === null && !value.hasSigned) &&
      canonical(value.typedData) === canonical(value.swapOrder.settlementContext.typedData),
  );
}

export function selectSwapSettlementLookup(
  swap: SettlementSwapOrder,
  owner: OrderSubmissionOwner,
  wallet: Pick<Wallet, 'uuid' | 'userAccount' | 'address'>,
  orderUuid?: string,
): SwapSettlementSelection {
  requireValue(wallet.userAccount === owner.ownerAccountUuid && swap.settlementProtocolVersion === 1);
  const sides = [swap.settlementContext.seller, swap.settlementContext.buyer].filter(
    (side) =>
      side.ownerAccountUuid === owner.ownerAccountUuid &&
      side.walletUuid === wallet.uuid &&
      sameAddress(side.address, wallet.address) &&
      (orderUuid === undefined || orderUuid === side.orderUuid),
  );
  requireValue(sides.length === 1, 'Choose the current account’s original order and wallet for this swap.');
  return {
    swapUuid: swap.uuid,
    orderUuid: sides[0]!.orderUuid,
    ownerAccountUuid: owner.ownerAccountUuid,
    walletUuid: wallet.uuid,
    walletAddress: wallet.address,
    settlementDigest: swap.settlementDigest,
  };
}

export function swapSettlementRole(response: SwapSettlementResponse, signerAddress: string): 'seller' | 'buyer' {
  const captured = response.swapOrder.settlementContext;
  if (sameAddress(signerAddress, captured.seller.address)) return 'seller';
  if (sameAddress(signerAddress, captured.buyer.address)) return 'buyer';
  throw new SwapSettlementError('The signature did not belong to an original settlement participant.');
}

export function swapSettlementAdmitted(response: SwapSettlementResponse, now = Date.now()): boolean {
  return (
    response.admissionRefusal === null &&
    ['created', 'seller_signed', 'buyer_signed', 'ready'].includes(response.swapOrder.status) &&
    BigInt(response.typedData.message.deadline) * 1000n > BigInt(Math.floor(now))
  );
}

function approvalIdentity(
  value: SwapSettlementIdentity & { userRole: string },
  response: SwapSettlementResponse,
): void {
  echo(value, response);
  requireValue(value.userRole === response.userRole);
}

function approvalTerms(response: SwapSettlementResponse) {
  const captured = response.swapOrder.settlementContext;
  const seller = response.userRole === 'seller';
  return {
    token: seller ? captured.shareToken.address : captured.paymentAsset.deploymentAddress,
    symbol: seller ? captured.shareToken.symbol : captured.paymentAsset.symbol,
    amount: seller ? response.typedData.message.shareAmount : response.typedData.message.paymentAmount,
    owner: captured[response.userRole].address,
    spender: response.typedData.domain.verifyingContract,
  };
}

export function validateSwapSettlementApprovalStatus(
  value: SwapSettlementApprovalStatus,
  response: SwapSettlementResponse,
): void {
  approvalIdentity(value, response);
  const terms = approvalTerms(response);
  requireValue(
    sameAddress(value.tokenAddress, terms.token) &&
      value.tokenSymbol === terms.symbol &&
      sameAddress(value.spender, terms.spender) &&
      value.requiredAmount === terms.amount &&
      uint(value.currentAllowance) &&
      value.needsApproval === BigInt(value.currentAllowance) < BigInt(terms.amount),
  );
}

function hexInteger(value: unknown): value is string {
  return typeof value === 'string' && /^0x[0-9a-f]+$/i.test(value) && value.length <= 66;
}

function approvalTransaction(value: ApprovalTransaction, response: SwapSettlementResponse): void {
  const terms = approvalTerms(response);
  const calldata = `0x095ea7b3${terms.spender.slice(2).toLowerCase().padStart(64, '0')}${MAX_UINT.toString(16)}`;
  requireValue(
    value &&
      sameAddress(value.from, terms.owner) &&
      sameAddress(value.to, terms.token) &&
      typeof value.data === 'string' &&
      value.data.toLowerCase() === calldata &&
      [value.value, value.gas, value.gasPrice, value.nonce, value.chainId].every(hexInteger) &&
      BigInt(value.value) === 0n &&
      BigInt(value.chainId).toString() === response.typedData.domain.chainId &&
      BigInt(value.gas) > 0n,
  );
}

export function validateSwapSettlementApprovalData(
  value: SwapSettlementApprovalData,
  response: SwapSettlementResponse,
): void {
  approvalIdentity(value, response);
  const terms = approvalTerms(response);
  if (value.needsApproval === false) {
    requireValue(
      value.requiredAmount === terms.amount &&
        uint(value.currentAllowance) &&
        BigInt(value.currentAllowance) >= BigInt(terms.amount) &&
        typeof value.message === 'string',
    );
  } else {
    requireValue(
      value.needsApproval === true &&
        value.unlimited === true &&
        value.amount === MAX_UINT.toString() &&
        sameAddress(value.tokenAddress, terms.token) &&
        value.tokenSymbol === terms.symbol &&
        sameAddress(value.spender, terms.spender) &&
        typeof value.description === 'string',
    );
    approvalTransaction(value.transaction, response);
  }
}

export function validateSwapSettlementSignedApproval(
  value: SwapSettlementSignedApproval,
  expected: ApprovalTransaction,
  response: SwapSettlementResponse,
): void {
  requireValue(value && HASH.test(value.txHash));
  approvalTransaction(value.transaction, response);
  for (const key of ['value', 'gas', 'gasPrice', 'nonce', 'chainId'] as const)
    requireValue(
      BigInt(value.transaction[key]) === BigInt(expected[key]),
      'The signed approval changed the reviewed transaction.',
    );
  requireValue(
    value.transaction.data.toLowerCase() === expected.data.toLowerCase() &&
      sameAddress(value.transaction.to, expected.to) &&
      sameAddress(value.transaction.from, expected.from),
  );
}

export function validateSwapSettlementApprovalResult(
  value: SwapSettlementApprovalConfirmed | SwapSettlementApprovalUnconfirmed,
  status: number,
  response: SwapSettlementResponse,
  txHash: string,
): void {
  approvalIdentity(value, response);
  requireValue(HASH.test(value.txHash) && value.txHash.toLowerCase() === txHash.toLowerCase());
  if (status === 503) {
    const uncertain = value as SwapSettlementApprovalUnconfirmed;
    requireValue(
      uncertain.code === 'swap_approval_unconfirmed' &&
        typeof uncertain.detail === 'string' &&
        !('blockNumber' in value) &&
        !('gasUsed' in value),
    );
  } else {
    const confirmed = value as SwapSettlementApprovalConfirmed;
    requireValue(
      status === 200 &&
        !('code' in value) &&
        [confirmed.blockNumber, confirmed.gasUsed].every(
          (item) => item === null || (typeof item === 'number' && Number.isSafeInteger(item) && item >= 0),
        ),
    );
  }
}

export function hasSwapSettlementContext(swap: SwapOrder): swap is SettlementSwapOrder {
  return (
    swap.settlementProtocolVersion === 1 &&
    !!swap.settlementContext &&
    typeof swap.settlementDigest === 'string' &&
    (swap.completedAt === null || typeof swap.completedAt === 'string')
  );
}
