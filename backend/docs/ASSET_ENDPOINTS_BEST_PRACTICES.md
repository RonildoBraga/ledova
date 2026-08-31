# Asset Model & API Documentation

## Overview

The Ledova backend provides a unified `Asset` model representing all tradable assets that users can hold in their portfolios and wallets.

## What Are Assets?

**Assets** in Ledova represent any tradable financial instrument that can be:
- Held in a wallet (cryptocurrencies)
- Tracked in a portfolio
- Priced and displayed to users

Assets are **reference data** managed by admins - users cannot create or modify assets.

## Asset Types

| Type | Examples | Description |
|------|----------|-------------|
| `native_crypto` | BTC, ETH, SOL | Native blockchain coins |
| `erc20_token` | LINK, UNI, AAVE | ERC-20 tokens on Ethereum |
| `stablecoin` | USDC, USDT, DAI | Fiat-pegged stablecoins |
| `tokenized_security` | AAPL.t, VAS.t | Tokenized traditional securities |
| `tokenized_rwa` | - | Tokenized real-world assets (bonds, treasuries) |
| `synthetic` | - | Synthetic tracking tokens |

## Asset Model

**Location:** `assets/models/asset.py`

| Field | Type | Description |
|-------|------|-------------|
| `uuid` | UUID | Primary key |
| `symbol` | CharField | Trading symbol (e.g., BTC, ETH) - unique |
| `name` | CharField | Full name (e.g., Bitcoin, Ethereum) |
| `asset_type` | CharField | Classification (see types above) |
| `chain` | CharField | Blockchain (ethereum, bitcoin, polygon, etc.) |
| `contract_address` | CharField | Smart contract address (null for native tokens) |
| `decimals` | Integer | Token decimals (default: 18) |
| `current_price` | Decimal | Latest price |
| `price_currency` | CharField | Price currency (default: USD) |
| `is_active` | Boolean | Whether asset is actively tradable |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

## API Endpoints

### List/Retrieve Assets

```
GET /api/assets/
GET /api/assets/{uuid}/
```

**Authentication:** Required
**Permissions:** Read-only (clients cannot create/update/delete)

**Query Parameters:**
| Parameter | Description |
|-----------|-------------|
| `symbol` | Filter by symbol (exact match) |
| `asset_type` | Filter by type (native_crypto, stablecoin, etc.) |
| `chain` | Filter by blockchain |
| `is_active` | Filter by active status (true/false) |
| `search` | Search by symbol or name |

**Example Response:**
```json
{
  "uuid": "123e4567-e89b-12d3-a456-426614174000",
  "symbol": "BTC",
  "name": "Bitcoin",
  "asset_type": "native_crypto",
  "asset_type_display": "Crypto",
  "chain": "bitcoin",
  "contract_address": null,
  "decimals": 8,
  "current_price": "45000.00",
  "price_currency": "USD",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-15T12:00:00Z"
}
```

### Price History

```
GET /api/assets/{uuid}/snapshots/
```

**Query Parameters:**
- `start_date` - ISO datetime
- `end_date` - ISO datetime
- `limit` - Max results (default: 100)

## Usage Examples

```bash
# Get all active assets
GET /api/assets/?is_active=true

# Get only cryptocurrencies
GET /api/assets/?asset_type=native_crypto

# Get stablecoins
GET /api/assets/?asset_type=stablecoin

# Get Ethereum-based assets
GET /api/assets/?chain=ethereum

# Search for Bitcoin
GET /api/assets/?search=bitcoin
```

## Price Updates

Asset prices are updated automatically via procrastinate tasks:
- **`sync_all_assets`** runs every 10 minutes (`@app.periodic`)
- Fetches prices from CoinGecko API
- Can also be triggered manually: `python manage.py asset_sync`

## Security

- **Read-only API** - Clients cannot create, update, or delete assets
- **Admin-managed** - Assets are created/modified via Django Admin only
- **Authentication required** - All endpoints require valid auth tokens

## Related Models

- **AssetSnapshot** - Historical price data points
- **Wallet** - User wallets that hold assets
- **PortfolioHolding** - Portfolio positions in assets
