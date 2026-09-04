# Interface Naming Conventions

This document outlines the naming conventions for TypeScript interfaces in the `@ledova/shared-types` package.

## Status: Implemented

All interface renaming changes described in this document have been implemented as of version 8.22.468.

---

## Recommended Naming Patterns

### 1. Entity Types (API responses representing database models)

**Pattern:** `EntityName` (no suffix)

Examples:

- `Asset`, `Wallet`, `Portfolio`, `Transaction`, `UserProfile`, `FavouriteAsset`

### 2. Create Request Types (POST body for creating entities)

**Pattern:** `Create{EntityName}`

Examples:

- `CreateWidget` ✅
- `CreateFavouriteAsset` ✅

### 3. Update Request Types (PATCH/PUT body for updating entities)

**Pattern:** `Update{EntityName}`

Examples:

- `UpdateWidget` ✅
- `UpdateUserPreferences` ✅

### 4. Query Parameters (GET request query strings)

**Pattern:** `{EntityName}QueryParams`

Examples:

- `AssetQueryParams` ✅
- `WalletQueryParams` ✅
- `FavouriteAssetQueryParams` ✅

### 5. API Response Types (non-entity responses)

**Pattern:** `{ActionName}Response`

Examples:

- `SyncWalletResponse` ✅
- `PrepareTransferResponse` ✅

### 6. API Request Types (non-CRUD action requests)

**Pattern:** `{ActionName}Request`

Examples:

- `PrepareTransferRequest` ✅
- `BroadcastTransferRequest` ✅
- `VerifyWalletRequest` ✅
- `SigninRequest` ✅
- `SignupRequest` ✅
- `EmailVerificationRequest` ✅
- `TokenRefreshRequest` ✅
- `WaitlistSignupRequest` ✅

### 7. Query Request Types (GET requests with parameters)

**Pattern:** `Get{ActionName}Request`

Examples:

- `GetOnRampQuotesRequest` ✅
- `GetOnRampWidgetRequest` ✅
- `GetBatchBalanceRequest` ✅

---

## Implemented Changes

### Auth Domain (`domain/auth.ts`)

| Interface Name             | Status         |
| -------------------------- | -------------- |
| `SigninRequest`            | ✅ Implemented |
| `SignupRequest`            | ✅ Implemented |
| `EmailVerificationRequest` | ✅ Implemented |
| `TokenRefreshRequest`      | ✅ Implemented |
| `TokenRefreshResult`       | ✅ Implemented |

### API Types (`api.ts`)

| Interface Name          | Status         |
| ----------------------- | -------------- |
| `WaitlistSignupRequest` | ✅ Implemented |

### User Preferences Domain (`domain/user-preferences.ts`)

| Interface Name          | Status         |
| ----------------------- | -------------- |
| `UpdateUserPreferences` | ✅ Implemented |

### On-Ramp Domain (`domain/onramp.ts`)

| Interface Name           | Status         |
| ------------------------ | -------------- |
| `GetOnRampQuotesRequest` | ✅ Implemented |
| `GetOnRampWidgetRequest` | ✅ Implemented |

### Chain Domain (`domain/chain.ts`)

| Interface Name           | Status         |
| ------------------------ | -------------- |
| `GetBatchBalanceRequest` | ✅ Implemented |
