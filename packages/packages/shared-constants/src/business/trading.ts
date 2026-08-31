export const ORDER_TYPE = {
  BUY: 'buy',
  SELL: 'sell',
} as const;

export type OrderType = (typeof ORDER_TYPE)[keyof typeof ORDER_TYPE];

export const ORDER_STATUS = {
  OPEN: 'open',
  PARTIALLY_FILLED: 'partially_filled',
  MATCHED: 'matched',
  PENDING_SIGNATURE: 'pending_signature',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  EXPIRED: 'expired',
} as const;

export type OrderStatus = (typeof ORDER_STATUS)[keyof typeof ORDER_STATUS];

export const SWAP_STATUS = {
  CREATED: 'created',
  SELLER_SIGNED: 'seller_signed',
  BUYER_SIGNED: 'buyer_signed',
  READY: 'ready',
  EXECUTING: 'executing',
  COMPLETED: 'completed',
  FAILED: 'failed',
  EXPIRED: 'expired',
} as const;

export type SwapStatus = (typeof SWAP_STATUS)[keyof typeof SWAP_STATUS];

export const SWAP_USER_ROLE = {
  SELLER: 'seller',
  BUYER: 'buyer',
} as const;

export type SwapUserRole = (typeof SWAP_USER_ROLE)[keyof typeof SWAP_USER_ROLE];

export const TRADING_EVENT_TYPES = {
  ORDER_CREATED: 'order_created',
  ORDER_CANCELLED: 'order_cancelled',
  ORDER_MODIFIED: 'order_modified',
  ORDER_MATCHED: 'order_matched',
  SWAP_SIGNED: 'swap_signed',
  SWAP_COMPLETED: 'swap_completed',
  SWAP_FAILED: 'swap_failed',
} as const;

export type TradingEventType = (typeof TRADING_EVENT_TYPES)[keyof typeof TRADING_EVENT_TYPES];

export const TRADING_EVENT_INVALIDATION_MAP: Record<TradingEventType, string[][]> = {
  order_created: [
    ['trading', 'orderBook'],
    ['trading', 'userOrders'],
  ],
  order_cancelled: [
    ['trading', 'orderBook'],
    ['trading', 'userOrders'],
  ],
  order_modified: [
    ['trading', 'orderBook'],
    ['trading', 'userOrders'],
  ],
  order_matched: [
    ['trading', 'orderBook'],
    ['trading', 'userOrders'],
    ['trading', 'swaps'],
  ],
  swap_signed: [
    ['trading', 'swaps'],
    ['trading', 'orderSwapData'],
  ],
  swap_completed: [
    ['trading', 'swaps'],
    ['trading', 'userOrders'],
    ['trading', 'walletBalances'],
  ],
  swap_failed: [
    ['trading', 'swaps'],
    ['trading', 'userOrders'],
  ],
};

export const TRADING_ENDPOINTS = {
  TOKENS: {
    LIST: '/api/v1/trading/tokens/',
    DETAIL: (uuid: string) => `/api/v1/trading/tokens/${uuid}/` as const,
    ORDER_BOOK: (uuid: string) => `/api/v1/trading/tokens/${uuid}/order-book/` as const,
    MARKET_DATA: (uuid: string) => `/api/v1/trading/tokens/${uuid}/market-data/` as const,
  },
  ORDERS: {
    LIST: '/api/v1/trading/orders/',
    DETAIL: (uuid: string) => `/api/v1/trading/orders/${uuid}/` as const,
    CREATE: '/api/v1/trading/orders/create/',
    CREATE_MESSAGE: '/api/v1/trading/orders/create/message/',
    CANCEL: (uuid: string) => `/api/v1/trading/orders/${uuid}/cancel/` as const,
    CANCEL_MESSAGE: (uuid: string) => `/api/v1/trading/orders/${uuid}/cancel/message/` as const,
    MODIFY: (uuid: string) => `/api/v1/trading/orders/${uuid}/modify/` as const,
    MODIFY_MESSAGE: (uuid: string) => `/api/v1/trading/orders/${uuid}/modify/message/` as const,
    MODIFICATIONS: (uuid: string) => `/api/v1/trading/orders/${uuid}/modifications/` as const,
    SWAP: (uuid: string) => `/api/v1/trading/orders/${uuid}/swap/` as const,
    SWAP_SIGN: (uuid: string) => `/api/v1/trading/orders/${uuid}/swap/sign/` as const,
    SWAP_APPROVAL_STATUS: (uuid: string) => `/api/v1/trading/orders/${uuid}/swap/approval-status/` as const,
    SWAP_APPROVAL_DATA: (uuid: string) => `/api/v1/trading/orders/${uuid}/swap/approval-data/` as const,
  },
  WALLETS: {
    BALANCES: '/api/v1/trading/wallets/balances/',
  },
  SWAPS: {
    LIST: '/api/v1/trading/swaps/',
  },
  STABLECOINS: {
    LIST: '/api/v1/trading/stablecoins/',
  },
  TRANSACTIONS: {
    LIST: '/api/v1/trading/transactions/',
  },
  TRANSFERS: {
    PREPARE: '/api/v1/trading/transfers/prepare/',
    BROADCAST: '/api/v1/trading/transfers/broadcast/',
  },
  WHITELIST: {
    STATUS: (address: string) => `/api/v1/trading/whitelist/${address}/status/` as const,
  },
  EVENTS: {
    STREAM: '/api/v1/trading/events/stream/',
  },
} as const;

export const TRADING_CONFIG = {
  ORDER_BOOK_FALLBACK_INTERVAL: 120000,
  DEFAULT_ORDER_EXPIRY_DAYS: 7,
  SSE_RECONNECT_DELAY: 3000,
  SSE_MAX_RECONNECT_DELAY: 30000,
  SSE_HEARTBEAT_TIMEOUT: 45000,
} as const;
